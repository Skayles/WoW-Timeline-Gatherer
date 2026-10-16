import pytest

from conftest import ROGUE_ID, load_json, read_golden
from wcl_notes.api.reports import parse_cast_events
from wcl_notes.domain.models import Cast, Report
from wcl_notes.exporters.mrt import export_mrt, format_mrt_time
from wcl_notes.services.report_navigation import resolve_fight
from wcl_notes.services.timeline import build_casts

DEATHMARK, KINGSBANE, VANISH = 360194, 385627, 1856


@pytest.mark.parametrize(
    ("time_ms", "expected"),
    [
        (0, "00:00.0"),
        (857, "00:00.9"),
        (1249, "00:01.2"),
        (1250, "00:01.3"),
        (59_949, "00:59.9"),
        (59_950, "01:00.0"),
        (605_149, "10:05.1"),
        (3_600_000, "60:00.0"),
        (-1_500, "00:00.0"),
    ],
)
def test_format_mrt_time(time_ms: int, expected: str) -> None:
    assert format_mrt_time(time_ms) == expected


def _cast(time_ms: int, spell_id: int) -> Cast:
    return Cast(time_ms=time_ms, spell_id=spell_id, source_id=1)


def test_edge_cases_golden() -> None:
    casts = [
        _cast(605_149, 5),
        _cast(-1_500, 1),
        _cast(1_250, 3),
        _cast(0, 2),
        _cast(3_600_000, 6),
        _cast(59_960, 4),
    ]
    note = export_mrt(casts, "Kràùck-Ysondre")
    assert note + "\n" == read_golden("mrt_edge_cases.txt")


def test_offset_moves_casts_earlier_and_clamps_at_pull() -> None:
    note = export_mrt([_cast(3_000, 1), _cast(18_900, 2)], "Kràùck", offset_ms=5_000)
    assert note.splitlines() == [
        "{time:00:00.0} - Kràùck {spell:1}",
        "{time:00:13.9} - Kràùck {spell:2}",
    ]


def test_empty_selection_gives_empty_note() -> None:
    assert export_mrt([], "Kràùck") == ""


def test_rogue_cooldowns_golden(report: Report) -> None:
    fight = resolve_fight(report, 7)
    events = parse_cast_events(
        load_json("casts_cmw7_f7_s126.json")["data"]["reportData"]["report"]["events"]["data"]
    )
    casts = [
        c
        for c in build_casts(events, fight)
        if c.source_id == ROGUE_ID and c.spell_id in {DEATHMARK, KINGSBANE, VANISH}
    ]
    assert export_mrt(casts, "Kràùck") + "\n" == read_golden("mrt_rogue_cooldowns.txt")
