"""The one thread that talks to LIRA.

COM objects created in a single-threaded apartment may only be called from the thread that
created them, so every LIRA call goes through this worker's queue and runs here, one at a
time. Between jobs the worker pumps Windows messages: LIRA delivers its COM events (for
example "analysis finished") as messages to this thread.
"""

import asyncio
import logging
import queue
import threading
import traceback
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any

from lira_sapr_mcp.errors import LiraTimeoutError

log = logging.getLogger(__name__)

_STOP = object()


def _com_init() -> None:
    import pythoncom

    pythoncom.CoInitialize()


def _com_uninit() -> None:
    import pythoncom

    pythoncom.CoUninitialize()


def _pump() -> None:
    import pythoncom

    pythoncom.PumpWaitingMessages()


def _drop_frame_locals(exc: BaseException) -> None:
    """Free the locals kept in an exception's traceback before it leaves this thread.

    They often hold COM objects; released later by the garbage collector on a thread
    without COM, they fail with CO_E_NOTINITIALIZED.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        traceback.clear_frames(current.__traceback__)
        current = current.__cause__ or current.__context__


class ComWorker:
    def __init__(
        self,
        *,
        init: Callable[[], None] = _com_init,
        uninit: Callable[[], None] = _com_uninit,
        pump: Callable[[], None] = _pump,
        idle_wait_s: float = 0.02,
    ) -> None:
        self._init = init
        self._uninit = uninit
        self._pump = pump
        self._idle_wait_s = idle_wait_s
        self._jobs: queue.Queue[Any] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._busy_with: str | None = None

    @property
    def busy_with(self) -> str | None:
        """Name of the job running now, or None when idle."""
        return self._busy_with

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="lira-com", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            self._jobs.put(_STOP)
            self._thread.join(timeout)
            self._thread = None

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        self.start()
        fut: Future = Future()
        self._jobs.put((fut, fn, args, kwargs))
        return fut

    def call(self, fn: Callable[..., Any], *args: Any, timeout: float, **kwargs: Any) -> Any:
        """Run ``fn`` on the worker and wait for it from any other thread."""
        fut = self.submit(fn, *args, **kwargs)
        try:
            return fut.result(timeout)
        except TimeoutError:
            fut.cancel()
            raise self._timeout_error(fn, timeout) from None

    async def run(self, fn: Callable[..., Any], *args: Any, timeout: float, **kwargs: Any) -> Any:
        """Run ``fn`` on the worker and await it from the event loop."""
        fut = self.submit(fn, *args, **kwargs)
        try:
            return await asyncio.wait_for(asyncio.wrap_future(fut), timeout)
        except TimeoutError:
            raise self._timeout_error(fn, timeout) from None

    def _timeout_error(self, fn: Callable[..., Any], timeout: float) -> LiraTimeoutError:
        running = self._busy_with or "nothing"
        return LiraTimeoutError(
            f"LIRA did not answer within {timeout:.0f} s ({getattr(fn, '__name__', fn)}; "
            f"running now: {running}). A modal dialog in LIRA may be waiting for the user."
        )

    def _loop(self) -> None:
        self._init()
        try:
            while True:
                try:
                    job = self._jobs.get(timeout=self._idle_wait_s)
                except queue.Empty:
                    self._pump()
                    continue
                if job is _STOP:
                    return
                fut, fn, args, kwargs = job
                if not fut.set_running_or_notify_cancel():
                    continue
                self._busy_with = getattr(fn, "__name__", repr(fn))
                try:
                    fut.set_result(fn(*args, **kwargs))
                except BaseException as exc:
                    log.debug("job %s failed", self._busy_with, exc_info=exc)
                    _drop_frame_locals(exc)
                    fut.set_exception(exc)
                finally:
                    self._busy_with = None
                self._pump()
        finally:
            self._uninit()
