"""
Performance monitoring system for Phase 1 foundation safeguards.
Provides lightweight event loop monitoring and automatic degradation triggers.
"""

import asyncio
import time
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from .logging_config import get_logger
from .config import settings

logger = get_logger("performance_monitor")


class SimpleEventLoopMonitor:
    """
    Lightweight event loop performance monitor for Phase 1 safeguards.
    
    Features:
    - Event loop lag detection with configurable threshold
    - Automatic degradation triggers during high load
    - Periodic monitoring with single background task
    - Integration with existing structured logging
    - <20ms lag detection as per PRD requirements
    """
    
    def __init__(self, max_lag_ms: Optional[float] = None, check_interval: Optional[float] = None):
        # Use configuration settings with fallbacks
        self.max_lag_ms = max_lag_ms or settings.performance_monitor_max_lag_ms
        self.check_interval = check_interval or settings.performance_monitor_check_interval
        self.last_check = time.perf_counter()
        self.monitor_task: Optional[asyncio.Task] = None
        
        # Performance metrics
        self.lag_measurements = []
        self.max_measurements = 100  # Keep last 100 measurements
        self.degradation_active = False
        self.degradation_callbacks = []
        
        # Circuit breaker for severe lag - use configuration settings
        self.severe_lag_threshold = self.max_lag_ms * settings.performance_monitor_severe_lag_threshold_multiplier
        self.severe_lag_count = 0
        self.max_severe_lag_count = settings.performance_monitor_max_severe_lag_count
        
        logger.debug("SimpleEventLoopMonitor initialized",
                    max_lag_ms=max_lag_ms,
                    check_interval=check_interval)
    
    def start_monitoring(self) -> None:
        """Start the background monitoring task."""
        if self.monitor_task is None or self.monitor_task.done():
            try:
                loop = asyncio.get_running_loop()
                self.monitor_task = loop.create_task(self.periodic_check())
                logger.info("Event loop monitoring started")
            except RuntimeError:
                logger.warning("Cannot start event loop monitor - no running event loop")
    
    def stop_monitoring(self) -> None:
        """Stop the background monitoring task."""
        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            logger.info("Event loop monitoring stopped")
    
    async def periodic_check(self) -> None:
        """
        Lightweight periodic event loop lag detection.
        Runs every second by default as specified in PRD.
        """
        self.last_check = time.perf_counter()
        
        while True:
            try:
                await asyncio.sleep(self.check_interval)
                await self._check_event_loop_lag()
            except asyncio.CancelledError:
                logger.debug("Event loop monitor task cancelled")
                break
            except Exception as e:
                logger.error("Error in event loop monitoring", error=str(e))
    
    async def _check_event_loop_lag(self) -> None:
        """Check for event loop lag and trigger degradation if needed."""
        current_time = time.perf_counter()
        expected_time = self.last_check + self.check_interval
        lag_seconds = current_time - expected_time
        lag_ms = lag_seconds * 1000
        
        # Record measurement
        measurement = {
            'timestamp': current_time,
            'lag_ms': lag_ms,
            'expected_interval': self.check_interval
        }
        
        self.lag_measurements.append(measurement)
        if len(self.lag_measurements) > self.max_measurements:
            self.lag_measurements.pop(0)
        
        # Check for lag threshold violation
        if lag_ms > self.max_lag_ms:
            logger.warning("Event loop lag detected",
                          lag_ms=round(lag_ms, 2),
                          threshold_ms=self.max_lag_ms)
            
            # Check for severe lag
            if lag_ms > self.severe_lag_threshold:
                self.severe_lag_count += 1
                logger.error("Severe event loop lag detected",
                           lag_ms=round(lag_ms, 2),
                           severe_lag_count=self.severe_lag_count,
                           threshold_ms=self.severe_lag_threshold)
                
                # Trigger emergency degradation
                if self.severe_lag_count >= self.max_severe_lag_count:
                    await self.trigger_emergency_degradation(lag_ms)
            else:
                # Normal lag - trigger standard degradation
                await self.trigger_degradation(lag_ms)
        else:
            # No lag - reset severe lag counter and degradation if active
            if self.severe_lag_count > 0:
                self.severe_lag_count = max(0, self.severe_lag_count - 1)
            
            if self.degradation_active and lag_ms < self.max_lag_ms / 2:
                await self.recover_from_degradation()
        
        self.last_check = current_time
    
    async def trigger_degradation(self, lag_ms: float) -> None:
        """
        Simple load reduction strategy for normal lag conditions.
        As specified in PRD - increase batching interval and reduce non-essential messages.
        """
        if not self.degradation_active:
            self.degradation_active = True
            logger.warning("Triggering performance degradation",
                          lag_ms=round(lag_ms, 2),
                          degradation_level="standard")
            
            # Execute degradation callbacks
            for callback in self.degradation_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback("standard", lag_ms)
                    else:
                        callback("standard", lag_ms)
                except Exception as e:
                    logger.error("Error executing degradation callback", error=str(e))
    
    async def trigger_emergency_degradation(self, lag_ms: float) -> None:
        """
        Emergency load reduction for severe lag conditions.
        More aggressive degradation measures.
        """
        logger.error("Triggering emergency performance degradation",
                    lag_ms=round(lag_ms, 2),
                    severe_lag_count=self.severe_lag_count,
                    degradation_level="emergency")
        
        # Execute emergency degradation callbacks
        for callback in self.degradation_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback("emergency", lag_ms)
                else:
                    callback("emergency", lag_ms)
            except Exception as e:
                logger.error("Error executing emergency degradation callback", error=str(e))
        
        # Reset severe lag counter after emergency action
        self.severe_lag_count = 0
    
    async def recover_from_degradation(self) -> None:
        """Recover from degraded state when performance improves."""
        if self.degradation_active:
            self.degradation_active = False
            logger.info("Recovering from performance degradation")
            
            # Execute recovery callbacks
            for callback in self.degradation_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback("recovery", 0.0)
                    else:
                        callback("recovery", 0.0)
                except Exception as e:
                    logger.error("Error executing recovery callback", error=str(e))
    
    def add_degradation_callback(self, callback: Callable) -> None:
        """
        Add a callback to be executed during degradation events.
        Callback signature: callback(level: str, lag_ms: float)
        Levels: "standard", "emergency", "recovery"
        """
        self.degradation_callbacks.append(callback)
        logger.debug("Added performance degradation callback")
    
    def remove_degradation_callback(self, callback: Callable) -> None:
        """Remove a degradation callback."""
        if callback in self.degradation_callbacks:
            self.degradation_callbacks.remove(callback)
            logger.debug("Removed performance degradation callback")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance statistics and metrics."""
        if not self.lag_measurements:
            return {
                'status': 'no_measurements',
                'monitoring_active': self.monitor_task is not None and not self.monitor_task.done(),
                'degradation_active': self.degradation_active
            }
        
        # Calculate statistics from recent measurements
        recent_lags = [m['lag_ms'] for m in self.lag_measurements[-20:]]  # Last 20 measurements
        avg_lag = sum(recent_lags) / len(recent_lags)
        max_lag = max(recent_lags)
        min_lag = min(recent_lags)
        
        # Calculate 95th percentile
        sorted_lags = sorted(recent_lags)
        p95_index = int(len(sorted_lags) * 0.95)
        p95_lag = sorted_lags[p95_index] if p95_index < len(sorted_lags) else max_lag
        
        return {
            'status': 'active',
            'monitoring_active': self.monitor_task is not None and not self.monitor_task.done(),
            'degradation_active': self.degradation_active,
            'severe_lag_count': self.severe_lag_count,
            'max_lag_threshold_ms': self.max_lag_ms,
            'severe_lag_threshold_ms': self.severe_lag_threshold,
            'measurements_count': len(self.lag_measurements),
            'recent_stats': {
                'avg_lag_ms': round(avg_lag, 2),
                'max_lag_ms': round(max_lag, 2),
                'min_lag_ms': round(min_lag, 2),
                'p95_lag_ms': round(p95_lag, 2),
                'measurements': len(recent_lags)
            },
            'callback_count': len(self.degradation_callbacks)
        }
    
    def is_healthy(self) -> bool:
        """Check if the event loop is performing within acceptable parameters."""
        if not self.lag_measurements:
            return True  # No measurements yet, assume healthy
        
        recent_lags = [m['lag_ms'] for m in self.lag_measurements[-5:]]  # Last 5 measurements
        avg_recent_lag = sum(recent_lags) / len(recent_lags)
        
        return (
            avg_recent_lag <= self.max_lag_ms and 
            not self.degradation_active and 
            self.severe_lag_count == 0
        )


# Global event loop monitor instance
event_loop_monitor = SimpleEventLoopMonitor()


def start_performance_monitoring() -> None:
    """Start global performance monitoring."""
    event_loop_monitor.start_monitoring()


def stop_performance_monitoring() -> None:
    """Stop global performance monitoring."""
    event_loop_monitor.stop_monitoring()


def get_global_performance_stats() -> Dict[str, Any]:
    """Get global performance statistics."""
    return event_loop_monitor.get_performance_stats()


def add_global_degradation_callback(callback: Callable) -> None:
    """Add a callback to the global performance monitor."""
    event_loop_monitor.add_degradation_callback(callback)