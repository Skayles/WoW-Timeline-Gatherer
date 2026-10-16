"""English translation: complete, consistent placeholders, and actually used."""

import ast
import string
from collections.abc import Iterator
from importlib import resources
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from conftest import REPORT_CODE, FakeWcl
from wcl_notes.cli import main
from wcl_notes.domain.encounters import IDENTITY_MAPPING
from wcl_notes.i18n import catalog, get_language, set_language, system_language, tr
from wcl_notes.labels import CATEGORY_LABELS, DIFFICULTY_LABELS, OTHER_CATEGORY_LABEL, ROLE_LABELS
from wcl_notes.services.data_files import load_encounters
from wcl_notes.services.notes import MAPPING_STATUS_LABELS
from wcl_notes.services.report_reference import (
    InvalidReportReferenceError,
    parse_report_reference,
)
from wcl_notes.ui import log_panel, rankings_panel
from wcl_notes.ui.controller import AppController
from wcl_notes.ui.icons import IconProvider
from wcl_notes.ui.main_window import MainWindow
from wcl_notes.ui.settings import AppSettings
from wcl_notes.ui.workers import TaskRunner

SOURCE = Path(resources.files("wcl_notes").joinpath("__init__.py")).parent  # type: ignore[arg-type]


def literal_texts() -> set[str]:
    """Every ``tr("...")`` literal of the source code."""
    texts = set()
    for path in SOURCE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                texts.add(node.args[0].value)
    return texts


def dynamic_texts() -> set[str]:
    """Texts passed to ``tr`` through variables: labels, states, phase notes."""
    texts = {OTHER_CATEGORY_LABEL, IDENTITY_MAPPING.note}
    texts |= set(DIFFICULTY_LABELS.values()) | set(ROLE_LABELS.values())
    texts |= set(CATEGORY_LABELS.values()) | set(MAPPING_STATUS_LABELS.values())
    texts |= {t for t in log_panel.STATE_LABELS.values() if t}
    texts |= {t for t in rankings_panel.STATE_LABELS.values() if t}
    texts |= set(rankings_panel.SORT_LABELS.values()) | set(rankings_panel.COLUMNS)
    texts |= {e.nsrt.note for e in load_encounters().values() if e.nsrt.note}
    return texts


def _placeholders(text: str) -> Iterator[str]:
    for _, field, _, _ in string.Formatter().parse(text):
        if field is not None:
            yield field


@pytest.fixture(autouse=True)
def french_afterwards() -> Iterator[None]:
    yield
    set_language("fr")


def test_every_text_has_an_english_translation() -> None:
    missing = (literal_texts() | dynamic_texts()) - set(catalog("en"))
    assert not missing, sorted(missing)


def test_no_unused_translation() -> None:
    unused = set(catalog("en")) - literal_texts() - dynamic_texts()
    assert not unused, sorted(unused)


def test_placeholders_are_kept() -> None:
    for source, english in catalog("en").items():
        assert sorted(_placeholders(source)) == sorted(_placeholders(english)), source


def test_tr_follows_the_language() -> None:
    assert get_language() == "fr"
    assert tr("Charger") == "Charger"
    set_language("en")
    assert tr("Charger") == "Load"
    assert tr("texte inconnu") == "texte inconnu"
    set_language("xx")
    assert get_language() == "fr"
    assert system_language() in ("fr", "en")


def test_errors_in_english() -> None:
    set_language("en")
    with pytest.raises(InvalidReportReferenceError, match="Paste a Warcraft Logs URL"):
        parse_report_reference("")


def test_cli_in_english(fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([REPORT_CODE, "--lang", "en"], client_factory=lambda _: fake_wcl.client()) == 0
    out = capsys.readouterr().out
    assert "→ Run again with --fight <id>" in out
    assert "Mythic" in out and "Mythique" not in out


def test_main_window_in_english(qtbot: QtBot, fake_wcl: FakeWcl, tmp_path: Path) -> None:
    set_language("en")
    settings = AppSettings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    runner = TaskRunner(synchronous=True)
    icons = IconProvider(runner, tmp_path / "icons", download=False)
    window = MainWindow(AppController(runner, fake_wcl.client), settings, icons, runner)
    qtbot.addWidget(window)
    tabs = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert tabs == ["Rankings", "Log", "Tracks"]
    assert window.log_panel.load_button.text() == "Load"


def test_language_setting(tmp_path: Path) -> None:
    settings = AppSettings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    assert settings.language == ""
    settings.language = "en"
    assert settings.language == "en"
    settings.language = "de"
    assert settings.language == ""
