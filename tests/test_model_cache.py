import pytest
import asyncio
import time
from unittest.mock import AsyncMock, Mock

from src.modul8r.model_cache import ModelCache, CacheEntry
from src.modul8r.services import OpenAIService


class TestModelCache:
    @pytest.fixture
    def mock_openai_service(self):
        service = Mock(spec=OpenAIService)
        service.get_vision_models = AsyncMock(return_value=["gpt-4o", "gpt-4o-mini", "o1-preview"])
        return service

    @pytest.fixture
    def cache(self):
        # Use short TTL for testing
        return ModelCache(ttl_hours=1)

    def test_cache_entry_expiration(self):
        # Test cache entry expiration logic
        entry = CacheEntry(models=["gpt-4o"], timestamp=time.time())
        assert not entry.is_expired(3600)  # 1 hour TTL, not expired
        
        old_entry = CacheEntry(models=["gpt-4o"], timestamp=time.time() - 7200)  # 2 hours ago
        assert old_entry.is_expired(3600)  # 1 hour TTL, expired

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_fresh_data(self, cache, mock_openai_service):
        # First call should fetch from API
        models = await cache.get_models(mock_openai_service)
        
        assert models == ["gpt-4o", "gpt-4o-mini", "o1-preview"]
        mock_openai_service.get_vision_models.assert_called_once()
        
        # Cache should now be populated
        status = cache.get_cache_status()
        assert status["status"] == "valid"
        assert status["model_count"] == 3

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_data(self, cache, mock_openai_service):
        # Populate cache
        await cache.get_models(mock_openai_service)
        mock_openai_service.get_vision_models.reset_mock()
        
        # Second call should use cache
        models = await cache.get_models(mock_openai_service)
        
        assert models == ["gpt-4o", "gpt-4o-mini", "o1-preview"]
        mock_openai_service.get_vision_models.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_expiration_triggers_refresh(self, mock_openai_service):
        # Use very short TTL
        cache = ModelCache(ttl_hours=1)
        
        # Populate cache
        await cache.get_models(mock_openai_service)
        
        # Manually expire cache by setting old timestamp
        cache._cache_entry.timestamp = time.time() - 7200  # 2 hours ago
        mock_openai_service.get_vision_models.reset_mock()
        
        # Next call should refresh cache
        models = await cache.get_models(mock_openai_service)
        
        assert models == ["gpt-4o", "gpt-4o-mini", "o1-preview"]
        mock_openai_service.get_vision_models.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_failure_preserves_old_cache(self, cache, mock_openai_service):
        # Populate cache initially
        await cache.get_models(mock_openai_service)
        
        # Configure service to fail on next call
        mock_openai_service.get_vision_models.side_effect = Exception("API Error")
        
        # Manually expire cache
        cache._cache_entry.timestamp = time.time() - 7200
        
        # Should return old cached data despite being expired
        models = await cache.get_models(mock_openai_service)
        assert models == ["gpt-4o", "gpt-4o-mini", "o1-preview"]

    @pytest.mark.asyncio
    async def test_cache_failure_with_no_cache_raises_error(self, cache, mock_openai_service):
        # Configure service to fail
        mock_openai_service.get_vision_models.side_effect = Exception("API Error")
        
        # Should raise error when no cache exists
        with pytest.raises(Exception, match="API Error"):
            await cache.get_models(mock_openai_service)

    @pytest.mark.asyncio
    async def test_periodic_refresh_lifecycle(self, cache, mock_openai_service):
        # Start periodic refresh
        await cache.start_periodic_refresh(mock_openai_service)
        
        status = cache.get_cache_status()
        assert status["periodic_refresh_active"] is True
        
        # Stop periodic refresh
        await cache.stop_periodic_refresh()
        
        status = cache.get_cache_status()
        assert status["periodic_refresh_active"] is False

    @pytest.mark.asyncio
    async def test_multiple_start_refresh_calls_ignored(self, cache, mock_openai_service):
        # Multiple calls to start should not create multiple tasks
        await cache.start_periodic_refresh(mock_openai_service)
        first_task = cache._refresh_task
        
        await cache.start_periodic_refresh(mock_openai_service)
        second_task = cache._refresh_task
        
        assert first_task is second_task
        
        await cache.stop_periodic_refresh()

    def test_cache_status_empty(self, cache):
        status = cache.get_cache_status()
        assert status["status"] == "empty"
        assert status["model_count"] == 0
        assert status["age_seconds"] == 0
        assert status["periodic_refresh_active"] is False

    @pytest.mark.asyncio
    async def test_cache_status_populated(self, cache, mock_openai_service):
        await cache.get_models(mock_openai_service)
        
        status = cache.get_cache_status()
        assert status["status"] == "valid"
        assert status["model_count"] == 3
        assert status["age_seconds"] >= 0
        assert status["ttl_seconds"] == 3600  # 1 hour in seconds

    def test_clear_cache(self, cache):
        # Manually add cache entry
        cache._cache_entry = CacheEntry(models=["test"], timestamp=time.time())
        
        # Clear cache
        cache.clear_cache()
        
        assert cache._cache_entry is None
        status = cache.get_cache_status()
        assert status["status"] == "empty"