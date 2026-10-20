from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from craft.ui.background_tasks import QtBackgroundExecutor


ComparisonSignature = tuple[object, ...] | str
ComparisonBundle = object


class ComparisonExecutor(Protocol):
    def submit(
        self,
        work: Callable[[], ComparisonBundle],
        succeeded: Callable[[ComparisonBundle], None],
        failed: Callable[[BaseException], None],
    ) -> None: ...

    def close(self, timeout_ms: int) -> bool: ...


@dataclass(frozen=True, slots=True)
class _Request:
    signature: ComparisonSignature
    work: Callable[[], ComparisonBundle]


class ComparisonRequestManager:
    """Serialize comparison work and publish only the latest requested signature."""

    def __init__(
        self,
        executor: ComparisonExecutor,
        ready: Callable[[ComparisonSignature, ComparisonBundle], None],
        failed: Callable[[ComparisonSignature, BaseException], None],
        *,
        max_cached: int = 8,
    ) -> None:
        self._executor = executor
        self._ready = ready
        self._failed = failed
        self._max_cached = max(1, int(max_cached))
        self._accepting = True
        self._current_signature: ComparisonSignature | None = None
        self._active: _Request | None = None
        self._pending: _Request | None = None
        self._cache: dict[ComparisonSignature, ComparisonBundle] = {}

    def request(
        self,
        signature: ComparisonSignature,
        work: Callable[[], ComparisonBundle],
    ) -> None:
        if not self._accepting:
            return
        self._current_signature = signature
        cached = self._cache.get(signature)
        if cached is not None:
            self._pending = None
            self._ready(signature, cached)
            return
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
            lambda bundle: self._succeeded(request, bundle),
            lambda error: self._errored(request, error),
        )

    def _succeeded(self, request: _Request, bundle: ComparisonBundle) -> None:
        if request is not self._active:
            return
        self._active = None
        if not self._accepting:
            return
        self._cache[request.signature] = bundle
        while len(self._cache) > self._max_cached:
            self._cache.pop(next(iter(self._cache)))
        if request.signature == self._current_signature:
            self._ready(request.signature, bundle)
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


class QtComparisonExecutor(QtBackgroundExecutor):
    """Run comparisons with the shared Qt worker lifecycle."""

    _thread_name = "crystal-comparison"

    def submit(
        self,
        work: Callable[[], ComparisonBundle],
        succeeded: Callable[[ComparisonBundle], None],
        failed: Callable[[BaseException], None],
    ) -> None:
        self._submit(lambda _progress: work(), None, succeeded, failed)


__all__ = [
    "ComparisonExecutor",
    "ComparisonRequestManager",
    "ComparisonSignature",
    "QtComparisonExecutor",
]
