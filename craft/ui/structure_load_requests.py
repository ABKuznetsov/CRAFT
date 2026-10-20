from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from craft.ui.background_tasks import QtBackgroundExecutor


LoadSignature = tuple[object, ...] | str
ProgressCallback = Callable[[object], None]
LoadWork = Callable[[ProgressCallback], object]


class StructureLoadExecutor(Protocol):
    def submit(
        self,
        work: LoadWork,
        progressed: ProgressCallback,
        succeeded: Callable[[object], None],
        failed: Callable[[BaseException], None],
    ) -> None: ...

    def close(self, timeout_ms: int) -> bool: ...


@dataclass(frozen=True, slots=True)
class _Request:
    signature: LoadSignature
    work: LoadWork


class StructureLoadRequestManager:
    """Serialize loads and publish progress only for the latest request."""

    def __init__(
        self,
        executor: StructureLoadExecutor,
        progressed: Callable[[LoadSignature, object], None],
        ready: Callable[[LoadSignature], None],
        failed: Callable[[LoadSignature, BaseException], None],
    ) -> None:
        self._executor = executor
        self._progressed = progressed
        self._ready = ready
        self._failed = failed
        self._accepting = True
        self._current_signature: LoadSignature | None = None
        self._active: _Request | None = None
        self._pending: _Request | None = None

    def request(self, signature: LoadSignature, work: LoadWork) -> None:
        if not self._accepting:
            return
        self._current_signature = signature
        request = _Request(signature, work)
        if self._active is not None:
            self._pending = None if self._active.signature == signature else request
            return
        self._start(request)

    def close(self, timeout_ms: int = 100) -> bool:
        self._accepting = False
        self._pending = None
        return self._executor.close(timeout_ms)

    def _start(self, request: _Request) -> None:
        self._active = request
        self._executor.submit(
            request.work,
            lambda update: self._progress(request, update),
            lambda result: self._succeeded(request, result),
            lambda error: self._errored(request, error),
        )

    def _progress(self, request: _Request, update: object) -> None:
        if (
            self._accepting
            and request is self._active
            and request.signature == self._current_signature
        ):
            self._progressed(request.signature, update)

    def _succeeded(self, request: _Request, _result: object) -> None:
        if request is not self._active:
            return
        self._active = None
        if not self._accepting:
            return
        if request.signature == self._current_signature:
            self._ready(request.signature)
        self._start_pending()

    def _errored(self, request: _Request, error: BaseException) -> None:
        if request is not self._active:
            return
        self._active = None
        if not self._accepting:
            return
        if request.signature == self._current_signature:
            self._failed(request.signature, error)
        self._start_pending()

    def _start_pending(self) -> None:
        request = self._pending
        self._pending = None
        if request is not None and request.signature == self._current_signature:
            self._start(request)


class QtStructureLoadExecutor(QtBackgroundExecutor):
    """Run staged loading with the shared Qt worker lifecycle."""

    _thread_name = "crystal-load"

    def submit(
        self,
        work: LoadWork,
        progressed: ProgressCallback,
        succeeded: Callable[[object], None],
        failed: Callable[[BaseException], None],
    ) -> None:
        self._submit(work, progressed, succeeded, failed)


__all__ = [
    "QtStructureLoadExecutor",
    "StructureLoadExecutor",
    "StructureLoadRequestManager",
]
