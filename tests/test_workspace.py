from dataclasses import replace

import pytest

from conftest import MAGE_ID, REPORT_CODE, FakeWcl, load_json
from wcl_notes.api.reports import fetch_player_roles, parse_player_roles
from wcl_notes.domain.models import Report, Role, Track, TrackRef
from wcl_notes.domain.spells import SpellCategory
from wcl_notes.services.notes import NoteAssignment, NoteFormat, NoteOptions, build_note
from wcl_notes.services.report_navigation import resolve_fight
from wcl_notes.services.selection import UNKNOWN_SPEC_MAX_CASTS
from wcl_notes.services.workspace import DifferentEncounterError, Workspace

DEATHMARK, KINGSBANE, VANISH, VORACIOUS_HEART = 360194, 385627, 1856, 1297761
MUTILATE, ICE_LANCE, TIME_WARP = 1329, 30455, 80353


@pytest.fixture
def workspace(report: Report, rogue_track: Track) -> Workspace:
    ws = Workspace()
    ws.add(rogue_track, spells=report.spells, origin="Log")
    return ws


def test_rogue_defaults_come_from_the_spec_file(workspace: Workspace) -> None:
    assert workspace.selection.included_spells == {DEATHMARK, KINGSBANE, VANISH, VORACIOUS_HEART}


def test_unknown_spec_preselects_rarely_cast_spells(report: Report, mage_track: Track) -> None:
    # An actor whose icon has no spec ("Mage") has no spell list.
    no_spec = replace(mage_track, player=replace(mage_track.player, icon="Mage"))
    ws = Workspace()
    ws.add(no_spec, spells=report.spells)
    included = ws.selection.included_spells
    assert TIME_WARP in included
    assert ICE_LANCE not in included
    counts = {s: sum(c.spell_id == s for c in mage_track.casts) for s in included}
    assert all(n <= UNKNOWN_SPEC_MAX_CASTS for n in counts.values())


def test_one_boss_per_timeline(workspace: Workspace, rogue_track: Track, report: Report) -> None:
    other_boss = replace(rogue_track, fight=resolve_fight(report, 15))
    assert not workspace.accepts(other_boss.fight.encounter_id)
    with pytest.raises(DifferentEncounterError):
        workspace.add(other_boss, spells=report.spells)


def test_adding_twice_keeps_one_track(workspace: Workspace, rogue_track: Track) -> None:
    again = workspace.add(rogue_track, spells={})
    assert again is workspace.entries[0]
    assert len(workspace.entries) == 1


def test_tracks_get_distinct_colors(
    workspace: Workspace, mage_track: Track, report: Report
) -> None:
    workspace.add(mage_track, spells=report.spells)
    assert len({e.color for e in workspace.entries}) == 2


def test_legend_lists_important_spells_first(workspace: Workspace) -> None:
    legend = workspace.legend()
    assert legend[0].category is SpellCategory.OFFENSIVE
    ids = [e.spell.id for e in legend]
    assert MUTILATE not in ids  # filler, not in the spec file
    deathmark = next(e for e in legend if e.spell.id == DEATHMARK)
    assert (deathmark.spell.name, deathmark.count, deathmark.included) == ("Deathmark", 3, True)


def test_show_all_lists_every_cast_spell(workspace: Workspace) -> None:
    workspace.selection.show_all = True
    ids = {e.spell.id for e in workspace.legend()}
    assert MUTILATE in ids
    mutilate = next(e for e in workspace.legend() if e.spell.id == MUTILATE)
    assert not mutilate.included


def test_toggling_a_spell_hides_it_and_removes_it_from_the_note(workspace: Workspace) -> None:
    entry = workspace.entries[0]
    assert workspace.selection.toggle_spell(VANISH) is False
    assert VANISH not in {c.spell_id for c in workspace.displayed_casts(entry)}
    assert VANISH not in {c.spell_id for c in workspace.selection.note_casts(entry.track)}


def test_disabling_one_cast(workspace: Workspace) -> None:
    entry = workspace.entries[0]
    first_deathmark = next(c for c in entry.track.casts if c.spell_id == DEATHMARK)
    assert workspace.selection.toggle_cast(entry.ref, first_deathmark) is False
    note_casts = workspace.selection.note_casts(entry.track)
    assert first_deathmark not in note_casts
    assert sum(c.spell_id == DEATHMARK for c in note_casts) == 2
    assert first_deathmark in workspace.displayed_casts(entry)  # still drawn, dimmed
    assert workspace.selection.toggle_cast(entry.ref, first_deathmark) is True


def test_removing_a_track_forgets_its_disabled_casts(workspace: Workspace) -> None:
    entry = workspace.entries[0]
    workspace.selection.toggle_cast(entry.ref, entry.track.casts[0])
    workspace.remove(entry.ref)
    assert workspace.entries == []
    assert workspace.selection.disabled_casts == set()
    assert workspace.encounter_id is None


def test_clear_keeps_the_show_all_switch(workspace: Workspace) -> None:
    workspace.selection.show_all = True
    workspace.clear()
    assert workspace.selection.show_all
    assert workspace.selection.included_spells == set()


def test_raid_note_mrt_merges_players(
    workspace: Workspace, mage_track: Track, report: Report
) -> None:
    workspace.add(mage_track, spells=report.spells)
    rogue_ref = workspace.entries[0].ref
    mage_ref = TrackRef(REPORT_CODE, 7, MAGE_ID)
    assignments = workspace.note_assignments([(rogue_ref, "Kràùck"), (mage_ref, "Zoë")])
    lines = build_note(assignments, NoteOptions()).text.splitlines()
    assert any("Kràùck {spell:360194}" in line for line in lines)
    assert any(f"Zoë {{spell:{TIME_WARP}}}" in line for line in lines)
    times = [line.split("}", 1)[0] for line in lines]
    assert times == sorted(times)  # MM:SS.d sorts chronologically


def test_raid_note_nsrt(workspace: Workspace, mage_track: Track, report: Report) -> None:
    workspace.add(mage_track, spells=report.spells)
    targets = [(e.ref, n) for e, n in zip(workspace.entries, ["Kràùck", "Zoë"], strict=True)]
    result = build_note(workspace.note_assignments(targets), NoteOptions(NoteFormat.NSRT))
    lines = result.text.splitlines()
    assert lines[0] == "EncounterID:3470;Name:Nek'zali the Soulcoiler;Difficulty:Mythic"
    phases = [float(line.split(";ph:")[1].split(";")[0]) for line in lines[1:]]
    assert phases == sorted(phases)
    assert {line.split(";")[0] for line in lines[1:]} == {"tag:Kràùck", "tag:Zoë"}
    assert len(result.infos) == 2
    assert any("approximatives" in w for w in result.warnings)


def test_kill_time_warning(rogue_track: Track) -> None:
    assignment = NoteAssignment(rogue_track, rogue_track.casts[:3], "Kràùck")
    far = build_note([assignment], NoteOptions(my_kill_ms=300_000))
    assert any("5:52 contre 5:00" in w for w in far.warnings)
    close = build_note([assignment], NoteOptions(my_kill_ms=350_000))
    assert close.warnings == ()


def test_a_note_covers_a_single_boss(rogue_track: Track, report: Report) -> None:
    other = replace(rogue_track, fight=resolve_fight(report, 15))
    with pytest.raises(ValueError, match="un seul boss"):
        build_note(
            [NoteAssignment(rogue_track, [], "A"), NoteAssignment(other, [], "B")],
            NoteOptions(),
        )


def test_player_roles() -> None:
    raw = load_json("player_details_cmw7_f7.json")["data"]["reportData"]["report"]["playerDetails"]
    roles = parse_player_roles(raw)
    assert [pid for pid, r in roles.items() if r is Role.TANK] == [115, 5]
    assert sum(r is Role.HEALER for r in roles.values()) == 4
    assert roles[126] is Role.DPS
    assert parse_player_roles(None) == {}
    assert parse_player_roles({"data": {"playerDetails": {"tanks": "oops"}}}) == {}


def test_fetch_player_roles(fake_wcl: FakeWcl, report: Report) -> None:
    with fake_wcl.client() as client:
        roles = fetch_player_roles(client, REPORT_CODE, resolve_fight(report, 7))
    assert len(roles) == 20
    assert fake_wcl.calls == [("PlayerDetails", {"code": REPORT_CODE, "fightID": 7})]


def test_note_merges_double_logged_casts(rogue_track: Track) -> None:
    deathmark = next(c for c in rogue_track.casts if c.spell_id == DEATHMARK)
    echo = replace(deathmark, time_ms=deathmark.time_ms + 100)
    assignment = NoteAssignment(rogue_track, [deathmark, echo], "Kràùck")
    assert len(build_note([assignment], NoteOptions()).text.splitlines()) == 1
    unmerged = build_note([assignment], NoteOptions(merge_window_ms=0))
    assert len(unmerged.text.splitlines()) == 2
