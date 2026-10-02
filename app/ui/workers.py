"""Background workers so the UI never blocks on network calls."""

from __future__ import annotations

import traceback
from collections.abc import Callable, Iterator
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from ..core.redact import redact_secrets


class WorkerSignals(QObject):
    started = Signal(str)
    progress = Signal(str)
    result = Signal(object)
    error = Signal(str)
    traceback = Signal(str)
    finished = Signal(str)


class Task(QRunnable):
    """Run ``fn(*args, **kwargs)`` on a thread pool thread.

    ``fn`` may return an iterator; in that case every yielded item is emitted
    through :attr:`stream` and the joined text becomes the final result. This is
    how streaming LLM responses are handled.
    """

    def __init__(self, key: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.key = key
        self.signals = WorkerSignals()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._cancelled = False
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:  # noqa: D102
        self.signals.started.emit(self.key)
        try:
            outcome = self._fn(*self._args, **self._kwargs)
            if self._cancelled:
                return
            if isinstance(outcome, Iterator) or (
                hasattr(outcome, "__next__") and hasattr(outcome, "__iter__")
            ):
                chunks: list[str] = []
                for piece in outcome:
                    if self._cancelled:
                        return
                    text = piece if isinstance(piece, str) else str(piece)
                    chunks.append(text)
                    self.signals.progress.emit(text)
                self.signals.result.emit("".join(chunks))
            else:
                self.signals.result.emit(outcome)
        except Exception as exc:  # noqa: BLE001
            # Report the exception type alongside the message: a bare str(exc)
            # can be empty, which would surface as a blank toast. Scrubbed in
            # case the message quotes a credential.
            detail = str(exc).strip() or exc.__class__.__name__
            self.signals.error.emit(redact_secrets(detail))
            self.signals.traceback.emit(traceback.format_exc())
        finally:
            self.signals.finished.emit(self.key)

    def cancel(self) -> None:
        self._cancelled = True


# Strong references to in-flight tasks.
#
# QRunnable with autoDelete is freed by C++ as soon as run() returns, which can
# also drop the Python wrapper and therefore its WorkerSignals - the queued
# signals then never arrive. Keeping the task alive until "finished" fixes it.
#
# Keyed by id(task), not by the caller's key: two tasks that happen to share a
# name would otherwise evict each other from this dict and the older one could
# be collected while still running, which is the same bug again.
_ACTIVE: dict[int, tuple[str, Task]] = {}


def _release(handle: int) -> None:
    """Drop the strong reference held while the task was running."""
    _ACTIVE.pop(handle, None)


def run(
    key: str,
    fn: Callable[..., Any],
    *args: Any,
    on_start: Callable[[], None] | None = None,
    on_result: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_finish: Callable[[], None] | None = None,
    **kwargs: Any,
) -> Task:
    """Convenience wrapper: build, wire and schedule a :class:`Task`."""
    task = Task(key, fn, *args, **kwargs)
    handle = id(task)
    _ACTIVE[handle] = (key, task)

    def done(_key: str) -> None:
        # Release before on_finish so a task started from that callback is not
        # mistaken for this one.
        _release(handle)
        if on_finish:
            on_finish()

    if on_start:
        task.signals.started.connect(lambda _k: on_start())
    if on_result:
        task.signals.result.connect(on_result)
    if on_error:
        task.signals.error.connect(on_error)
    if on_progress:
        task.signals.progress.connect(on_progress)
    task.signals.finished.connect(done)

    pool().start(task)
    return task


def active_keys() -> list[str]:
    """Keys of the tasks that have been scheduled but not yet finished."""
    return [key for key, _ in _ACTIVE.values()]


def active_count() -> int:
    """Number of tasks currently in flight."""
    return len(_ACTIVE)


def pool() -> QThreadPool:
    instance = QThreadPool.globalInstance()
    instance.setMaxThreadCount(max(4, min(10, instance.maxThreadCount())))
    return instance


def shutdown() -> None:
    QThreadPool.globalInstance().waitForDone(3000)
