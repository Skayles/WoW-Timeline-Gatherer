from dataclasses import replace

import pytest

from conftest import REPORT_CODE, ROGUE_ID, FakeWcl
from wcl_notes.api.rankings import fetch_catalog, fetch_rankings, parse_rankings
from wcl_notes.domain.models import Report
from wcl_notes.domain.rankings import RankingEntry, RankingQuery
from wcl_notes.services.rankings import (
    RankingSort,
    default_metric,
    filter_rankings,
    find_ranked_player,
    sort_rankings,
)
from wcl_notes.services.report_navigation import NavigationError, resolve_fight

QUERY = RankingQuery(
    encounter_id=3470, difficulty=5, class_name="Rogue", spec="Assassination", metric="dps"
)


def _entry(rank: int, name: str, duration_s: int, day: int) -> RankingEntry:
    return RankingEntry(
        rank=rank,
        name=name,
        class_name="Rogue",
        spec="Assassination",
        amount=200_000,
        duration_ms=duration_s * 1000,
        start_time=1_790_000_000_000 + day * 86_400_000,
        report_code="x" * 16,
        fight_id=1,
    )


ENTRIES = [_entry(1, "Alpha", 300, 1), _entry(2, "Bràvo", 280, 3), _entry(3, "Charlie", 330, 2)]


def test_catalog(fake_wcl: FakeWcl) -> None:
    with fake_wcl.client() as client:
        catalog = fetch_catalog(client)
    assert [name for name, _ in fake_wcl.calls] == ["GameCatalog", "RaidZones"]
    assert fake_wcl.calls[1][1] == {"expansionID": 7}  # latest expansion: Midnight
    assert [z.name for z in catalog.raids] == [
        "The Venomous Abyss",  # current tier first, then older raids, newest first
        "Sporefall",
        "VS / DR / MQD",
    ]  # Mythic+ zones left out
    assert len(catalog.raids[0].encounters) == 10
    rogue = next(c for c in catalog.classes if c.slug == "Rogue")
    assert [s.slug for s in rogue.specs] == ["Assassination", "Subtlety", "Outlaw"]
    hunter = next(c for c in catalog.classes if c.slug == "Hunter")
    assert hunter.specs[0].name == "Beast Mastery"
    assert hunter.specs[0].slug == "BeastMastery"


def test_rankings_page(fake_wcl: FakeWcl) -> None:
    with fake_wcl.client() as client:
        page = fetch_rankings(client, QUERY)
    variables = fake_wcl.calls[0][1]
    assert variables["className"] == "Rogue"
    assert variables["serverRegion"] == ""
    assert page.has_more
    assert len(page.entries) == 12
    third = page.entries[2]
    assert (third.rank, third.name, third.server, third.region) == (3, "Vénéfique", "Ysondre", "EU")
    assert (third.report_code, third.fight_id, third.duration_ms) == (REPORT_CODE, 7, 352_392)
    assert third.icon == "Rogue-Assassination"


def test_second_page_ranks_continue() -> None:
    raw = {"hasMorePages": False, "rankings": [_raw("Zed")]}
    page = parse_rankings(raw, replace(QUERY, page=2))
    assert page.entries[0].rank == 101
    assert not page.has_more


def test_invalid_entries_are_skipped() -> None:
    raw = {"rankings": [{"name": "broken"}, _raw("Ok"), "garbage"]}
    assert [e.name for e in parse_rankings(raw, QUERY).entries] == ["Ok"]
    assert parse_rankings(None, QUERY).entries == ()


def _raw(name: str) -> dict[str, object]:
    return {
        "name": name,
        "class": "Rogue",
        "spec": "Assassination",
        "amount": 1.0,
        "duration": 300000,
        "startTime": 1790000000000,
        "report": {"code": "y" * 16, "fightID": 3},
        "server": {"name": "Hyjal", "region": "EU"},
    }


def test_filter_by_kill_time_and_name() -> None:
    assert [e.name for e in filter_rankings(ENTRIES, min_duration_ms=290_000)] == [
        "Alpha",
        "Charlie",
    ]
    assert [e.name for e in filter_rankings(ENTRIES, max_duration_ms=300_000)] == [
        "Alpha",
        "Bràvo",
    ]
    assert [e.name for e in filter_rankings(ENTRIES, name="brà")] == ["Bràvo"]


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (RankingSort.RANK, ["Alpha", "Bràvo", "Charlie"]),
        (RankingSort.DURATION, ["Bràvo", "Alpha", "Charlie"]),
        (RankingSort.DATE, ["Bràvo", "Charlie", "Alpha"]),
    ],
)
def test_sort(key: RankingSort, expected: list[str]) -> None:
    assert [e.name for e in sort_rankings(ENTRIES, key)] == expected


def test_default_metric() -> None:
    assert default_metric("Assassination") == "dps"
    assert default_metric("Holy") == "hps"
    assert default_metric("Preservation") == "hps"


def test_find_ranked_player(report: Report) -> None:
    fight = resolve_fight(report, 7)
    entry = replace(ENTRIES[0], name="Vénéfique", report_code=REPORT_CODE, fight_id=7)
    assert find_ranked_player(report, fight, entry).id == ROGUE_ID
    with pytest.raises(NavigationError):
        find_ranked_player(report, fight, replace(entry, name="Absentéïste"))
