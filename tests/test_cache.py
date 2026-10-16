from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from conftest import MAGE_ID, REPORT_CODE, FakeWcl
from wcl_notes.api.client import WclClient
from wcl_notes.api.credentials import Credentials
from wcl_notes.api.rankings import fetch_rankings
from wcl_notes.api.reports import (
    LIVE_REPORT_CACHE,
    fetch_player_casts,
    fetch_report,
    report_cache_rule,
)
from wcl_notes.cache.response_cache import ResponseCache
from wcl_notes.domain.models import Report
from wcl_notes.domain.rankings import RankingQuery
from wcl_notes.services.report_navigation import resolve_fight

HOUR = 3600.0


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def cache(tmp_path: Path, clock: Clock) -> ResponseCache:
    return ResponseCache(tmp_path / "cache.sqlite", clock=clock)


def _client(fake_wcl: FakeWcl, cache: ResponseCache) -> WclClient:
    http = httpx.Client(transport=httpx.MockTransport(fake_wcl.handle))
    return WclClient(Credentials("id", "secret"), http=http, cache=cache)


def test_put_get_and_expiry(cache: ResponseCache, clock: Clock) -> None:
    cache.put("forever", "report", {"name": "Kràùck"}, None)
    cache.put("hour", "rankings", {"n": 1}, HOUR)
    assert cache.get("forever") == {"name": "Kràùck"}
    assert cache.get("hour") == {"n": 1}
    assert cache.get("missing") is None
    clock.now += HOUR + 1
    assert cache.get("hour") is None
    assert cache.get("forever") == {"name": "Kràùck"}
    assert cache.prune() == 1
    assert cache.stats().entries == 1


def test_clear_and_stats(cache: ResponseCache) -> None:
    cache.put("a", "q", {"x": "y" * 1000}, None)
    stats = cache.stats()
    assert stats.entries == 1
    assert 0 < stats.size_bytes < 1000  # compressed
    cache.clear()
    assert cache.stats().entries == 0


def test_key_depends_on_query_text_and_variables() -> None:
    key = ResponseCache.make_key("query A", {"code": "x", "fightID": 7})
    assert key == ResponseCache.make_key("query A", {"fightID": 7, "code": "x"})
    assert key != ResponseCache.make_key("query B", {"code": "x", "fightID": 7})
    assert key != ResponseCache.make_key("query A", {"code": "x", "fightID": 8})


def test_corrupted_entry_is_a_miss(cache: ResponseCache) -> None:
    cache.put("k", "q", {"a": 1}, None)
    with cache._lock, cache._conn:
        cache._conn.execute("UPDATE responses SET payload = ?", (b"not zlib",))
    assert cache.get("k") is None


def test_cache_survives_reopening(tmp_path: Path) -> None:
    ResponseCache(tmp_path / "c.sqlite").put("k", "q", {"a": 1}, None)
    assert ResponseCache(tmp_path / "c.sqlite").get("k") == {"a": 1}


def test_report_rule() -> None:
    finished = {"reportData": {"report": {"endTime": 1_000_000}}}
    assert report_cache_rule(finished, now_s=1_000 + 3 * HOUR).ttl_s is None
    assert report_cache_rule(finished, now_s=1_000 + 0.5 * HOUR) == LIVE_REPORT_CACHE
    assert report_cache_rule({}, now_s=0) == LIVE_REPORT_CACHE


def test_second_load_costs_nothing(fake_wcl: FakeWcl, cache: ResponseCache) -> None:
    with _client(fake_wcl, cache) as client:
        first = fetch_report(client, REPORT_CODE)
        second = fetch_report(client, REPORT_CODE)
        assert client.cache_hits == 1
    assert first == second
    assert len(fake_wcl.calls) == 1


def test_offline_after_caching(fake_wcl: FakeWcl, cache: ResponseCache, report: Report) -> None:
    """Cached responses need neither a token nor the network."""
    fight = resolve_fight(report, 7)
    with _client(fake_wcl, cache) as client:
        fetch_player_casts(client, REPORT_CODE, fight, MAGE_ID)  # 4 pages
    offline = FakeWcl()
    offline.handlers.clear()
    with _client(offline, cache) as client:
        events = fetch_player_casts(client, REPORT_CODE, fight, MAGE_ID)
        assert client.cache_hits == 4
    assert len(events) == 341
    assert offline.token_requests == 0


def test_fight_in_progress_is_not_cached(
    fake_wcl: FakeWcl, cache: ResponseCache, report: Report
) -> None:
    live = replace(resolve_fight(report, 7), in_progress=True)
    with _client(fake_wcl, cache) as client:
        fetch_player_casts(client, REPORT_CODE, live, MAGE_ID)
        fetch_player_casts(client, REPORT_CODE, live, MAGE_ID)
        assert client.cache_hits == 0


def test_rankings_expire_after_an_hour(
    fake_wcl: FakeWcl, cache: ResponseCache, clock: Clock
) -> None:
    query = RankingQuery(3470, 5, "Rogue", "Assassination", "dps")
    with _client(fake_wcl, cache) as client:
        fetch_rankings(client, query)
        fetch_rankings(client, query)
        clock.now += HOUR + 1
        fetch_rankings(client, query)
    assert sum(name == "CharacterRankings" for name, _ in fake_wcl.calls) == 2


def test_errors_are_not_cached(fake_wcl: FakeWcl, cache: ResponseCache) -> None:
    fake_wcl.handlers["Report"] = lambda _: httpx.Response(429)
    with _client(fake_wcl, cache) as client, pytest.raises(Exception, match="Quota"):
        fetch_report(client, REPORT_CODE)
    assert cache.stats().entries == 0
