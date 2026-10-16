"""Run network calls off the UI thread (QThreadPool) and get results back on it."""

import itertools
import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from wcl_notes.api.errors import WclError
from wcl_notes.services.report_navigation import NavigationError
from wcl_notes.services.report_reference import InvalidReportReferenceError

log = logging.getLogger(__name__)

# Errors whose message is already written for the user.
USER_FACING_ERRORS = (WclError, InvalidReportReferenceError, NavigationError, ValueError)

SuccessCallback = Callable[[Any], None]
ErrorCallback = Callable[[str], None]


def error_message(exc: BaseException) -> str:
    if isinstance(exc, USER_FACING_ERRORS):
        return str(exc)
    log.exception("Unexpected error in background task", exc_info=exc)
    return f"Erreur inattendue : {exc}"


class _TaskSignals(QObject):
    succeeded = Signal(int, object)
    failed = Signal(int, str)


class _Task(QRunnable):
    def __init__(self, task_id: int, fn: Callable[[], Any], signals: _TaskSignals) -> None:
        super().__init__()
        self._task_id = task_id
        self._fn = fn
        self._signals = signals

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:
            self._signals.failed.emit(self._task_id, error_message(exc))
        else:
            self._signals.succeeded.emit(self._task_id, result)


class TaskRunner(QObject):
    """Callbacks always run on the thread that owns the runner (the UI thread).

    ``synchronous=True`` runs tasks inline, for tests.
    """

    busy_changed = Signal(bool)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        pool: QThreadPool | None = None,
        synchronous: bool = False,
    ) -> None:
        super().__init__(parent)
        self._pool = pool or QThreadPool.globalInstance()
        self._synchronous = synchronous
        self._ids = itertools.count(1)
        self._callbacks: dict[int, tuple[SuccessCallback, ErrorCallback | None]] = {}
        self._signals = _TaskSignals()
        self._signals.succeeded.connect(self._on_succeeded)
        self._signals.failed.connect(self._on_failed)

    @property
    def busy(self) -> bool:
        return bool(self._callbacks)

    def run(
        self,
        fn: Callable[[], Any],
        on_success: SuccessCallback,
        on_error: ErrorCallback | None = None,
    ) -> None:
        if self._synchronous:
            try:
                result = fn()
            except Exception as exc:
                if on_error is not None:
                    on_error(error_message(exc))
                return
            on_success(result)
            return
        task_id = next(self._ids)
        was_busy = self.busy
        self._callbacks[task_id] = (on_success, on_error)
        if not was_busy:
            self.busy_changed.emit(True)
        self._pool.start(_Task(task_id, fn, self._signals))

    def wait(self) -> None:
        self._pool.waitForDone()

    @Slot(int, object)
    def _on_succeeded(self, task_id: int, result: object) -> None:
        on_success, _ = self._finish(task_id)
        on_success(result)

    @Slot(int, str)
    def _on_failed(self, task_id: int, message: str) -> None:
        _, on_error = self._finish(task_id)
        if on_error is not None:
            on_error(message)

    def _finish(self, task_id: int) -> tuple[SuccessCallback, ErrorCallback | None]:
        callbacks = self._callbacks.pop(task_id)
        if not self.busy:
            self.busy_changed.emit(False)
        return callbacks
