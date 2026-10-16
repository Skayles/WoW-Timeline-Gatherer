"""Packaging smoke test: ``--self-check report.json`` (no window shown, no network).

Checks that a frozen build ships what the app loads at run time: GraphQL queries,
YAML data, Qt platform plugin and French translations, keyring backend, SQLite.
"""

import json
import sys
import tempfile
import traceback
from collections.abc import Callable
from importlib import resources
from pathlib import Path

from wcl_notes import __version__


def _check(results: dict[str, object], name: str, fn: Callable[[], object]) -> None:
    try:
        results[name] = fn()
    except Exception:
        results[name] = {"error": traceback.format_exc(limit=3)}


def run_self_check(output: Path) -> int:
    from PySide6.QtCore import QLibraryInfo, QLocale, QSettings, QTranslator
    from PySide6.QtWidgets import QApplication

    results: dict[str, object] = {
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
    }

    def queries() -> int:
        folder = resources.files("wcl_notes.api").joinpath("queries")
        return sum(1 for f in folder.iterdir() if f.name.endswith(".graphql"))

    def data() -> dict[str, int]:
        from wcl_notes.services.data_files import all_spec_files, load_encounters

        return {"encounters": len(load_encounters()), "spec_files": len(all_spec_files())}

    def keyring_backend() -> str:
        import keyring

        return type(keyring.get_keyring()).__module__

    def sqlite_cache() -> int:
        from wcl_notes.cache.response_cache import ResponseCache

        with tempfile.TemporaryDirectory() as folder:
            cache = ResponseCache(Path(folder) / "check.sqlite")
            cache.put("k", "check", {"ok": True}, None)
            hit = cache.get("k") == {"ok": True}
            cache.close()
        return int(hit)

    app = QApplication(["wcl-notes", "--self-check"])

    def qt() -> dict[str, object]:
        translator = QTranslator()
        french = translator.load(
            QLocale(QLocale.Language.French),
            "qtbase",
            "_",
            QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
        )
        return {"platform": app.platformName(), "qtbase_fr": french}

    def main_window() -> str:
        from wcl_notes.ui.controller import AppController
        from wcl_notes.ui.icons import IconProvider
        from wcl_notes.ui.main_window import MainWindow
        from wcl_notes.ui.settings import AppSettings
        from wcl_notes.ui.workers import TaskRunner

        with tempfile.TemporaryDirectory() as folder:
            settings = AppSettings(
                QSettings(str(Path(folder) / "s.ini"), QSettings.Format.IniFormat)
            )
            runner = TaskRunner(synchronous=True)
            icons = IconProvider(runner, Path(folder) / "icons", download=False)
            window = MainWindow(AppController(runner), settings, icons, runner)
            title = window.windowTitle()
            window.deleteLater()
        return title

    for name, fn in (
        ("queries", queries),
        ("data", data),
        ("keyring", keyring_backend),
        ("sqlite", sqlite_cache),
        ("qt", qt),
        ("main_window", main_window),
    ):
        _check(results, name, fn)

    ok = not any(isinstance(v, dict) and "error" in v for v in results.values())
    results["ok"] = ok
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok else 1
