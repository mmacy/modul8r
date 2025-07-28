import asyncio
import pytest

pytest_plugins = ["pytest_asyncio"]


@pytest.fixture
def event_loop():
    """Provide an event loop for tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as using asyncio")


def pytest_pyfunc_call(pyfuncitem):
    testfunc = pyfuncitem.obj
    if asyncio.iscoroutinefunction(testfunc):
        loop = pyfuncitem.funcargs.get("event_loop")
        if loop is None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(testfunc(**pyfuncitem.funcargs))
            finally:
                loop.close()
        else:
            loop.run_until_complete(testfunc(**pyfuncitem.funcargs))
        return True
