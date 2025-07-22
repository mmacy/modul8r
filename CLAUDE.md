# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

modul8r is a personal-use web service that converts scanned tabletop RPG adventure module PDFs into Markdown format using OpenAI's vision models. The service uses a vision-centric approach, analyzing each PDF page as an image to generate structured text.

## Architecture

The application will be built with:

- **Backend**: Python 3.13+ with FastAPI framework  
- **Frontend**: Web UI served directly from FastAPI with Jinja2 templating
- **AI Integration**: OpenAI Python SDK for vision model processing
- **PDF Processing**: pdf2image library (requires poppler system dependency)
- **Package Management**: uv

## Core Components

### API Endpoints
- `GET /` - Serves the main HTML page for web UI
- `GET /models` - Returns available OpenAI vision models via client.models.list()  
- `POST /convert` - Accepts multipart/form-data with PDF files, model selection, and detail level

### Processing Flow
1. Receive uploaded PDF files via web form or API
2. Rasterize each PDF page into high-resolution images (PNG/JPEG)
3. Base64-encode images for OpenAI API transmission
4. Send each page to selected OpenAI vision model with system prompt for TTRPG conversion
5. Concatenate Markdown results with horizontal rules (---) between pages
6. Return JSON response with filename keys and Markdown content values

### Key Features
- Batch processing of multiple PDF files
- Dynamic model selection from OpenAI API
- Configurable image detail level (low/high, default: high)
- Web UI for easy file upload and conversion
- REST API for programmatic access

## Development Commands

### Installation
```bash
uv sync --dev  # Install dependencies
playwright install  # Install browser drivers for testing
```

### Running the Application
```bash
uv run python -m src.modul8r.main  # Start development server on http://127.0.0.1:8000
```

### Testing
```bash
uv run pytest  # Run all tests
uv run pytest tests/test_services.py  # Run unit tests only
uv run pytest tests/test_main.py  # Run API tests only
uv run pytest tests/test_playwright.py  # Run web UI tests only
uv run python test_logging_fix.py  # Validate logging configuration
```

### Code Quality
```bash
uv run ruff check  # Lint code
uv run ruff format  # Format code
uv run mypy src/  # Type checking
```

### Environment Setup
The application requires an OpenAI API key. Set the `OPENAI_API_KEY` environment variable or pass it to the OpenAIService constructor.

### System Dependencies
- poppler-utils (for pdf2image library)
  - macOS: `brew install poppler`
  - Ubuntu/Debian: `apt-get install poppler-utils`
  - Windows: Download from poppler website

## Logging System

The application uses structured logging with the following features:

### Configuration
- **JSON Format**: Structured logs with consistent fields (timestamp, level, request_id, etc.)
- **Request Correlation**: All logs within a request share the same request_id for tracing
- **WebSocket Streaming**: Real-time log streaming to web clients (configurable)
- **Deduplication**: Prevents duplicate log entries

### Settings
```bash
MODUL8R_LOG_LEVEL=INFO           # DEBUG, INFO, WARNING, ERROR
MODUL8R_LOG_FORMAT=json          # json or console
MODUL8R_ENABLE_LOG_CAPTURE=true  # Enable WebSocket log streaming
```

### Log Levels
- **DEBUG**: Detailed processing information
- **INFO**: Standard operation events (requests, processing status)
- **WARNING**: Non-critical issues (API fallbacks, file skips)
- **ERROR**: Processing failures and exceptions

### WebSocket Log Streaming
- Endpoint: `ws://localhost:8000/ws/logs`
- Only active when clients are connected (performance optimized)
- JSON messages: `{"type": "log_entry", "log": {...}}`

## Development Notes

This project prioritizes fidelity and accuracy in converting scanned tabletop RPG documents to clean, structured Markdown format. The vision-first approach means the quality of PDF-to-image conversion and prompt engineering for the AI model will be critical success factors.

### Recent Fixes
- **Duplicate Logging**: Resolved console log duplication issue in WebSocket capture processor
- **Performance**: Optimized log processing to only run when needed
- **Memory**: Added cleanup for captured log entries to prevent memory leaks