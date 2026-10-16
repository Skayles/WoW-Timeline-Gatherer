"""UI tests (offscreen Qt, recorded WCL responses, no network)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPixmap
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from conftest import MAGE_ID, REPORT_CODE, ROGUE_ID, FakeWcl
from wcl_notes.api.errors import WclError
from wcl_notes.domain.models import Report, TrackRef
from wcl_notes.services.notes import NoteFormat, NoteOptions, build_note
from wcl_notes.services.report_navigation import resolve_fight
from wcl_notes.services.report_reference import parse_report_reference
from wcl_notes.ui.controller import AppController, TrackState
from wcl_notes.ui.copy_note_dialog import CopyNoteDialog, parse_kill_time
from wcl_notes.ui.icons import IconProvider
from wcl_notes.ui.legend_panel import SPELL_ID_ROLE, LegendPanel
from wcl_notes.ui.log_panel import ID_ROLE, LogPanel
from wcl_notes.ui.main_window import MainWindow
from wcl_notes.ui.rankings_panel import RankingsPanel
from wcl_notes.ui.settings import DEFAULT_PLAYER_NAME, AppSettings
from wcl_notes.ui.timeline_view import LABEL_WIDTH, MAX_PX_PER_S, TimelineView
from wcl_notes.ui.tracks_panel import TracksPanel
from wcl_notes.ui.workers import TaskRunner

URL = f"https://www.warcraftlogs.com/reports/{REPORT_CODE}"
ROGUE_REF = TrackRef(REPORT_CODE, 7, ROGUE_ID)
VANISH = 1856


class DeferredRunner(TaskRunner):
    """Keeps tasks until ``flush()``: lets tests act while a download is in flight."""

    def __init__(self) -> None:
        super().__init__(synchronous=True)
        self.pending: list[tuple[Callable[[], Any], Any, Any]] = []

    def run(self, fn: Callable[[], Any], on_success: Any, on_error: Any = None) -> None:
        self.pending.append((fn, on_success, on_error))

    def flush(self) -> None:
        while self.pending:
            fn, on_success, on_error = self.pending.pop(0)
            super().run(fn, on_success, on_error)


@pytest.fixture
def settings(tmp_path: Path) -> AppSettings:
    return AppSettings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))


@pytest.fixture
def controller(qtbot: QtBot, fake_wcl: FakeWcl) -> AppController:
    return AppController(TaskRunner(synchronous=True), client_factory=fake_wcl.client)


@pytest.fixture
def icons(tmp_path: Path) -> IconProvider:
    return IconProvider(TaskRunner(synchronous=True), tmp_path / "icons", download=False)


def _load(controller: AppController, text: str = URL) -> Report:
    loaded: list[Report] = []
    controller.report_loaded.connect(lambda report, _ref: loaded.append(report))
    controller.load_report(text)
    assert loaded, "report not loaded"
    return loaded[-1]


def _add(controller: AppController, report: Report, source_id: int, fight_id: int = 7) -> None:
    fight = resolve_fight(report, fight_id)
    controller.add_track(report, fight, report.actors[source_id], "test")


# --- settings & workers --------------------------------------------------------------


def test_settings_defaults_and_recent_reports(settings: AppSettings) -> None:
    assert settings.player_name == DEFAULT_PLAYER_NAME
    assert settings.my_spec == "Rogue-Assassination"
    assert (settings.note_format, settings.offset_s, settings.nsrt_dur) == ("mrt", 0.0, 0)
    settings.player_name = "  "
    assert settings.player_name == DEFAULT_PLAYER_NAME
    for i in range(12):
        settings.add_recent_report(f"code{i}", f"Raid {i}")
    settings.add_recent_report("code3", "Raid 3")
    recent = settings.recent_reports
    assert recent[0] == ("code3", "Raid 3")
    assert len(recent) == 10
    assert len({code for code, _ in recent}) == 10


def test_task_runner_delivers_results_on_the_ui_thread(qtbot: QtBot) -> None:
    runner = TaskRunner()
    results: list[object] = []
    with qtbot.waitSignal(runner.busy_changed, check_params_cb=lambda busy: busy is False):
        runner.run(lambda: 42, results.append)
    assert results == [42]


def test_task_runner_reports_errors(qtbot: QtBot) -> None:
    runner = TaskRunner()
    errors: list[str] = []

    def fail(exc: Exception) -> Callable[[], None]:
        def raise_it() -> None:
            raise exc

        return raise_it

    with qtbot.waitSignal(runner.busy_changed, check_params_cb=lambda busy: busy is False):
        runner.run(fail(WclError("Quota dépassé")), print, errors.append)
        runner.run(fail(KeyError("x")), print, errors.append)
    assert errors[0] == "Quota dépassé"
    assert errors[1].startswith("Erreur inattendue")


# --- controller ----------------------------------------------------------------------


def test_controller_loads_report_and_tracks(controller: AppController) -> None:
    report = _load(controller)
    assert report.code == REPORT_CODE
    _add(controller, report, ROGUE_ID)
    assert controller.track_state(ROGUE_REF) == TrackState.LOADED
    assert len(controller.workspace.entries[0].track.casts) == 338
    controller.remove_track(ROGUE_REF)
    assert controller.workspace.entries == []


def test_controller_refuses_another_boss(controller: AppController) -> None:
    report = _load(controller)
    _add(controller, report, ROGUE_ID)
    errors: list[str] = []
    controller.error.connect(errors.append)
    _add(controller, report, ROGUE_ID, fight_id=15)
    assert len(controller.workspace.entries) == 1
    assert "autre boss" in errors[0]


def test_unticking_during_download_cancels_the_track(fake_wcl: FakeWcl) -> None:
    runner = DeferredRunner()
    controller = AppController(runner, client_factory=fake_wcl.client)
    controller.load_report(URL)
    runner.flush()
    report = controller.cached_report(parse_report_reference(URL))
    assert report is not None
    _add(controller, report, ROGUE_ID)
    assert controller.track_state(ROGUE_REF) == TrackState.LOADING
    controller.remove_track(ROGUE_REF)
    runner.flush()
    assert controller.workspace.entries == []
    assert controller.track_state(ROGUE_REF) is None


def test_invalid_url_is_reported(controller: AppController) -> None:
    errors: list[str] = []
    controller.error.connect(errors.append)
    controller.load_report("https://lorrgs.io/")
    assert errors and "Warcraft Logs" in errors[0]


# --- Log panel -----------------------------------------------------------------------


def test_log_panel_preselects_fight_and_player(
    qtbot: QtBot, controller: AppController, settings: AppSettings
) -> None:
    panel = LogPanel(controller, settings)
    qtbot.addWidget(panel)
    panel.input.setEditText(f"{URL}#fight=7&source={ROGUE_ID}")
    panel.load()
    assert [e.ref for e in controller.workspace.entries] == [ROGUE_REF]
    tops = [panel.players.topLevelItem(i) for i in range(panel.players.topLevelItemCount())]
    groups = [item.text(0) for item in tops if item is not None]
    assert groups == ["Tanks (2)", "Heals (4)", "DPS (14)"]
    names = {item.text(0) for item in panel._player_items()}
    assert "Vénéfique" in names
    assert "Absentéïste" not in names
    assert settings.recent_reports[0][0] == REPORT_CODE


def test_log_panel_shortcuts(
    qtbot: QtBot, controller: AppController, settings: AppSettings
) -> None:
    panel = LogPanel(controller, settings)
    qtbot.addWidget(panel)
    panel.input.setEditText(f"{URL}#fight=7")
    panel.load()
    panel.my_spec_button.click()  # Rogue-Assassination
    assert [e.ref.source_id for e in controller.workspace.entries] == [ROGUE_ID]
    settings.player_name = "Givrâme"
    panel.me_button.click()
    assert {e.ref.source_id for e in controller.workspace.entries} == {ROGUE_ID, MAGE_ID}
    panel.search.setText("givr")
    visible = [i.text(0) for i in panel._player_items() if not i.isHidden()]
    assert visible == ["Givrâme"]


def test_log_panel_asks_before_switching_boss(
    qtbot: QtBot,
    controller: AppController,
    settings: AppSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panel = LogPanel(controller, settings)
    qtbot.addWidget(panel)
    panel.input.setEditText(f"{URL}#fight=7&source={ROGUE_ID}")
    panel.load()
    panel.kills_only.setChecked(False)
    panel._select_fight(15)  # Entombed Sentinels wipe

    answers = [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes]
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: answers.pop(0))
    item = next(i for i in panel._player_items() if i.data(0, ID_ROLE) == ROGUE_ID)
    item.setCheckState(0, Qt.CheckState.Checked)
    assert [e.ref.fight_id for e in controller.workspace.entries] == [7]
    assert item.checkState(0) == Qt.CheckState.Unchecked
    item.setCheckState(0, Qt.CheckState.Checked)
    assert [e.ref.fight_id for e in controller.workspace.entries] == [15]


# --- legend, timeline, tracks ---------------------------------------------------------


def test_legend_unticking_removes_the_spell(
    qtbot: QtBot, controller: AppController, icons: IconProvider
) -> None:
    legend = LegendPanel(controller, icons)
    qtbot.addWidget(legend)
    _add(controller, _load(controller), ROGUE_ID)
    items = [legend.list.item(i) for i in range(legend.list.count())]
    vanish = next(i for i in items if i is not None and i.data(SPELL_ID_ROLE) == VANISH)
    assert vanish.checkState() == Qt.CheckState.Checked
    vanish.setCheckState(Qt.CheckState.Unchecked)
    assert not controller.workspace.selection.is_included(VANISH)
    legend.show_all.setChecked(True)
    assert controller.workspace.selection.show_all
    assert legend.list.count() > len(items)


def test_timeline_draws_and_toggles_casts(
    qtbot: QtBot, controller: AppController, icons: IconProvider
) -> None:
    view = TimelineView(controller, icons)
    qtbot.addWidget(view)
    view.resize(1400, 300)
    view.show()
    qtbot.waitExposed(view)
    _add(controller, _load(controller), ROGUE_ID)
    entry = controller.workspace.entries[0]
    items = view.cast_items()
    assert len(items) == len(controller.workspace.displayed_casts(entry)) == 14

    target = min(items, key=lambda item: item.cast.time_ms)
    pos = view.mapFromScene(target.sceneBoundingRect().center())
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    assert controller.workspace.selection.is_disabled(entry.ref, target.cast)

    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(LABEL_WIDTH // 2, 60))
    assert len(controller.workspace.selection.disabled_casts) == 1

    for _ in range(30):
        view.zoom_in()
    assert view.px_per_s == MAX_PX_PER_S


def test_tracks_panel_lists_and_removes(qtbot: QtBot, controller: AppController) -> None:
    panel = TracksPanel(controller)
    qtbot.addWidget(panel)
    assert panel.table.rowCount() == 0
    report = _load(controller)
    _add(controller, report, ROGUE_ID)
    _add(controller, report, MAGE_ID)
    assert panel.table.rowCount() == 2
    controller.set_visible(ROGUE_REF, False)
    assert [e.ref for e in controller.workspace.visible_entries()] == [
        TrackRef(REPORT_CODE, 7, MAGE_ID)
    ]
    panel.clear_button.click()
    assert panel.table.rowCount() == 0


# --- copy note dialog, main window ------------------------------------------------------


def test_copy_note_dialog_matches_the_note_service(
    qtbot: QtBot, controller: AppController, settings: AppSettings
) -> None:
    _add(controller, _load(controller), ROGUE_ID)
    dialog = CopyNoteDialog(controller, settings)
    qtbot.addWidget(dialog)
    assignments = controller.workspace.note_assignments([(ROGUE_REF, DEFAULT_PLAYER_NAME)])
    assert dialog.preview.toPlainText() == build_note(assignments, NoteOptions()).text

    dialog.nsrt.setChecked(True)
    dialog.dur.setValue(5)
    nsrt = build_note(assignments, NoteOptions(NoteFormat.NSRT, dur=5)).text
    assert dialog.preview.toPlainText() == nsrt
    assert "approximatives" in dialog.warnings.text()

    dialog.copy()
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    assert clipboard.text() == nsrt
    assert settings.note_format == "nsrt"
    assert settings.nsrt_dur == 5


def test_copy_note_dialog_raid_note(
    qtbot: QtBot, controller: AppController, settings: AppSettings
) -> None:
    report = _load(controller)
    _add(controller, report, ROGUE_ID)
    _add(controller, report, MAGE_ID)
    dialog = CopyNoteDialog(controller, settings)
    qtbot.addWidget(dialog)
    dialog.raid_mode.setChecked(True)
    name = dialog.raid_table.item(1, 2)
    assert name is not None
    name.setText("Zoë")
    text = dialog.preview.toPlainText()
    assert "Vénéfique {spell:" in text
    assert "Zoë {spell:" in text


@pytest.mark.parametrize(
    ("text", "expected"), [("5:26", 326_000), (" 0:59 ", 59_000), ("5:60", None), ("abc", None)]
)
def test_parse_kill_time(text: str, expected: int | None) -> None:
    assert parse_kill_time(text) == expected


def test_main_window_smoke(
    qtbot: QtBot, controller: AppController, settings: AppSettings, icons: IconProvider
) -> None:
    window = MainWindow(controller, settings, icons, TaskRunner(synchronous=True))
    qtbot.addWidget(window)
    assert not window.copy_action.isEnabled()
    _add(controller, _load(controller), ROGUE_ID)
    assert window.copy_action.isEnabled()


def test_icon_provider_uses_the_disk_cache(tmp_path: Path) -> None:
    cache = tmp_path / "icons"
    cache.mkdir()
    pixmap = QPixmap(56, 56)
    pixmap.fill(QColor("red"))
    pixmap.save(str(cache / "ability_rogue_deathmark.jpg"), "JPG")
    provider = IconProvider(TaskRunner(synchronous=True), cache, download=False)
    icon = provider.pixmap("ability_rogue_deathmark.jpg", 28)
    assert icon.width() == 28
    assert icon.toImage().pixelColor(14, 14).red() > 200
    placeholder = provider.pixmap("missing.jpg", 28)
    assert placeholder.toImage().pixelColor(14, 14).red() < 200
    assert provider.pixmap("../evil.jpg", 28).cacheKey() == placeholder.cacheKey()


# --- rankings ------------------------------------------------------------------------


@pytest.fixture
def rankings_panel(
    qtbot: QtBot, controller: AppController, settings: AppSettings, icons: IconProvider
) -> RankingsPanel:
    panel = RankingsPanel(controller, settings, icons)
    qtbot.addWidget(panel)
    panel.ensure_catalog()
    return panel


def test_rankings_panel_prefills_my_spec(rankings_panel: RankingsPanel) -> None:
    assert rankings_panel.raid.currentText() == "The Venomous Abyss"
    assert rankings_panel.boss.count() == 10
    assert rankings_panel.game_class.currentData() == "Rogue"
    assert rankings_panel.spec.currentData() == "Assassination"
    assert rankings_panel.difficulty.currentData() == 5
    assert rankings_panel.metric_box.currentData() == "dps"
    holy = rankings_panel.game_class.findData("Paladin")
    rankings_panel.game_class.setCurrentIndex(holy)
    rankings_panel.spec.setCurrentIndex(rankings_panel.spec.findData("Holy"))
    assert rankings_panel.metric_box.currentData() == "hps"


def test_rankings_search_filter_and_pages(rankings_panel: RankingsPanel, fake_wcl: FakeWcl) -> None:
    rankings_panel.boss.setCurrentIndex(rankings_panel.boss.findData(3470))
    rankings_panel.search()
    assert rankings_panel.table.topLevelItemCount() == 12
    first = rankings_panel.table.topLevelItem(0)
    assert first is not None and first.text(0) == "1"

    rankings_panel.min_kill.setText("5:00")
    rankings_panel.max_kill.setText("5:30")
    shown = [e.duration_ms for e in rankings_panel.visible_entries()]
    assert shown and all(300_000 <= d <= 330_000 for d in shown)
    rankings_panel.sort.setCurrentIndex(rankings_panel.sort.findData("duration"))
    assert shown != [] and [e.duration_ms for e in rankings_panel.visible_entries()] == sorted(
        shown
    )

    assert rankings_panel.more_button.isEnabled()
    rankings_panel.load_more()
    assert not rankings_panel.more_button.isEnabled()
    assert [v["page"] for name, v in fake_wcl.calls if name == "CharacterRankings"] == [1, 2]


def test_ticking_a_ranking_adds_its_track(
    rankings_panel: RankingsPanel, controller: AppController
) -> None:
    rankings_panel.boss.setCurrentIndex(rankings_panel.boss.findData(3470))
    rankings_panel.search()
    item = next(
        i
        for i in (rankings_panel.table.topLevelItem(n) for n in range(12))
        if i is not None and "Vénéfique" in i.text(1)
    )
    item.setCheckState(0, Qt.CheckState.Checked)
    entry = controller.workspace.entries[0]
    assert entry.ref == ROGUE_REF
    assert entry.origin == "Classement #3"
    assert item.text(5) == "✓"
    item.setCheckState(0, Qt.CheckState.Unchecked)
    assert controller.workspace.entries == []
