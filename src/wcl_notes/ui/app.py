"""Start the desktop application."""

import logging
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QTimer, QTranslator
from PySide6.QtWidgets import QApplication

from wcl_notes.api.client import WclClient
from wcl_notes.api.credentials import has_credentials, load_credentials
from wcl_notes.cache.response_cache import ResponseCache, default_cache_path
from wcl_notes.i18n import get_language, set_language, system_language
from wcl_notes.ui.controller import AppController
from wcl_notes.ui.icons import IconProvider
from wcl_notes.ui.main_window import MainWindow
from wcl_notes.ui.settings import AppSettings
from wcl_notes.ui.style import apply_dark_theme
from wcl_notes.ui.workers import TaskRunner


def open_cache() -> ResponseCache | None:
    """The cache saves API points; the app still works (slower on quota) without it."""
    try:
        cache = ResponseCache(default_cache_path())
        cache.prune()
    except (OSError, sqlite3.Error):
        logging.getLogger(__name__).exception("Cache unavailable")
        return None
    return cache


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setOrganizationName("WoW Timeline Gatherer")
    app.setApplicationName("wcl-notes")
    apply_dark_theme(app)
    settings = AppSettings()
    set_language(settings.language or system_language())
    if get_language() == "fr":
        # French texts for Qt's own widgets (standard buttons, color dialog…).
        qt_translator = QTranslator(app)
        if qt_translator.load(
            QLocale(QLocale.Language.French),
            "qtbase",
            "_",
            QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
        ):
            app.installTranslator(qt_translator)

    runner = TaskRunner(app)
    # Icon downloads get their own runner so they do not drive the busy indicator.
    icons = IconProvider(TaskRunner(app), parent=app)
    cache = open_cache()

    def client_factory() -> WclClient:
        return WclClient(load_credentials(Path(".env")), cache=cache)

    controller = AppController(runner, client_factory, parent=app, presets=settings)
    window = MainWindow(controller, settings, icons, runner, cache=cache)
    window.show()
    if not has_credentials(Path(".env")):
        QTimer.singleShot(0, window.ask_for_credentials)
    return app.exec()
