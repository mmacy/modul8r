import asyncio
import pytest
from functools import wraps


def fixture(*args, **kwargs):
    """Simple replacement for pytest_asyncio.fixture."""
    def decorator(func):
        is_coroutine = asyncio.iscoroutinefunction(func)

        @wraps(func)
        def wrapper(*fa, **fkw):
            if is_coroutine:
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(func(*fa, **fkw))
            return func(*fa, **fkw)

        return pytest.fixture(*args, **kwargs)(wrapper)

    return decorator

__all__ = ["fixture"]
