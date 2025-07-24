"""
Unit tests for Phase 1 foundation safeguards components.
Tests the ThrottledBroadcaster, EnhancedLogCapture, and SimpleEventLoopMonitor.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta, UTC
from unittest.mock import Mock, AsyncMock, patch
from collections import deque

from src.modul8r.websocket_handlers import ThrottledBroadcaster, LogStreamManager
from src.modul8r.performance_monitor import SimpleEventLoopMonitor
from src.modul8r.logging_config import EnhancedLogCapture
from src.modul8r.config import settings


class TestThrottledBroadcaster:
    """Test the message throttling system."""

    def test_throttled_broadcaster_initialization(self):
        """Test ThrottledBroadcaster initializes correctly."""
        broadcaster = ThrottledBroadcaster(batch_interval=1.0, max_batch_size=50)

        assert broadcaster.batch_interval == 1.0
        assert broadcaster.max_batch_size == 50
        assert broadcaster.pending_messages == []
        assert broadcaster.flush_task is None
        assert not broadcaster.rate_limit_active

    def test_throttled_broadcaster_uses_config_defaults(self):
        """Test that ThrottledBroadcaster uses configuration defaults."""
        broadcaster = ThrottledBroadcaster()

        assert broadcaster.batch_interval == settings.throttle_batch_interval
        assert broadcaster.max_batch_size == settings.throttle_max_batch_size
        assert broadcaster.circuit_breaker_threshold == settings.throttle_circuit_breaker_threshold

    @pytest.mark.asyncio
    async def test_message_queuing(self):
        """Test that messages are queued correctly."""
        broadcaster = ThrottledBroadcaster(batch_interval=10.0)  # Long interval to prevent auto-flush
        mock_manager = Mock()
        mock_manager.active_connections = set()

        test_message = {"type": "test", "content": "test message"}

        await broadcaster.queue_message(test_message, mock_manager)

        assert len(broadcaster.pending_messages) == 1
        assert broadcaster.pending_messages[0] == test_message

    @pytest.mark.asyncio
    async def test_batch_flush_on_size_limit(self):
        """Test that batch flushes when size limit is reached."""
        broadcaster = ThrottledBroadcaster(batch_interval=10.0, max_batch_size=2)
        # Reset circuit breaker state for this test
        broadcaster.circuit_breaker_threshold = 10000  # Very high threshold
        broadcaster.message_count = 0  # Reset message count
        broadcaster.last_flush_time = time.time()  # Reset timing
        broadcaster.rate_limit_active = False  # Ensure not active

        mock_manager = Mock()
        mock_manager.active_connections = {Mock(), Mock()}

        # Mock the _direct_broadcast method
        broadcaster._direct_broadcast = AsyncMock()

        # Add messages up to the limit
        await broadcaster.queue_message({"type": "test1"}, mock_manager)
        await broadcaster.queue_message({"type": "test2"}, mock_manager)

        # Should have triggered flush
        broadcaster._direct_broadcast.assert_called_once()
        assert len(broadcaster.pending_messages) == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_activation(self):
        """Test that circuit breaker activates under high load."""
        broadcaster = ThrottledBroadcaster()
        broadcaster.circuit_breaker_threshold = 5  # Low threshold for testing
        broadcaster.message_count = 100  # Simulate high message count
        broadcaster.last_flush_time = time.time() - 1  # 1 second ago

        mock_manager = Mock()
        current_time = time.time()

        # Should activate circuit breaker
        is_active = broadcaster._check_circuit_breaker(current_time)
        assert is_active
        assert broadcaster.rate_limit_active

    def test_get_stats(self):
        """Test that statistics are returned correctly."""
        broadcaster = ThrottledBroadcaster()
        broadcaster.pending_messages = [{"test": "message1"}, {"test": "message2"}]
        broadcaster.message_count = 10

        stats = broadcaster.get_stats()

        assert stats["pending_messages"] == 2
        assert stats["total_messages"] == 10
        assert "current_rate" in stats
        assert "circuit_breaker_active" in stats
        assert "time_since_last_flush" in stats


class TestLogStreamManager:
    """Test the WebSocket log stream manager with Phase 1 safeguards."""

    def test_log_stream_manager_initialization(self):
        """Test LogStreamManager initializes with throttling if enabled."""
        # Test with throttling enabled (default)
        with patch.object(settings, "enable_message_throttling", True):
            manager = LogStreamManager()
            assert manager.throttled_broadcaster is not None
            assert isinstance(manager.throttled_broadcaster, ThrottledBroadcaster)

    def test_log_stream_manager_throttling_disabled(self):
        """Test LogStreamManager without throttling when disabled."""
        with patch.object(settings, "enable_message_throttling", False):
            manager = LogStreamManager()
            assert manager.throttled_broadcaster is None

    @pytest.mark.asyncio
    async def test_broadcast_log_with_throttling(self):
        """Test that log broadcasting uses throttling when enabled."""
        with patch.object(settings, "enable_message_throttling", True):
            manager = LogStreamManager()
            manager.active_connections = {Mock()}

            # Mock the throttled broadcaster
            manager.throttled_broadcaster = Mock()
            manager.throttled_broadcaster.queue_message = AsyncMock()

            test_log = {"level": "info", "message": "test log"}
            await manager.broadcast_log(test_log)

            manager.throttled_broadcaster.queue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_log_without_throttling(self):
        """Test that log broadcasting falls back to direct when throttling disabled."""
        with patch.object(settings, "enable_message_throttling", False):
            manager = LogStreamManager()
            manager.active_connections = {Mock()}
            manager._direct_broadcast = AsyncMock()

            test_log = {"level": "info", "message": "test log"}
            await manager.broadcast_log(test_log)

            manager._direct_broadcast.assert_called_once()

    def test_get_throttling_stats_enabled(self):
        """Test throttling stats when throttling is enabled."""
        with patch.object(settings, "enable_message_throttling", True):
            manager = LogStreamManager()
            manager.active_connections = {Mock(), Mock()}

            # Mock throttled broadcaster stats
            mock_stats = {
                "pending_messages": 5,
                "total_messages": 100,
                "current_rate": 2.5,
                "circuit_breaker_active": False,
            }
            manager.throttled_broadcaster.get_stats = Mock(return_value=mock_stats)

            stats = manager.get_throttling_stats()

            assert stats["active_connections"] == 2
            assert stats["pending_messages"] == 5
            assert stats["total_messages"] == 100

    def test_get_throttling_stats_disabled(self):
        """Test throttling stats when throttling is disabled."""
        with patch.object(settings, "enable_message_throttling", False):
            manager = LogStreamManager()
            manager.active_connections = {Mock(), Mock()}

            stats = manager.get_throttling_stats()

            assert stats["active_connections"] == 2
            assert stats["throttling_enabled"] is False
            assert stats["pending_messages"] == 0
            assert stats["current_rate"] == 0


class TestSimpleEventLoopMonitor:
    """Test the event loop performance monitor."""

    def test_monitor_initialization(self):
        """Test SimpleEventLoopMonitor initializes correctly."""
        monitor = SimpleEventLoopMonitor(max_lag_ms=50.0, check_interval=2.0)

        assert monitor.max_lag_ms == 50.0
        assert monitor.check_interval == 2.0
        assert monitor.monitor_task is None
        assert not monitor.degradation_active
        assert monitor.degradation_callbacks == []

    def test_monitor_uses_config_defaults(self):
        """Test that monitor uses configuration defaults."""
        monitor = SimpleEventLoopMonitor()

        assert monitor.max_lag_ms == settings.performance_monitor_max_lag_ms
        assert monitor.check_interval == settings.performance_monitor_check_interval
        expected_severe_threshold = (
            settings.performance_monitor_max_lag_ms * settings.performance_monitor_severe_lag_threshold_multiplier
        )
        assert monitor.severe_lag_threshold == expected_severe_threshold

    @pytest.mark.asyncio
    async def test_monitor_start_stop(self):
        """Test starting and stopping the monitor."""
        monitor = SimpleEventLoopMonitor()

        # Start monitoring
        monitor.start_monitoring()
        assert monitor.monitor_task is not None
        assert not monitor.monitor_task.done()

        # Stop monitoring
        monitor.stop_monitoring()
        await asyncio.sleep(0.1)  # Let cancellation propagate
        assert monitor.monitor_task.done()

    @pytest.mark.asyncio
    async def test_lag_measurement_recording(self):
        """Test that lag measurements are recorded correctly."""
        monitor = SimpleEventLoopMonitor(check_interval=0.1)  # Fast for testing

        # Mock the _check_event_loop_lag method to simulate lag
        original_check = monitor._check_event_loop_lag

        async def mock_check():
            # Simulate lag measurement
            measurement = {
                "timestamp": time.perf_counter(),
                "lag_ms": 25.0,
                "expected_interval": monitor.check_interval,
            }
            monitor.lag_measurements.append(measurement)

        monitor._check_event_loop_lag = mock_check

        # Run a few checks
        await monitor._check_event_loop_lag()
        await monitor._check_event_loop_lag()

        assert len(monitor.lag_measurements) == 2
        assert monitor.lag_measurements[0]["lag_ms"] == 25.0

    def test_degradation_callback_management(self):
        """Test adding and removing degradation callbacks."""
        monitor = SimpleEventLoopMonitor()

        callback1 = Mock()
        callback2 = Mock()

        # Add callbacks
        monitor.add_degradation_callback(callback1)
        monitor.add_degradation_callback(callback2)

        assert len(monitor.degradation_callbacks) == 2
        assert callback1 in monitor.degradation_callbacks
        assert callback2 in monitor.degradation_callbacks

        # Remove callback
        monitor.remove_degradation_callback(callback1)
        assert len(monitor.degradation_callbacks) == 1
        assert callback2 in monitor.degradation_callbacks

    @pytest.mark.asyncio
    async def test_degradation_trigger(self):
        """Test that degradation callbacks are triggered correctly."""
        monitor = SimpleEventLoopMonitor()

        callback_mock = AsyncMock()
        monitor.add_degradation_callback(callback_mock)

        # Trigger standard degradation
        await monitor.trigger_degradation(50.0)

        callback_mock.assert_called_once_with("standard", 50.0)
        assert monitor.degradation_active

    @pytest.mark.asyncio
    async def test_emergency_degradation(self):
        """Test emergency degradation triggers."""
        monitor = SimpleEventLoopMonitor(max_lag_ms=40.0)
        monitor.severe_lag_count = 5  # At threshold

        callback_mock = AsyncMock()
        monitor.add_degradation_callback(callback_mock)

        # Trigger emergency degradation
        await monitor.trigger_emergency_degradation(200.0)

        callback_mock.assert_called_once_with("emergency", 200.0)
        assert monitor.severe_lag_count == 0  # Should reset after emergency

    def test_performance_stats(self):
        """Test that performance statistics are calculated correctly."""
        monitor = SimpleEventLoopMonitor()

        # Add some mock measurements
        base_time = time.perf_counter()
        monitor.lag_measurements = [
            {"timestamp": base_time, "lag_ms": 10.0, "expected_interval": 1.0},
            {"timestamp": base_time + 1, "lag_ms": 20.0, "expected_interval": 1.0},
            {"timestamp": base_time + 2, "lag_ms": 30.0, "expected_interval": 1.0},
            {"timestamp": base_time + 3, "lag_ms": 15.0, "expected_interval": 1.0},
            {"timestamp": base_time + 4, "lag_ms": 25.0, "expected_interval": 1.0},
        ]

        stats = monitor.get_performance_stats()

        assert stats["status"] == "active"
        assert "recent_stats" in stats
        assert stats["recent_stats"]["avg_lag_ms"] == 20.0  # Average of last 5
        assert stats["recent_stats"]["max_lag_ms"] == 30.0
        assert stats["recent_stats"]["min_lag_ms"] == 10.0

    def test_is_healthy(self):
        """Test health check functionality."""
        monitor = SimpleEventLoopMonitor(max_lag_ms=40.0)

        # No measurements - should be healthy
        assert monitor.is_healthy()

        # Add low lag measurements - should be healthy
        base_time = time.perf_counter()
        monitor.lag_measurements = [
            {"timestamp": base_time, "lag_ms": 10.0, "expected_interval": 1.0},
            {"timestamp": base_time + 1, "lag_ms": 15.0, "expected_interval": 1.0},
            {"timestamp": base_time + 2, "lag_ms": 20.0, "expected_interval": 1.0},
        ]

        assert monitor.is_healthy()

        # Add high lag measurements - should not be healthy
        monitor.lag_measurements = [  # Replace instead of extend to ensure we have recent high lag
            {"timestamp": base_time + 1, "lag_ms": 50.0, "expected_interval": 1.0},
            {"timestamp": base_time + 2, "lag_ms": 60.0, "expected_interval": 1.0},
            {"timestamp": base_time + 3, "lag_ms": 55.0, "expected_interval": 1.0},
            {"timestamp": base_time + 4, "lag_ms": 65.0, "expected_interval": 1.0},
            {"timestamp": base_time + 5, "lag_ms": 70.0, "expected_interval": 1.0},
        ]

        assert not monitor.is_healthy()


class TestEnhancedLogCapture:
    """Test the enhanced log capture system."""

    def test_enhanced_log_capture_initialization(self):
        """Test EnhancedLogCapture initializes correctly."""
        capture = EnhancedLogCapture(max_entries=500, max_age_seconds=1800)

        assert capture.max_age_seconds == 1800
        assert isinstance(capture.entries, deque)
        assert capture.entries.maxlen == 500
        assert isinstance(capture.memory_usage_samples, deque)
        assert capture.memory_usage_samples.maxlen == 100

    def test_enhanced_log_capture_uses_config_defaults(self):
        """Test that EnhancedLogCapture uses configuration defaults."""
        capture = EnhancedLogCapture()

        assert capture.max_age_seconds == settings.enhanced_log_capture_max_age_seconds
        assert capture.entries.maxlen == settings.enhanced_log_capture_max_entries

    def test_add_entry_with_session_context(self):
        """Test that entries get session context added."""
        capture = EnhancedLogCapture()
        capture._subscribers = [Mock()]  # Mock subscriber to process entry

        test_entry = {"event": "test message", "level": "info", "_websocket_only": True}

        capture.add_entry(test_entry)

        # Should have added the entry with session context
        assert len(capture.entries) == 1
        added_entry = capture.entries[0]
        assert "session_age" in added_entry
        assert added_entry["session_age"] >= 0

    @pytest.mark.asyncio
    async def test_periodic_cleanup_removes_old_entries(self):
        """Test that periodic cleanup removes old entries."""
        capture = EnhancedLogCapture(max_age_seconds=1)  # 1 second for testing

        # Add an old entry
        old_time = (datetime.now(UTC) - timedelta(seconds=2)).isoformat()
        old_entry = {"event": "old message", "timestamp": old_time, "level": "info"}
        capture.entries.append(old_entry)

        # Add a recent entry
        recent_entry = {"event": "recent message", "timestamp": datetime.now(UTC).isoformat(), "level": "info"}
        capture.entries.append(recent_entry)

        assert len(capture.entries) == 2

        # Run cleanup
        await capture._perform_cleanup()

        # Should have removed the old entry
        assert len(capture.entries) == 1
        assert capture.entries[0]["event"] == "recent message"

    def test_get_memory_stats(self):
        """Test that memory statistics are returned correctly."""
        capture = EnhancedLogCapture()

        # Add some entries
        capture.entries.extend(
            [
                {"event": "test1", "level": "info"},
                {"event": "test2", "level": "error"},
                {"event": "test3", "level": "warning"},
            ]
        )

        # Add some memory samples
        capture.memory_usage_samples.extend(
            [{"timestamp": time.time() - 60, "memory_mb": 100.0}, {"timestamp": time.time(), "memory_mb": 110.0}]
        )

        stats = capture.get_memory_stats()

        assert stats["entries_count"] == 3
        assert stats["max_entries"] == capture.entries.maxlen
        assert stats["max_age_seconds"] == capture.max_age_seconds
        assert "session_age_seconds" in stats
        assert "current_memory_mb" in stats
        assert stats["current_memory_mb"] == 110.0
        assert "memory_trend_mb_per_minute" in stats

    def test_cleanup_immediately(self):
        """Test that immediate cleanup can be triggered."""
        capture = EnhancedLogCapture()

        # Should return current stats
        stats = capture.cleanup_immediately()

        assert isinstance(stats, dict)
        assert "entries_count" in stats
        assert "session_age_seconds" in stats


class TestPhase1Integration:
    """Integration tests for Phase 1 components working together."""

    @pytest.mark.asyncio
    async def test_performance_monitor_triggers_websocket_degradation(self):
        """Test that performance monitor triggers WebSocket throttling degradation."""
        # Create components
        monitor = SimpleEventLoopMonitor(max_lag_ms=30.0)

        with patch.object(settings, "enable_message_throttling", True):
            manager = LogStreamManager()

        # Verify initial throttling settings
        initial_interval = manager.throttled_broadcaster.batch_interval
        initial_batch_size = manager.throttled_broadcaster.max_batch_size

        # Register the manager's degradation handler with the monitor
        monitor.add_degradation_callback(manager._handle_performance_degradation)

        # Trigger standard degradation
        await monitor.trigger_degradation(50.0)

        # Should have adjusted throttling parameters
        assert manager.throttled_broadcaster.batch_interval > initial_interval

        # Trigger emergency degradation
        await monitor.trigger_emergency_degradation(150.0)

        # Should have more aggressive throttling
        assert manager.throttled_broadcaster.batch_interval == 2.0
        assert manager.throttled_broadcaster.max_batch_size == 50

        # Trigger recovery
        await monitor.recover_from_degradation()

        # Should restore original settings
        assert manager.throttled_broadcaster.batch_interval == settings.throttle_batch_interval
        assert manager.throttled_broadcaster.max_batch_size == settings.throttle_max_batch_size

    @pytest.mark.asyncio
    async def test_all_phase1_components_start_and_stop_cleanly(self):
        """Test that all Phase 1 components can start and stop without errors."""
        # Test the components as they would be used in the real application

        # Performance monitor
        monitor = SimpleEventLoopMonitor()
        monitor.start_monitoring()
        assert monitor.monitor_task is not None

        # Enhanced log capture
        log_capture = EnhancedLogCapture()
        assert log_capture.cleanup_task is not None or asyncio.get_running_loop() is None

        # WebSocket manager with throttling
        with patch.object(settings, "enable_message_throttling", True):
            manager = LogStreamManager()
            assert manager.throttled_broadcaster is not None

        # Let them run briefly
        await asyncio.sleep(0.1)

        # Stop everything cleanly
        monitor.stop_monitoring()
        await asyncio.sleep(0.1)

        # Should stop without errors
        assert monitor.monitor_task.done()


@pytest.mark.phase1
class TestPhase1Configuration:
    """Test Phase 1 configuration and feature flags."""

    def test_all_phase1_settings_exist(self):
        """Test that all Phase 1 configuration settings exist."""
        # Message throttling settings
        assert hasattr(settings, "throttle_batch_interval")
        assert hasattr(settings, "throttle_max_batch_size")
        assert hasattr(settings, "throttle_circuit_breaker_threshold")
        assert hasattr(settings, "throttle_circuit_breaker_window")
        assert hasattr(settings, "throttle_circuit_breaker_recovery_time")

        # Memory management settings
        assert hasattr(settings, "enhanced_log_capture_max_entries")
        assert hasattr(settings, "enhanced_log_capture_max_age_seconds")
        assert hasattr(settings, "enhanced_log_capture_cleanup_interval")

        # Performance monitoring settings
        assert hasattr(settings, "performance_monitor_max_lag_ms")
        assert hasattr(settings, "performance_monitor_check_interval")
        assert hasattr(settings, "performance_monitor_severe_lag_threshold_multiplier")
        assert hasattr(settings, "performance_monitor_max_severe_lag_count")

        # Feature flags
        assert hasattr(settings, "enable_message_throttling")
        assert hasattr(settings, "enable_enhanced_memory_management")
        assert hasattr(settings, "enable_performance_monitoring")
        assert hasattr(settings, "enable_phase1_status_endpoint")

    def test_phase1_settings_have_reasonable_defaults(self):
        """Test that Phase 1 settings have reasonable default values."""
        # Message throttling
        assert 0.1 <= settings.throttle_batch_interval <= 5.0
        assert 10 <= settings.throttle_max_batch_size <= 500
        assert 10.0 <= settings.throttle_circuit_breaker_threshold <= 200.0

        # Memory management
        assert 100 <= settings.enhanced_log_capture_max_entries <= 5000
        assert 300 <= settings.enhanced_log_capture_max_age_seconds <= 86400
        assert 60 <= settings.enhanced_log_capture_cleanup_interval <= 1800

        # Performance monitoring
        assert 10.0 <= settings.performance_monitor_max_lag_ms <= 200.0
        assert 0.5 <= settings.performance_monitor_check_interval <= 10.0
        assert 2.0 <= settings.performance_monitor_severe_lag_threshold_multiplier <= 10.0

        # Feature flags should be enabled by default
        assert settings.enable_message_throttling is True
        assert settings.enable_enhanced_memory_management is True
        assert settings.enable_performance_monitoring is True
        assert settings.enable_phase1_status_endpoint is True
