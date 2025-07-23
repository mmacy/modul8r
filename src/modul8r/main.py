from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List, Optional, Dict, Any
import asyncio
import uuid
import json
from contextlib import asynccontextmanager

from .services import OpenAIService, PDFService
from .config import settings
from .logging_config import get_logger, set_request_context, generate_request_id
from .websocket_handlers import log_stream_manager
from .performance_monitor import start_performance_monitoring, stop_performance_monitoring, get_global_performance_stats

# Configure logging on startup
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown events."""
    # Startup
    logger.info("Starting Phase 1 foundation safeguards", 
                throttling_enabled=settings.enable_message_throttling,
                memory_management_enabled=settings.enable_enhanced_memory_management,
                performance_monitoring_enabled=settings.enable_performance_monitoring)
    
    # Start performance monitoring if enabled
    if settings.enable_performance_monitoring:
        start_performance_monitoring()
        logger.info("Performance monitoring initialized")
    else:
        logger.info("Performance monitoring disabled")
    
    logger.info("Phase 1 foundation safeguards ready")
    
    yield  # Application runs here
    
    # Shutdown
    logger.info("Shutting down Phase 1 foundation safeguards")
    
    # Stop performance monitoring if it was enabled
    if settings.enable_performance_monitoring:
        stop_performance_monitoring()
        logger.info("Performance monitoring stopped")
    
    logger.info("Phase 1 foundation safeguards shutdown complete")


app = FastAPI(
    title="modul8r",
    description="Convert TTRPG adventure module PDFs to Markdown",
    version="0.1.0",
    lifespan=lifespan
)

templates = Jinja2Templates(directory="templates")

# Dependency injection
def get_openai_service() -> OpenAIService:
    return OpenAIService()

def get_pdf_service() -> PDFService:
    return PDFService()

@app.middleware("http")
async def add_correlation_id_middleware(request: Request, call_next):
    """Add correlation ID to all requests."""
    request_id = request.headers.get(settings.log_correlation_id_header) or generate_request_id()
    set_request_context(request_id=request_id)
    
    logger.info("Request started", 
                method=request.method, 
                url=str(request.url),
                request_id=request_id)
    
    response = await call_next(request)
    
    logger.info("Request completed", 
                method=request.method,
                url=str(request.url), 
                status_code=response.status_code,
                request_id=request_id)
    
    response.headers[settings.log_correlation_id_header] = request_id
    return response

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    logger.info("Serving main page")
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/models")
async def get_models(openai_service: OpenAIService = Depends(get_openai_service)):
    """Get list of available OpenAI models."""
    logger.info("Fetching available models")
    try:
        models = await openai_service.get_vision_models()
        logger.info("Successfully returned models", model_count=len(models))
        return models
    except Exception as e:
        logger.error("Failed to fetch models", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {str(e)}")

@app.post("/convert")
async def convert_pdfs(
    files: List[UploadFile] = File(...),
    model: Optional[str] = Form(None),
    detail: Optional[str] = Form("high"),
    concurrency: Optional[int] = Form(settings.max_concurrent_requests),
    openai_service: OpenAIService = Depends(get_openai_service),
    pdf_service: PDFService = Depends(get_pdf_service)
):
    """Convert uploaded PDF files to Markdown using async processing."""
    if not files:
        logger.error("No files provided in request")
        raise HTTPException(status_code=400, detail="No files provided")
    
    # Validate concurrency setting
    if concurrency is not None:
        concurrency = max(1, min(concurrency, 100))
        openai_service.semaphore = asyncio.Semaphore(concurrency)
        logger.info("Updated concurrency setting", concurrency=concurrency)
    
    # Use default model if none specified
    if not model:
        available_models = await openai_service.get_vision_models()
        model = available_models[0] if available_models else settings.openai_default_model
        logger.info("Using default model", model=model)
    
    logger.info("Starting PDF conversion", 
                file_count=len(files),
                model=model,
                detail=detail,
                concurrency=concurrency)
    
    results = {}
    
    try:
        async with asyncio.timeout(settings.pdf_processing_timeout):
            for file in files:
                if file.content_type != "application/pdf":
                    logger.warning("Skipping non-PDF file", filename=file.filename, content_type=file.content_type)
                    continue
                
                filename = file.filename or "unknown.pdf"
                logger.info("Processing file", filename=filename)
                
                try:
                    # Read PDF file
                    pdf_bytes = await file.read()
                    logger.info("Read PDF file", filename=filename, size=len(pdf_bytes))
                    
                    # Convert PDF pages to images
                    image_bytes_list = pdf_service.pdf_to_images(pdf_bytes)
                    
                    # Convert images to base64
                    image_base64_list = pdf_service.images_to_base64(image_bytes_list)
                    
                    # Process all pages concurrently using TaskGroup
                    markdown_pages = await openai_service.process_images_batch(
                        image_base64_list, model, detail
                    )
                    
                    if markdown_pages:
                        # Combine all pages with double line breaks (no horizontal rules)
                        full_markdown = "\n\n".join(markdown_pages)
                        results[filename] = full_markdown
                        logger.info("Successfully processed file", 
                                  filename=filename,
                                  page_count=len(markdown_pages),
                                  content_length=len(full_markdown))
                    else:
                        results[filename] = "No content could be extracted from this PDF"
                        logger.warning("No content extracted from file", filename=filename)
                    
                except Exception as e:
                    error_msg = f"Error processing {filename}: {str(e)}"
                    results[filename] = error_msg
                    logger.error("File processing failed", filename=filename, error=str(e))
        
        logger.info("Completed PDF conversion", 
                    total_files=len(files),
                    successful_files=len([r for r in results.values() if not r.startswith("Error")]),
                    failed_files=len([r for r in results.values() if r.startswith("Error")]))
        
        return JSONResponse(content=results)
        
    except asyncio.TimeoutError:
        logger.error("PDF processing timeout", timeout=settings.pdf_processing_timeout)
        raise HTTPException(status_code=408, detail=f"Processing timeout after {settings.pdf_processing_timeout} seconds")
    except Exception as e:
        logger.error("Unexpected error during PDF conversion", error=str(e))
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


@app.websocket("/ws/logs")
async def websocket_logs_endpoint(websocket: WebSocket, client_id: str = None):
    """WebSocket endpoint for real-time log streaming."""
    await log_stream_manager.connect(websocket, client_id)
    
    try:
        while True:
            # Keep the connection alive and handle client messages
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data) if data else {}
                
                # Handle client requests
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif message.get("type") == "get_status":
                    status = {
                        "active_connections": log_stream_manager.get_connection_count(),
                        "server_status": "running"
                    }
                    await log_stream_manager.send_status_update(status)
                    
            except json.JSONDecodeError:
                logger.warning("Received invalid JSON from WebSocket client")
                
    except WebSocketDisconnect:
        await log_stream_manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket error", error=str(e))
        await log_stream_manager.disconnect(websocket)

@app.get("/config")
async def get_config():
    """Get current configuration settings."""
    logger.info("Returning current configuration")
    return {
        "max_concurrent_requests": settings.max_concurrent_requests,
        "openai_default_model": settings.openai_default_model,
        "pdf_dpi": settings.pdf_dpi,
        "openai_timeout": settings.openai_timeout,
        "retry_max_attempts": settings.retry_max_attempts
    }

@app.get("/status")
async def get_status():
    """Get application status and health check."""
    logger.info("Health check requested")
    return {
        "status": "healthy",
        "version": "0.1.0",
        "settings": {
            "max_concurrent_requests": settings.max_concurrent_requests,
            "default_model": settings.openai_default_model
        }
    }


if settings.enable_phase1_status_endpoint:
    @app.get("/status/phase1")
    async def get_phase1_status():
        """Get Phase 1 foundation safeguards status and monitoring statistics."""
        logger.info("Phase 1 status requested")
        
        # Get integrated performance and WebSocket statistics
        integrated_stats = log_stream_manager.get_performance_integrated_stats()
        
        # Get memory statistics from enhanced log capture
        from .logging_config import log_capture
        memory_stats = log_capture.get_memory_stats() if hasattr(log_capture, 'get_memory_stats') else {}
        
        return {
            "phase1_status": "active",
            "version": "0.1.0",
            "feature_flags": {
                "message_throttling": settings.enable_message_throttling,
                "memory_management": settings.enable_enhanced_memory_management,
                "performance_monitoring": settings.enable_performance_monitoring
            },
            "safeguards": {
                "message_throttling": {
                    "status": "active" if settings.enable_message_throttling else "disabled",
                    "circuit_breaker_active": integrated_stats["websocket"].get("circuit_breaker_active", False),
                    "current_rate": integrated_stats["websocket"].get("current_rate", 0),
                    "pending_messages": integrated_stats["websocket"].get("pending_messages", 0)
                },
                "memory_management": {
                    "status": "active" if settings.enable_enhanced_memory_management else "disabled",
                    **memory_stats
                },
                "performance_monitoring": {
                    "status": "active" if integrated_stats["event_loop"].get("monitoring_active", False) else "inactive",
                    **integrated_stats["event_loop"]
                }
            },
            "overall_health": integrated_stats["integrated_health"],
            "active_connections": integrated_stats["websocket"].get("active_connections", 0)
        }

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting modul8r server", 
                host=settings.server_host, 
                port=settings.server_port)
    uvicorn.run(
        app, 
        host=settings.server_host, 
        port=settings.server_port,
        reload=settings.server_reload
    )