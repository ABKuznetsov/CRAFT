"""Warm CRiStMa reference data without racing the first structure load."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event, Lock, Thread

from cristma.crystallography import SpaceGroupCatalog


class ReferenceDataWarmup:
    """Load one immutable reference resource once, optionally in the background."""

    def __init__(self, loader: Callable[[], object]) -> None:
        self._loader = loader
        self._load_lock = Lock()
        self._start_lock = Lock()
        self._ready = Event()
        self._result: object | None = None
        self._error: BaseException | None = None
        self._thread: Thread | None = None

    def ensure(self) -> object:
        if not self._ready.is_set():
            with self._load_lock:
                if not self._ready.is_set():
                    try:
                        self._result = self._loader()
                    except BaseException as error:
                        self._error = error
                    finally:
                        self._ready.set()
        if self._error is not None:
            raise self._error
        return self._result

    def start(self) -> Thread:
        with self._start_lock:
            if self._thread is None:
                self._thread = Thread(
                    target=self._run,
                    name="cristma-reference-data-warmup",
                    daemon=True,
                )
                self._thread.start()
            return self._thread

    def _run(self) -> None:
        try:
            self.ensure()
        except BaseException:
            # The foreground reader will surface the original failure with its
            # normal CRAFT error handling if the installation is incomplete.
            pass


_CRISTMA_REFERENCE_DATA = ReferenceDataWarmup(SpaceGroupCatalog.default)


def ensure_cristma_reference_data() -> object:
    return _CRISTMA_REFERENCE_DATA.ensure()


def start_cristma_reference_data_warmup() -> Thread:
    return _CRISTMA_REFERENCE_DATA.start()


__all__ = [
    "ReferenceDataWarmup",
    "ensure_cristma_reference_data",
    "start_cristma_reference_data_warmup",
]
