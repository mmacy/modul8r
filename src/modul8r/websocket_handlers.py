import asyncio
import json
from typing import Set, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from .logging_config import get_logger, log_capture

logger = get_logger("websocket")


class LogStreamManager:
    """Manages WebSocket connections for real-time log streaming."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.connection_info: Dict[WebSocket, Dict[str, Any]] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str = None):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        
        self.connection_info[websocket] = {
            "client_id": client_id or f"client_{id(websocket)}",
            "connected_at": asyncio.get_event_loop().time()
        }
        
        # Add to log capture subscribers
        log_capture.add_subscriber(websocket)
        
        logger.info("WebSocket client connected", 
                   client_id=self.connection_info[websocket]["client_id"],
                   total_connections=len(self.active_connections))
        
        # Send recent log entries to new client
        recent_logs = log_capture.get_recent_entries(limit=50)
        if recent_logs:
            try:
                await websocket.send_json({
                    "type": "log_history",
                    "logs": recent_logs
                })
            except Exception as e:
                logger.error("Failed to send log history to new client", error=str(e))
    
    async def disconnect(self, websocket: WebSocket):
        """Handle client disconnection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            client_info = self.connection_info.pop(websocket, {})
            
            # Remove from log capture subscribers
            log_capture.remove_subscriber(websocket)
            
            logger.info("WebSocket client disconnected",
                       client_id=client_info.get("client_id", "unknown"),
                       total_connections=len(self.active_connections))
    
    async def broadcast_log(self, log_entry: Dict[str, Any]):
        """Broadcast a log entry to all connected clients."""
        if not self.active_connections:
            return
        
        message = {
            "type": "log_entry",
            "log": log_entry
        }
        
        disconnected_clients = set()
        
        for websocket in self.active_connections:
            try:
                await websocket.send_json(message)
            except (WebSocketDisconnect, ConnectionClosed, RuntimeError) as e:
                logger.warning("Client disconnected during broadcast",
                             client_id=self.connection_info.get(websocket, {}).get("client_id", "unknown"),
                             error=str(e))
                disconnected_clients.add(websocket)
            except Exception as e:
                logger.error("Error broadcasting to client",
                           client_id=self.connection_info.get(websocket, {}).get("client_id", "unknown"),
                           error=str(e))
                disconnected_clients.add(websocket)
        
        # Clean up disconnected clients
        for websocket in disconnected_clients:
            await self.disconnect(websocket)
    
    async def send_status_update(self, status: Dict[str, Any]):
        """Send processing status update to all connected clients."""
        if not self.active_connections:
            return
        
        message = {
            "type": "status_update", 
            "status": status
        }
        
        disconnected_clients = set()
        
        for websocket in self.active_connections:
            try:
                await websocket.send_json(message)
            except (WebSocketDisconnect, ConnectionClosed, RuntimeError):
                disconnected_clients.add(websocket)
            except Exception as e:
                logger.error("Error sending status update",
                           client_id=self.connection_info.get(websocket, {}).get("client_id", "unknown"),
                           error=str(e))
        
        # Clean up disconnected clients
        for websocket in disconnected_clients:
            await self.disconnect(websocket)
    
    def get_connection_count(self) -> int:
        """Get the current number of active connections."""
        return len(self.active_connections)


# Global log stream manager instance
log_stream_manager = LogStreamManager()


# Enhanced log capture to work with WebSocket broadcasting  
class WebSocketLogCapture:
    """Enhanced log capture that broadcasts to WebSocket clients."""
    
    def __init__(self):
        # Don't override the original method, just enhance the log_capture instance
        self._original_add_entry = getattr(log_capture, 'add_entry', None)
        if self._original_add_entry:
            # Store reference but don't override to avoid duplication
            log_capture._websocket_manager = log_stream_manager


# Initialize the enhanced log capture on module import
websocket_log_capture = WebSocketLogCapture()