import logging
import sys
import contextvars
import uuid
from typing import Any, Dict, Optional

import structlog
from structlog.types import EventDict

from .config import settings

# Context variables for request tracing
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default='')
session_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('session_id', default='')


def add_correlation_ids(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add correlation IDs to log entries."""
    request_id = request_id_var.get()
    session_id = session_id_var.get()
    
    if request_id:
        event_dict['request_id'] = request_id
    if session_id:
        event_dict['session_id'] = session_id
    
    return event_dict


def add_app_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add application context to log entries."""
    event_dict['app'] = 'modul8r'
    event_dict['version'] = '0.1.0'
    return event_dict


def capture_logs_processor(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Processor to capture logs for WebSocket streaming."""
    # Import here to avoid circular imports
    global log_capture
    if log_capture is not None:
        # Make a copy of the event_dict for capture
        capture_entry = dict(event_dict)
        log_capture.add_entry(capture_entry)
    return event_dict


def configure_logging() -> None:
    """Configure structured logging for the application."""
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )

    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        add_correlation_ids,
        add_app_context,
        capture_logs_processor,  # Add log capture processor
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.extend([
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(colors=True)
        ])

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper())
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Get a configured logger instance."""
    return structlog.get_logger(name)


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return str(uuid.uuid4())


def set_request_context(request_id: Optional[str] = None, session_id: Optional[str] = None) -> None:
    """Set request context for logging."""
    if request_id:
        request_id_var.set(request_id)
    if session_id:
        session_id_var.set(session_id)


class LogCapture:
    """Capture log entries for streaming to WebSocket clients."""
    
    def __init__(self, max_entries: int = 1000):
        self.max_entries = max_entries
        self.entries: list[Dict[str, Any]] = []
        self._subscribers: list[Any] = []  # WebSocket connections
    
    def add_entry(self, entry: Dict[str, Any]) -> None:
        """Add a log entry and notify subscribers."""
        import asyncio
        import json
        from datetime import datetime
        
        # Ensure entry has required fields
        if 'timestamp' not in entry:
            entry['timestamp'] = datetime.now().isoformat()
        if 'level' not in entry:
            entry['level'] = 'info'
            
        self.entries.append(entry)
        
        # Keep only the most recent entries
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
        
        # Notify WebSocket subscribers asynchronously
        if self._subscribers:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._notify_subscribers_async(entry))
            except RuntimeError:
                # No event loop running, skip WebSocket broadcast
                pass
    
    async def _notify_subscribers_async(self, entry: Dict[str, Any]) -> None:
        """Notify WebSocket subscribers asynchronously."""
        if not self._subscribers:
            return
            
        message = {
            "type": "log_entry",
            "log": entry
        }
        
        disconnected_clients = set()
        
        for websocket in self._subscribers[:]:  # Copy list to avoid modification during iteration
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected_clients.add(websocket)
        
        # Remove disconnected clients
        for websocket in disconnected_clients:
            self.remove_subscriber(websocket)
    
    def _notify_subscribers(self, entry: Dict[str, Any]) -> None:
        """Legacy sync notification method - kept for compatibility."""
        pass
    
    def get_recent_entries(self, limit: int = 100) -> list[Dict[str, Any]]:
        """Get recent log entries."""
        return self.entries[-limit:] if self.entries else []
    
    def add_subscriber(self, subscriber: Any) -> None:
        """Add a WebSocket subscriber."""
        self._subscribers.append(subscriber)
    
    def remove_subscriber(self, subscriber: Any) -> None:
        """Remove a WebSocket subscriber."""
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)


# Global log capture instance
log_capture = LogCapture()


# Configure logging on module import
configure_logging()