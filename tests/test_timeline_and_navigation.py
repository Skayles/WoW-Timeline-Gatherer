import pytest

from conftest import ROGUE_ID
from wcl_notes.domain.models import Actor, CastEvent, CastKind, Fight, Report
from wcl_notes.domain.names import character_name
from wcl_notes.services.report_navigation import (
    NavigationError,
    boss_fights,
    find_player,
    players_in_fight,
    resolve_fight,
)
from wcl_notes.services.timeline import build_casts, spell_counts

FIGHT = Fight(
    id=1, encounter_id=3470, name="Boss", difficulty=5, kill=True, start_ms=10_000, end_ms=70_000
)


def _event(
    timestamp: int, spell_id: int, kind: CastKind = CastKind.CAST, *, fake: bool = False
) -> CastEvent:
    return CastEvent(timestamp=timestamp, kind=kind, source_id=7, spell_id=spell_id, fake=fake)


def test_build_casts_is_pull_relative_and_sorted() -> None:
    events = [_event(15_000, 2), _event(9_000, 1), _event(10_000, 3)]
    casts = build_casts(events, FIGHT)
    assert [(c.time_ms, c.spell_id) for c in casts] == [(-1_000, 1), (0, 3), (5_000, 2)]


def test_build_casts_filters_begincast_and_fake_by_default() -> None:
    events = [
        _event(11_000, 1, CastKind.BEGIN_CAST),
        _event(12_000, 1),
        _event(12_000, 2, fake=True),
    ]
    assert [c.spell_id for c in build_casts(events, FIGHT)] == [1]
    with_all = build_casts(events, FIGHT, include_begincast=True, include_fake=True)
    assert len(with_all) == 3


def test_spell_counts() -> None:
    casts = build_casts([_event(11_000, 1), _event(12_000, 1), _event(13_000, 2)], FIGHT)
    assert spell_counts(casts).most_common() == [(1, 2), (2, 1)]


def test_boss_fights_skip_trash_and_mythic_plus(report: Report) -> None:
    assert [f.id for f in boss_fights(report)] == [7, 15, 25]
    assert [f.id for f in boss_fights(report, kills_only=True)] == [7, 25]


def test_resolve_fight(report: Report) -> None:
    assert resolve_fight(report, "last").id == 25
    assert resolve_fight(report, 15).id == 15
    with pytest.raises(NavigationError):
        resolve_fight(report, 999)


def test_find_player_by_name_or_id(report: Report) -> None:
    players = players_in_fight(report, resolve_fight(report, 7))
    assert find_player(players, "Vénéfique").id == ROGUE_ID
    assert find_player(players, "vénéfique").id == ROGUE_ID
    assert find_player(players, str(ROGUE_ID)).name == "Vénéfique"
    assert find_player(players, ROGUE_ID).name == "Vénéfique"
    with pytest.raises(NavigationError):
        find_player(players, "Venefique")  # accents are significant
    with pytest.raises(NavigationError):
        find_player(players, "Absentéïste")  # in the report, not in the fight


def test_actor_spec_from_icon() -> None:
    def player(icon: str | None) -> Actor:
        return Actor(id=1, name="X", type="Player", sub_type="Rogue", icon=icon)

    assert player("Rogue-Assassination").spec == "Assassination"
    assert player("Rogue").spec is None
    assert player(None).spec is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [("Kràùck", "Kràùck"), ("Kràùck-Ysondre", "Kràùck"), (" Kràùck-Kirin Tor ", "Kràùck")],
)
def test_character_name_drops_realm_and_keeps_accents(name: str, expected: str) -> None:
    assert character_name(name) == expected
