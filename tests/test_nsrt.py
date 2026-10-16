import pytest

from conftest import ROGUE_ID, load_json, read_golden
from wcl_notes.api.reports import parse_cast_events
from wcl_notes.domain.models import PhasedCast, Report
from wcl_notes.exporters.nsrt import (
    NsrtHeader,
    export_nsrt,
    format_nsrt_phase,
    format_nsrt_time,
)
from wcl_notes.services.data_files import nsrt_mapping
from wcl_notes.services.phases import nsrt_segments, phase_casts
from wcl_notes.services.report_navigation import resolve_fight
from wcl_notes.services.timeline import build_casts

HEADER = NsrtHeader(3470, "Nek'zali the Soulcoiler", "Mythic")


@pytest.mark.parametrize(
    ("time_ms", "expected"),
    [
        (0, "0.0"),
        (1_250, "1.3"),
        (1_249, "1.2"),
        (22_200, "22.2"),
        (605_149, "605.1"),
        (-2_500, "-2.5"),
        (-20, "0.0"),
    ],
)
def test_format_nsrt_time(time_ms: int, expected: str) -> None:
    assert format_nsrt_time(time_ms) == expected


@pytest.mark.parametrize(
    ("phase", "expected"), [(1, "1"), (2.0, "2"), (1.5, "1.5"), (1.75, "1.75")]
)
def test_format_nsrt_phase(phase: float, expected: str) -> None:
    assert format_nsrt_phase(phase) == expected


def test_line_format_follows_the_native_writer() -> None:
    note = export_nsrt([PhasedCast(1.5, 13_300, 385627, 1)], "Kràùck-Ysondre", HEADER, dur=5)
    assert note.splitlines() == [
        "EncounterID:3470;Name:Nek'zali the Soulcoiler;Difficulty:Mythic",
        "tag:Kràùck;time:13.3;spellid:385627;ph:1.5;dur:5",
    ]


def test_dur_and_difficulty_are_optional() -> None:
    note = export_nsrt([PhasedCast(1, 1_300, 1, 1)], "Kràùck", NsrtHeader(3455, "Vashnik"))
    assert note.splitlines() == [
        "EncounterID:3455;Name:Vashnik",
        "tag:Kràùck;time:1.3;spellid:1;ph:1",
    ]


def test_separators_never_leak_into_values() -> None:
    note = export_nsrt([], "Krà;ùck", NsrtHeader(1, "Boss; with\nnewline"))
    assert note == "EncounterID:1;Name:Boss with newline"


def test_rogue_on_nekzali_golden(report: Report) -> None:
    fight = resolve_fight(report, 7)
    events = parse_cast_events(
        load_json("casts_cmw7_f7_s126.json")["data"]["reportData"]["report"]["events"]["data"]
    )
    casts = [
        c
        for c in build_casts(events, fight)
        if c.source_id == ROGUE_ID and c.spell_id in {360194, 385627, 1856}
    ]
    segments = nsrt_segments(fight, nsrt_mapping(fight.encounter_id))
    note = export_nsrt(phase_casts(casts, segments), "Kràùck", HEADER)
    assert note + "\n" == read_golden("nsrt_rogue_nekzali.txt")
