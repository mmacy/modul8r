import asyncio
import json
import time
from datetime import datetime, UTC
from typing import Set, Dict, Any, List, Optional
from fastapi import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from .logging_config import get_logger, log_capture
from .performance_monitor import event_loop_monitor
from .config import settings

logger = get_logger("websocket")


class ThrottledBroadcaster:
    """
    Batches WebSocket messages to prevent connection overflow and maintain
    performance during high-volume message scenarios.

    Features:
    - Timer-based batching with configurable intervals
    - Immediate flush when batch size limit reached
    - Circuit breaker functionality for high-volume scenarios
    - Maintains <10 msg/sec average as per PRD requirements
    """

    def __init__(self, batch_interval: Optional[float] = None, max_batch_size: Optional[int] = None):
        # Use configuration settings with fallbacks
        self.batch_interval = batch_interval or settings.throttle_batch_interval
        self.max_batch_size = max_batch_size or settings.throttle_max_batch_size
        self.pending_messages: List[Dict[str, Any]] = []
        self.flush_task: Optional[asyncio.Task] = None
        self.last_flush_time = time.time()
        self.message_count = 0
        self.rate_limit_active = False

        # Circuit breaker thresholds from configuration
        self.circuit_breaker_threshold = settings.throttle_circuit_breaker_threshold
        self.circuit_breaker_window = settings.throttle_circuit_breaker_window
        self.circuit_breaker_recovery_time = settings.throttle_circuit_breaker_recovery_time

        logger.debug("ThrottledBroadcaster initialized", batch_interval=batch_interval, max_batch_size=max_batch_size)

    async def queue_message(self, message: Dict[str, Any], websocket_manager) -> None:
        """Queue a message for batched broadcast."""
        current_time = time.time()

        # Circuit breaker check
        if self._check_circuit_breaker(current_time):
            logger.warning("Circuit breaker active, dropping message")
            return

        # Add message to pending queue
        self.pending_messages.append(message)
        self.message_count += 1

        # Start timer-based flush if not already running
        if self.flush_task is None or self.flush_task.done():
            self.flush_task = asyncio.create_task(self._timer_flush(websocket_manager))

        # Immediate flush if batch is full
        if len(self.pending_messages) >= self.max_batch_size:
            await self.flush_batch(websocket_manager)

    async def _timer_flush(self, websocket_manager) -> None:
        """Ensure messages are flushed even during low activity periods."""
        try:
            await asyncio.sleep(self.batch_interval)
            await self.flush_batch(websocket_manager)
        except asyncio.CancelledError:
            # Task was cancelled, which is normal when immediate flush occurs
            pass
        except Exception as e:
            logger.error("Error in timer flush", error=str(e))

    async def flush_batch(self, websocket_manager) -> None:
        """Flush pending messages as a batch."""
        if not self.pending_messages:
            return

        # Cancel timer task since we're flushing now
        if self.flush_task and not self.flush_task.done():
            self.flush_task.cancel()

        try:
            # Create batched message
            batched_message = {
                "type": "batch_update",
                "messages": self.pending_messages.copy(),
                "timestamp": datetime.now(UTC).isoformat(),
                "batch_size": len(self.pending_messages),
            }

            # Broadcast batch to all connected clients
            await self._direct_broadcast(batched_message, websocket_manager)

            logger.debug(
                "Flushed message batch", batch_size=len(self.pending_messages), total_messages=self.message_count
            )

            # Clear pending messages
            self.pending_messages.clear()
            self.last_flush_time = time.time()

        except Exception as e:
            logger.error("Error flushing message batch", error=str(e))
        finally:
            self.flush_task = None

    async def _direct_broadcast(self, message: Dict[str, Any], websocket_manager) -> None:
        """Direct broadcast bypassing additional batching."""
        if not websocket_manager.active_connections:
            return

        disconnected_clients = set()

        for websocket in list(websocket_manager.active_connections):
            try:
                await websocket.send_json(message)
            except (WebSocketDisconnect, ConnectionClosed, RuntimeError):
                disconnected_clients.add(websocket)
            except Exception as e:
                logger.error(
                    "Error broadcasting batch to client",
                    client_id=websocket_manager.connection_info.get(websocket, {}).get("client_id", "unknown"),
                    error=str(e),
                )
                disconnected_clients.add(websocket)

        # Clean up disconnected clients
        for websocket in disconnected_clients:
            await websocket_manager.disconnect(websocket)

    def _check_circuit_breaker(self, current_time: float) -> bool:
        """Check if circuit breaker should be active."""
        time_window = current_time - self.circuit_breaker_window

        # Reset rate limit if enough time has passed
        if self.rate_limit_active and (current_time - self.last_flush_time) > self.circuit_breaker_recovery_time:
            self.rate_limit_active = False
            self.message_count = 0
            logger.info("Circuit breaker recovered")

        # Check if message rate exceeds threshold
        if not self.rate_limit_active:
            rate = self.message_count / min(current_time - self.last_flush_time or 1, self.circuit_breaker_window)
            if rate > self.circuit_breaker_threshold:
                self.rate_limit_active = True
                logger.warning("Circuit breaker activated", message_rate=rate, threshold=self.circuit_breaker_threshold)

        return self.rate_limit_active

    def get_stats(self) -> Dict[str, Any]:
        """Get current throttling statistics."""
        current_time = time.time()
        time_since_flush = current_time - self.last_flush_time
        current_rate = self.message_count / max(time_since_flush, 1.0)

        return {
            "pending_messages": len(self.pending_messages),
            "total_messages": self.message_count,
            "current_rate": round(current_rate, 2),
            "circuit_breaker_active": self.rate_limit_active,
            "time_since_last_flush": round(time_since_flush, 2),
        }


class LogStreamManager:
    """Manages WebSocket connections for real-time log streaming."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.connection_info: Dict[WebSocket, Dict[str, Any]] = {}

        # Initialize throttled broadcaster for Phase 1 safeguards (if enabled)
        if settings.enable_message_throttling:
            self.throttled_broadcaster = ThrottledBroadcaster()
            logger.info(
                "Message throttling enabled",
                batch_interval=settings.throttle_batch_interval,
                max_batch_size=settings.throttle_max_batch_size,
            )
        else:
            self.throttled_broadcaster = None
            logger.info("Message throttling disabled")

        # Register performance degradation callback (if performance monitoring enabled)
        if settings.enable_performance_monitoring:
            event_loop_monitor.add_degradation_callback(self._handle_performance_degradation)
            logger.info("Performance monitoring integration enabled")

    async def connect(self, websocket: WebSocket, client_id: str = None):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)

        self.connection_info[websocket] = {
            "client_id": client_id or f"client_{id(websocket)}",
            "connected_at": asyncio.get_event_loop().time(),
        }

        # Add to log capture subscribers
        log_capture.add_subscriber(websocket)

        logger.info(
            "WebSocket client connected",
            client_id=self.connection_info[websocket]["client_id"],
            total_connections=len(self.active_connections),
        )

        # Send recent log entries to new client
        recent_logs = log_capture.get_recent_entries(limit=50)
        if recent_logs:
            try:
                await websocket.send_json({"type": "log_history", "logs": recent_logs})
            except Exception as e:
                logger.error("Failed to send log history to new client", error=str(e))

    async def disconnect(self, websocket: WebSocket):
        """Handle client disconnection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            client_info = self.connection_info.pop(websocket, {})

            # Remove from log capture subscribers
            log_capture.remove_subscriber(websocket)

            logger.info(
                "WebSocket client disconnected",
                client_id=client_info.get("client_id", "unknown"),
                total_connections=len(self.active_connections),
            )

    async def broadcast_log(self, log_entry: Dict[str, Any]):
        """Broadcast a log entry to all connected clients using throttled broadcasting."""
        if not self.active_connections:
            return

        message = {"type": "log_entry", "log": log_entry}

        # Use throttled broadcaster if enabled, otherwise direct broadcast
        if self.throttled_broadcaster and settings.enable_message_throttling:
            await self.throttled_broadcaster.queue_message(message, self)
        else:
            await self._direct_broadcast(message)

    async def broadcast_log_immediate(self, log_entry: Dict[str, Any]):
        """Broadcast a log entry immediately (bypass throttling for critical messages)."""
        if not self.active_connections:
            return

        message = {"type": "log_entry", "log": log_entry}

        await self._direct_broadcast(message)

    async def _direct_broadcast(self, message: Dict[str, Any]):
        """Direct broadcast without throttling (for immediate/critical messages)."""
        disconnected_clients = set()

        for websocket in list(self.active_connections):
            try:
                await websocket.send_json(message)
            except (WebSocketDisconnect, ConnectionClosed, RuntimeError) as e:
                logger.warning(
                    "Client disconnected during broadcast",
                    client_id=self.connection_info.get(websocket, {}).get("client_id", "unknown"),
                    error=str(e),
                )
                disconnected_clients.add(websocket)
            except Exception as e:
                logger.error(
                    "Error broadcasting to client",
                    client_id=self.connection_info.get(websocket, {}).get("client_id", "unknown"),
                    error=str(e),
                )
                disconnected_clients.add(websocket)

        # Clean up disconnected clients
        for websocket in disconnected_clients:
            await self.disconnect(websocket)

    async def send_status_update(self, status: Dict[str, Any]):
        """Send processing status update to all connected clients using throttled broadcasting."""
        if not self.active_connections:
            return

        message = {"type": "status_update", "status": status}

        # Use throttled broadcaster if enabled, otherwise direct broadcast
        if self.throttled_broadcaster and settings.enable_message_throttling:
            await self.throttled_broadcaster.queue_message(message, self)
        else:
            await self._direct_broadcast(message)

    async def send_status_update_immediate(self, status: Dict[str, Any]):
        """Send processing status update immediately (bypass throttling for critical updates)."""
        if not self.active_connections:
            return

        message = {"type": "status_update", "status": status}

        await self._direct_broadcast(message)

    def get_connection_count(self) -> int:
        """Get the current number of active connections."""
        return len(self.active_connections)

    def get_throttling_stats(self) -> Dict[str, Any]:
        """Get current message throttling statistics for monitoring."""
        base_stats = {"active_connections": len(self.active_connections)}

        if self.throttled_broadcaster and settings.enable_message_throttling:
            stats = self.throttled_broadcaster.get_stats()
            stats.update(base_stats)
            return stats
        else:
            return {
                **base_stats,
                "throttling_enabled": False,
                "pending_messages": 0,
                "total_messages": 0,
                "current_rate": 0,
                "circuit_breaker_active": False,
            }

    async def flush_pending_messages(self) -> None:
        """Manually flush any pending throttled messages."""
        if self.throttled_broadcaster and settings.enable_message_throttling:
            await self.throttled_broadcaster.flush_batch(self)

    async def _handle_performance_degradation(self, level: str, lag_ms: float) -> None:
        """
        Handle performance degradation events from event loop monitor.
        Adjusts WebSocket broadcasting behavior based on performance conditions.
        """
        if not self.throttled_broadcaster or not settings.enable_message_throttling:
            # If throttling is disabled, only log the performance issue
            logger.warning(
                "Performance degradation detected but throttling disabled", level=level, lag_ms=round(lag_ms, 2)
            )
            return

        if level == "standard":
            # Increase batching interval to reduce message frequency
            old_interval = self.throttled_broadcaster.batch_interval
            self.throttled_broadcaster.batch_interval = min(2.0, old_interval * 1.5)

            logger.warning(
                "Applied standard performance degradation",
                old_batch_interval=old_interval,
                new_batch_interval=self.throttled_broadcaster.batch_interval,
                lag_ms=round(lag_ms, 2),
            )

        elif level == "emergency":
            # More aggressive throttling for emergency conditions
            self.throttled_broadcaster.batch_interval = 2.0  # 2 second batching
            self.throttled_broadcaster.max_batch_size = 50  # Smaller batches

            logger.error(
                "Applied emergency performance degradation",
                batch_interval=2.0,
                max_batch_size=50,
                lag_ms=round(lag_ms, 2),
            )

            # Send immediate status update to clients about degraded performance
            await self.send_status_update_immediate(
                {"performance_mode": "degraded", "reason": "high_system_load", "lag_ms": round(lag_ms, 2)}
            )

        elif level == "recovery":
            # Restore normal performance parameters from configuration
            self.throttled_broadcaster.batch_interval = settings.throttle_batch_interval
            self.throttled_broadcaster.max_batch_size = settings.throttle_max_batch_size

            logger.info(
                "Recovered from performance degradation",
                batch_interval=settings.throttle_batch_interval,
                max_batch_size=settings.throttle_max_batch_size,
            )

            # Send recovery status to clients
            await self.send_status_update_immediate({"performance_mode": "normal", "reason": "system_load_recovered"})

    def get_performance_integrated_stats(self) -> Dict[str, Any]:
        """Get combined WebSocket and performance monitoring statistics."""
        websocket_stats = self.get_throttling_stats()
        performance_stats = event_loop_monitor.get_performance_stats()

        return {
            "websocket": websocket_stats,
            "event_loop": performance_stats,
            "integrated_health": event_loop_monitor.is_healthy() and not self.throttled_broadcaster.rate_limit_active,
        }


# Global log stream manager instance
log_stream_manager = LogStreamManager()


# Enhanced log capture to work with WebSocket broadcasting
class WebSocketLogCapture:
    """Enhanced log capture that broadcasts to WebSocket clients."""

    def __init__(self):
        # Don't override the original method, just enhance the log_capture instance
        self._original_add_entry = getattr(log_capture, "add_entry", None)
        if self._original_add_entry:
            # Store reference but don't override to avoid duplication
            log_capture._websocket_manager = log_stream_manager


# Initialize the enhanced log capture on module import
websocket_log_capture = WebSocketLogCapture()
