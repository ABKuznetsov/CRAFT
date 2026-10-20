"""Shared Qt delivery and bounded shutdown for background application work."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import threading
import time

from PySide6.QtCore import QCoreApplication, QObject, Qt, Signal, Slot


ProgressCallback = Callable[[object], None]
BackgroundWork = Callable[[ProgressCallback], object]


class _Signals(QObject):
    progressed = Signal(int, object)
    succeeded = Signal(int, object)
    failed = Signal(int, object)


@dataclass(frozen=True, slots=True)
class _Job:
    progressed: ProgressCallback | None
    succeeded: Callable[[object], None]
    failed: Callable[[BaseException], None]
    cancelled: threading.Event


def _run_job(job_id: int, work: BackgroundWork, signals: _Signals, cancelled: threading.Event) -> None:
    # Do not retain the executor: cancelled workers may outlive its QObject.
    def emit(update: object) -> None:
        if not cancelled.is_set():
            signals.progressed.emit(job_id, update)

    try:
        result = work(emit)
    except BaseException as error:
        if not cancelled.is_set():
            signals.failed.emit(job_id, error)
    else:
        if not cancelled.is_set():
            signals.succeeded.emit(job_id, result)


class QtBackgroundExecutor(QObject):
    """Own worker lifetimes; leave request ordering and caching to managers."""

    _thread_name = "craft-background"

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # The application destroys the bridge on the GUI thread even if a
        # cancelled daemon still holds its Python wrapper during shutdown.
        self._signals = _Signals(QCoreApplication.instance())
        self._signals.progressed.connect(self._deliver_progress, Qt.ConnectionType.QueuedConnection)
        self._signals.succeeded.connect(self._deliver_success, Qt.ConnectionType.QueuedConnection)
        self._signals.failed.connect(self._deliver_failure, Qt.ConnectionType.QueuedConnection)
        self._jobs: dict[int, _Job] = {}
        self._threads: list[threading.Thread] = []
        self._next_job_id = 0
        self._accepting = True
        self._signals_connected = True

    def _submit(
        self,
        work: BackgroundWork,
        progressed: ProgressCallback | None,
        succeeded: Callable[[object], None],
        failed: Callable[[BaseException], None],
    ) -> None:
        if not self._accepting:
            return
        job_id = self._next_job_id
        self._next_job_id += 1
        cancelled = threading.Event()
        self._jobs[job_id] = _Job(progressed, succeeded, failed, cancelled)
        self._threads = [thread for thread in self._threads if thread.is_alive()]
        thread = threading.Thread(
            target=_run_job,
            args=(job_id, work, self._signals, cancelled),
            name=f"{self._thread_name}-{job_id}",
            daemon=True,
        )
        self._threads.append(thread)
        thread.start()

    def close(self, timeout_ms: int = 100) -> bool:
        self._accepting = False
        for job in self._jobs.values():
            job.cancelled.set()
        self._jobs.clear()
        if self._signals_connected:
            self._signals.progressed.disconnect(self._deliver_progress)
            self._signals.succeeded.disconnect(self._deliver_success)
            self._signals.failed.disconnect(self._deliver_failure)
            self._signals_connected = False
        # Reserve part of the budget for QObject/Python teardown.
        timeout_seconds = max(0, int(timeout_ms)) / 1_000.0
        deadline = time.monotonic() + max(0.0, timeout_seconds - min(0.005, timeout_seconds))
        threads = tuple(self._threads)
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        return all(not thread.is_alive() for thread in threads)

    @Slot(int, object)
    def _deliver_progress(self, job_id: int, update: object) -> None:
        job = self._jobs.get(job_id)
        if job is not None and self._accepting and not job.cancelled.is_set() and job.progressed is not None:
            job.progressed(update)

    @Slot(int, object)
    def _deliver_success(self, job_id: int, result: object) -> None:
        job = self._jobs.pop(job_id, None)
        if job is not None and self._accepting and not job.cancelled.is_set():
            job.succeeded(result)

    @Slot(int, object)
    def _deliver_failure(self, job_id: int, error: BaseException) -> None:
        job = self._jobs.pop(job_id, None)
        if job is not None and self._accepting and not job.cancelled.is_set():
            job.failed(error)
