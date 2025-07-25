import asyncio
import time
from typing import List, Optional
from dataclasses import dataclass

from .logging_config import get_logger


@dataclass
class CacheEntry:
    """Cached model data entry."""
    models: List[str]
    timestamp: float
    
    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if cache entry is expired."""
        return time.time() - self.timestamp > ttl_seconds


class ModelCache:
    """In-memory cache for OpenAI models with TTL and periodic refresh."""
    
    def __init__(self, ttl_hours: int = 4):
        self.ttl_seconds = ttl_hours * 3600
        self._cache_entry: Optional[CacheEntry] = None
        self._refresh_task: Optional[asyncio.Task] = None
        self._refresh_interval = ttl_hours * 3600  # Refresh at TTL interval
        self.logger = get_logger("model_cache")
        
    async def get_models(self, openai_service) -> List[str]:
        """Get cached models or fetch from API if cache is empty/expired."""
        if self._cache_entry is None or self._cache_entry.is_expired(self.ttl_seconds):
            self.logger.info("Cache miss or expired, fetching fresh models")
            await self._refresh_cache(openai_service)
        else:
            self.logger.debug("Cache hit, returning cached models", model_count=len(self._cache_entry.models))
            
        return self._cache_entry.models if self._cache_entry else []
    
    async def _refresh_cache(self, openai_service) -> None:
        """Refresh cache with fresh data from OpenAI API."""
        try:
            models = await openai_service.get_vision_models()
            self._cache_entry = CacheEntry(models=models, timestamp=time.time())
            self.logger.info("Cache refreshed", model_count=len(models))
        except Exception as e:
            self.logger.error("Failed to refresh model cache", error=str(e))
            # Keep existing cache if refresh fails
            if self._cache_entry is None:
                # If no cache exists and refresh fails, raise the error
                raise
    
    async def start_periodic_refresh(self, openai_service) -> None:
        """Start periodic cache refresh task."""
        if self._refresh_task is not None:
            return
            
        self.logger.info("Starting periodic cache refresh", interval_hours=self._refresh_interval/3600)
        self._refresh_task = asyncio.create_task(self._periodic_refresh_worker(openai_service))
    
    async def stop_periodic_refresh(self) -> None:
        """Stop periodic cache refresh task."""
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None
            self.logger.info("Stopped periodic cache refresh")
    
    async def _periodic_refresh_worker(self, openai_service) -> None:
        """Background worker for periodic cache refresh."""
        while True:
            try:
                await asyncio.sleep(self._refresh_interval)
                await self._refresh_cache(openai_service)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in periodic cache refresh", error=str(e))
    
    def get_cache_status(self) -> dict:
        """Get current cache status for monitoring."""
        base_status = {
            "ttl_seconds": self.ttl_seconds,
            "refresh_interval_seconds": self._refresh_interval,
            "periodic_refresh_active": self._refresh_task is not None
        }
        
        if self._cache_entry is None:
            base_status.update({
                "status": "empty",
                "model_count": 0,
                "age_seconds": 0
            })
            return base_status
        
        age_seconds = time.time() - self._cache_entry.timestamp
        is_expired = self._cache_entry.is_expired(self.ttl_seconds)
        
        base_status.update({
            "status": "expired" if is_expired else "valid",
            "model_count": len(self._cache_entry.models),
            "age_seconds": age_seconds
        })
        
        return base_status
    
    def clear_cache(self) -> None:
        """Clear the cache. Useful for testing."""
        self._cache_entry = None
        self.logger.debug("Cache cleared")


# Global cache instance
model_cache = ModelCache(ttl_hours=4)