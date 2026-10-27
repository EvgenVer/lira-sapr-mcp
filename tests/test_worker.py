import asyncio
import threading
import time

import pytest

from lira_sapr_mcp.com.worker import ComWorker
from lira_sapr_mcp.errors import LiraTimeoutError


@pytest.fixture
def worker():
    w = ComWorker(init=lambda: None, uninit=lambda: None, pump=lambda: None)
    yield w
    w.stop()


def test_jobs_run_on_one_dedicated_thread(worker):
    caller = threading.get_ident()
    ids = {worker.call(threading.get_ident, timeout=5) for _ in range(5)}
    assert len(ids) == 1
    assert caller not in ids


def test_exceptions_reach_the_caller(worker):
    def boom():
        raise ValueError("bad table")

    with pytest.raises(ValueError, match="bad table"):
        worker.call(boom, timeout=5)


def test_timeout_names_the_running_job_and_skips_cancelled_ones(worker):
    release = threading.Event()
    ran = []

    def hanging_dialog():
        release.wait(5)

    worker.submit(hanging_dialog)
    time.sleep(0.05)
    with pytest.raises(LiraTimeoutError, match="hanging_dialog"):
        worker.call(lambda: ran.append(1), timeout=0.1)
    release.set()
    assert worker.call(lambda: "after", timeout=5) == "after"
    assert ran == []


def test_async_run_returns_result(worker):
    async def main():
        return await worker.run(lambda a, b: a + b, 2, 3, timeout=5)

    assert asyncio.run(main()) == 5


def test_async_run_times_out(worker):
    release = threading.Event()
    worker.submit(lambda: release.wait(5))

    async def main():
        await worker.run(lambda: None, timeout=0.1)

    with pytest.raises(LiraTimeoutError):
        asyncio.run(main())
    release.set()


def test_pump_runs_while_idle():
    pumped = threading.Event()
    w = ComWorker(init=lambda: None, uninit=lambda: None, pump=pumped.set)
    w.start()
    try:
        assert pumped.wait(2)
    finally:
        w.stop()
