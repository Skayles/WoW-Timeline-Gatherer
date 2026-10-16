"""Filter and sort top logs, and find the ranked player inside the report."""

import unicodedata
from collections.abc import Iterable
from enum import StrEnum

from wcl_notes.domain.models import Actor, Fight, Report
from wcl_notes.domain.rankings import RankingEntry
from wcl_notes.services.report_navigation import NavigationError, players_in_fight

# WCL has no role on specs: healers are known by name (Holy covers Paladin and Priest).
HEALER_SPECS = frozenset({"Restoration", "Holy", "Discipline", "Mistweaver", "Preservation"})
METRICS = ("dps", "hps")


class RankingSort(StrEnum):
    RANK = "rank"
    DURATION = "duration"
    DATE = "date"


def default_metric(spec: str) -> str:
    return "hps" if spec in HEALER_SPECS else "dps"


def filter_rankings(
    entries: Iterable[RankingEntry],
    *,
    min_duration_ms: int | None = None,
    max_duration_ms: int | None = None,
    name: str = "",
) -> list[RankingEntry]:
    """Keep kills within a duration range (to match my raid's kill time) and by name."""
    needle = name.strip().casefold()
    return [
        e
        for e in entries
        if (min_duration_ms is None or e.duration_ms >= min_duration_ms)
        and (max_duration_ms is None or e.duration_ms <= max_duration_ms)
        and (not needle or needle in e.name.casefold())
    ]


def sort_rankings(entries: Iterable[RankingEntry], key: RankingSort) -> list[RankingEntry]:
    if key is RankingSort.DURATION:
        return sorted(entries, key=lambda e: (e.duration_ms, e.rank))
    if key is RankingSort.DATE:
        return sorted(entries, key=lambda e: (-e.start_time, e.rank))
    return sorted(entries, key=lambda e: e.rank)


def _server_key(server: str | None) -> str:
    """Realm names are written with or without spaces, hyphens and apostrophes."""
    text = unicodedata.normalize("NFKD", server or "")
    return "".join(c for c in text.casefold() if c.isalnum())


def find_ranked_player(report: Report, fight: Fight, entry: RankingEntry) -> Actor:
    """Rankings give a name and a realm, not an actor ID: match them in the fight."""
    same_name = [p for p in players_in_fight(report, fight) if p.name == entry.name]
    if not same_name:
        raise NavigationError(
            f"{entry.name} introuvable dans le fight #{fight.id} du report {report.code}."
        )
    if len(same_name) == 1:
        return same_name[0]
    realm = _server_key(entry.server)
    same_realm = [p for p in same_name if _server_key(p.server) == realm]
    if len(same_realm) == 1:
        return same_realm[0]
    raise NavigationError(
        f"Plusieurs joueurs nommés {entry.name} dans ce fight : impossible de choisir."
    )
