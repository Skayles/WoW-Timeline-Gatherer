from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from conftest import REPORT_CODE, ROGUE_ID, FakeWcl
from wcl_notes.domain.models import Track
from wcl_notes.domain.spells import SpellPreset
from wcl_notes.services.presets import apply_preset, merge_preset, preset_key, seen_spells
from wcl_notes.services.report_navigation import resolve_fight
from wcl_notes.ui.controller import AppController
from wcl_notes.ui.settings import AppSettings
from wcl_notes.ui.workers import TaskRunner

DEATHMARK, KINGSBANE, VANISH, CLOAK, MUTILATE = 360194, 385627, 1856, 31224, 1329


def test_preset_key(rogue_track: Track, mage_track: Track) -> None:
    assert preset_key(rogue_track) == (3470, "Rogue-Assassination")
    assert preset_key(mage_track) == (3470, "Mage-Frost")


def test_apply_preset() -> None:
    defaults = {DEATHMARK, VANISH}
    cast = {DEATHMARK, VANISH, CLOAK, MUTILATE}
    assert apply_preset(defaults, None, cast) == {DEATHMARK, VANISH}
    preset = SpellPreset(include=frozenset({CLOAK, 999}), exclude=frozenset({VANISH}))
    assert apply_preset(defaults, preset, cast) == {DEATHMARK, CLOAK}


def test_merge_keeps_choices_about_spells_not_seen_this_time() -> None:
    first = merge_preset(None, included={DEATHMARK, CLOAK}, seen={DEATHMARK, VANISH, CLOAK})
    assert first == SpellPreset(frozenset({DEATHMARK, CLOAK}), frozenset({VANISH}))
    # Next log: no Cloak cast, Vanish ticked again.
    second = merge_preset(first, included={DEATHMARK, VANISH}, seen={DEATHMARK, VANISH})
    assert second.include == {DEATHMARK, VANISH, CLOAK}
    assert second.exclude == frozenset()


def test_seen_spells_groups_by_spec(rogue_track: Track, mage_track: Track) -> None:
    seen = seen_spells([rogue_track, mage_track])
    assert set(seen) == {(3470, "Rogue-Assassination"), (3470, "Mage-Frost")}
    assert DEATHMARK in seen[(3470, "Rogue-Assassination")]


@pytest.fixture
def settings(tmp_path: Path) -> AppSettings:
    return AppSettings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))


def _add_rogue(controller: AppController) -> None:
    reports = []
    controller.report_loaded.connect(lambda report, _ref: reports.append(report))
    controller.load_report(REPORT_CODE)
    report = reports[-1]
    controller.add_track(report, resolve_fight(report, 7), report.actors[ROGUE_ID], "test")


def test_choices_are_remembered_per_boss_and_spec(
    qtbot: QtBot, fake_wcl: FakeWcl, settings: AppSettings
) -> None:
    controller = AppController(
        TaskRunner(synchronous=True), client_factory=fake_wcl.client, presets=settings
    )
    _add_rogue(controller)
    assert controller.workspace.selection.is_included(VANISH)
    controller.set_spell_included(VANISH, False)
    controller.set_spell_included(CLOAK, True)
    stored = settings.get_preset((3470, "Rogue-Assassination"))
    assert stored is not None
    assert VANISH in stored.exclude and CLOAK in stored.include

    controller.clear()
    _add_rogue(controller)
    selection = controller.workspace.selection
    assert not selection.is_included(VANISH)
    assert selection.is_included(CLOAK)
    assert selection.is_included(DEATHMARK)

    controller.reset_selection()
    assert selection.is_included(VANISH)
    assert not selection.is_included(CLOAK)
    assert settings.get_preset((3470, "Rogue-Assassination")) is None


def test_corrupted_preset_is_ignored(settings: AppSettings) -> None:
    settings._settings.setValue("presets/3470/Rogue-Assassination", "{not json")
    assert settings.get_preset((3470, "Rogue-Assassination")) is None
