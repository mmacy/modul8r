import logging
import sys
import contextvars
import uuid
import asyncio
import time
from datetime import datetime, timedelta, UTC
from typing import Any, Dict, Optional
from collections import deque

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
    """Processor to capture logs for WebSocket streaming without console duplication."""
    # Skip if already captured or if capture is disabled
    if event_dict.get('_captured') or not settings.enable_log_capture:
        return event_dict
    
    # Only process for WebSocket capture if there are active subscribers
    try:
        global log_capture
        if log_capture is not None and hasattr(log_capture, 'add_entry') and log_capture.has_subscribers():
            # Create a clean copy for WebSocket without affecting console output
            capture_entry = dict(event_dict)
            capture_entry['_captured'] = True
            capture_entry['_websocket_only'] = True
            log_capture.add_entry(capture_entry)
    except Exception:
        # Silently ignore logging capture errors to avoid recursion
        pass
    
    # Don't mark the original as captured to allow normal console processing
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
        """Add a log entry and notify subscribers with deduplication."""
        import asyncio
        import json
        import hashlib
        from datetime import datetime
        
        # Skip if not a WebSocket-only entry and we don't have subscribers
        if not entry.get('_websocket_only') and not self.has_subscribers():
            return
        
        # Create entry hash for deduplication
        entry_content = f"{entry.get('event', '')}{entry.get('timestamp', '')}{entry.get('request_id', '')}"
        entry_hash = hashlib.md5(entry_content.encode()).hexdigest()
        
        # Prevent duplicate entries within a short time window
        if hasattr(self, '_recent_hashes'):
            if entry_hash in self._recent_hashes:
                return
        else:
            self._recent_hashes = set()
        
        self._recent_hashes.add(entry_hash)
        
        # Clean up old hashes (keep only last 100)
        if len(self._recent_hashes) > 100:
            self._recent_hashes = set(list(self._recent_hashes)[-50:])
        
        # Ensure entry has required fields
        if 'timestamp' not in entry:
            entry['timestamp'] = datetime.now().isoformat()
        if 'level' not in entry:
            entry['level'] = 'info'
        
        # Remove internal flags before storing/broadcasting
        clean_entry = {k: v for k, v in entry.items() if not k.startswith('_')}
        
        self.entries.append(clean_entry)
        
        # Keep only the most recent entries
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
        
        # Notify WebSocket subscribers asynchronously only if we have active subscribers
        if self.has_subscribers():
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._notify_subscribers_async(clean_entry))
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
    
    def has_subscribers(self) -> bool:
        """Check if there are any active WebSocket subscribers."""
        return len(self._subscribers) > 0


class EnhancedLogCapture(LogCapture):
    """
    Extended LogCapture with age-based eviction and memory management
    for Phase 1 foundation safeguards.
    
    Features:
    - Age-based log entry cleanup (default: 1 hour)
    - Periodic memory monitoring and cleanup
    - Session memory usage tracking
    - Enhanced deduplication with timestamp awareness
    """
    
    def __init__(self, max_entries: Optional[int] = None, max_age_seconds: Optional[int] = None):
        # Use configuration settings with fallbacks
        max_entries = max_entries or settings.enhanced_log_capture_max_entries
        max_age_seconds = max_age_seconds or settings.enhanced_log_capture_max_age_seconds
        
        super().__init__(max_entries=max_entries)
        self.max_age_seconds = max_age_seconds
        self.cleanup_task: Optional[asyncio.Task] = None
        self.session_start_time = time.time()
        self.memory_usage_samples = deque(maxlen=100)  # Keep last 100 memory samples
        self.last_cleanup_time = time.time()
        
        # Convert list to deque for efficient operations
        if isinstance(self.entries, list):
            self.entries = deque(self.entries, maxlen=max_entries)
        
        # Start periodic cleanup task
        try:
            loop = asyncio.get_running_loop()
            self.cleanup_task = loop.create_task(self.periodic_cleanup())
        except RuntimeError:
            # No event loop running yet, cleanup task will be started later
            pass
        
        # Get logger after module initialization to avoid circular reference
        _logger = get_logger("enhanced_log_capture")
        _logger.debug("EnhancedLogCapture initialized",
                     max_entries=max_entries,
                     max_age_seconds=max_age_seconds)

    async def periodic_cleanup(self) -> None:
        """
        Periodic cleanup task that removes old entries and monitors memory usage.
        Runs every 5 minutes as specified in PRD.
        """
        while True:
            try:
                await asyncio.sleep(settings.enhanced_log_capture_cleanup_interval)
                await self._perform_cleanup()
            except asyncio.CancelledError:
                get_logger("enhanced_log_capture").debug("Enhanced log capture cleanup task cancelled")
                break
            except Exception as e:
                get_logger("enhanced_log_capture").error("Error in periodic log cleanup", error=str(e))
    
    async def _perform_cleanup(self) -> None:
        """Perform age-based and memory cleanup."""
        current_time = time.time()
        cutoff_time = datetime.now(UTC) - timedelta(seconds=self.max_age_seconds)
        
        # Age-based cleanup
        initial_count = len(self.entries)
        
        # Remove entries older than max_age_seconds
        while self.entries:
            # Get the oldest entry
            oldest_entry = self.entries[0]
            entry_time_str = oldest_entry.get('timestamp')
            
            if entry_time_str:
                try:
                    # Parse ISO timestamp
                    if entry_time_str.endswith('Z'):
                        entry_time_str = entry_time_str[:-1] + '+00:00'
                    entry_time = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
                    
                    if entry_time < cutoff_time:
                        self.entries.popleft()
                    else:
                        break
                except (ValueError, TypeError):
                    # If timestamp parsing fails, remove the entry as it's malformed
                    self.entries.popleft()
            else:
                # Entry without timestamp, assume it's old and remove
                self.entries.popleft()
        
        # Memory usage monitoring
        try:
            import psutil
            current_process = psutil.Process()
            memory_mb = current_process.memory_info().rss / 1024 / 1024
            self.memory_usage_samples.append({
                'timestamp': current_time,
                'memory_mb': memory_mb
            })
        except ImportError:
            # psutil not available, skip memory monitoring
            pass
        
        # Log cleanup statistics
        cleaned_count = initial_count - len(self.entries)
        if cleaned_count > 0:
            get_logger("enhanced_log_capture").debug("Performed age-based log cleanup",
                                                   entries_removed=cleaned_count,
                                                   remaining_entries=len(self.entries),
                                                   max_age_seconds=self.max_age_seconds)
        
        self.last_cleanup_time = current_time
    
    def add_entry(self, entry: Dict[str, Any]) -> None:
        """Enhanced add_entry with better timestamp handling and deduplication."""
        import hashlib
        
        # Start cleanup task if not running and event loop is available
        if self.cleanup_task is None or self.cleanup_task.done():
            try:
                loop = asyncio.get_running_loop()
                self.cleanup_task = loop.create_task(self.periodic_cleanup())
            except RuntimeError:
                pass
        
        # Skip if not a WebSocket-only entry and we don't have subscribers
        if not entry.get('_websocket_only') and not self.has_subscribers():
            return
        
        # Enhanced deduplication with timestamp awareness
        entry_content = f"{entry.get('event', '')}{entry.get('timestamp', '')}{entry.get('request_id', '')}{entry.get('level', '')}"
        entry_hash = hashlib.md5(entry_content.encode()).hexdigest()
        
        # Check for recent duplicates
        if hasattr(self, '_recent_hashes'):
            if entry_hash in self._recent_hashes:
                return
        else:
            self._recent_hashes = set()
        
        self._recent_hashes.add(entry_hash)
        
        # Clean up old hashes (keep only last 100)
        if len(self._recent_hashes) > 100:
            self._recent_hashes = set(list(self._recent_hashes)[-50:])
        
        # Ensure entry has required fields with enhanced timestamp handling
        if 'timestamp' not in entry:
            entry['timestamp'] = datetime.now(UTC).isoformat()
        if 'level' not in entry:
            entry['level'] = 'info'
        
        # Add session context for tracking
        entry['session_age'] = round(time.time() - self.session_start_time, 2)
        
        # Remove internal flags before storing/broadcasting
        clean_entry = {k: v for k, v in entry.items() if not k.startswith('_')}
        
        # Use deque for efficient operations
        self.entries.append(clean_entry)
        
        # The deque maxlen handles size-based cleanup automatically
        
        # Notify WebSocket subscribers asynchronously
        if self.has_subscribers():
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._notify_subscribers_async(clean_entry))
            except RuntimeError:
                # No event loop running, skip WebSocket broadcast
                pass
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get current memory usage statistics."""
        stats = {
            'entries_count': len(self.entries),
            'max_entries': self.max_entries if hasattr(self, 'max_entries') else getattr(self.entries, 'maxlen', 'unlimited'),
            'max_age_seconds': self.max_age_seconds,
            'session_age_seconds': round(time.time() - self.session_start_time, 2),
            'last_cleanup_age': round(time.time() - self.last_cleanup_time, 2),
            'subscriber_count': len(self._subscribers),
            'hash_cache_size': len(getattr(self, '_recent_hashes', set()))
        }
        
        # Add memory samples if available
        if self.memory_usage_samples:
            latest_sample = self.memory_usage_samples[-1]
            stats['current_memory_mb'] = latest_sample['memory_mb']
            
            # Calculate memory trend if we have multiple samples
            if len(self.memory_usage_samples) > 1:
                first_sample = self.memory_usage_samples[0]
                memory_change = latest_sample['memory_mb'] - first_sample['memory_mb']
                time_span = latest_sample['timestamp'] - first_sample['timestamp']
                stats['memory_trend_mb_per_minute'] = round(memory_change / (time_span / 60), 2) if time_span > 0 else 0
        
        return stats
    
    def get_recent_entries(self, limit: int = 100) -> list[Dict[str, Any]]:
        """Get recent log entries, overridden to work with deque."""
        if limit >= len(self.entries):
            return list(self.entries)
        else:
            # Get the last 'limit' entries from deque
            return list(self.entries)[-limit:]
    
    def cleanup_immediately(self) -> Dict[str, Any]:
        """Force immediate cleanup and return statistics."""
        if self.cleanup_task and not self.cleanup_task.done():
            # Schedule immediate cleanup
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._perform_cleanup())
            except RuntimeError:
                pass
        
        return self.get_memory_stats()
    
    def __del__(self):
        """Cleanup task when object is destroyed."""
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()


# Global log capture instance - replaced with enhanced version for Phase 1
log_capture = EnhancedLogCapture()


# Configure logging on module import
configure_logging()