"""Top logs (WCL character rankings) and the catalog used to pick them."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GameSpec:
    name: str
    """Display name ("Beast Mastery")."""
    slug: str
    """Name expected by the rankings API and used in actor icons ("BeastMastery")."""


@dataclass(frozen=True, slots=True)
class GameClass:
    id: int
    name: str
    slug: str
    specs: tuple[GameSpec, ...]


@dataclass(frozen=True, slots=True)
class EncounterRef:
    id: int
    name: str


@dataclass(frozen=True, slots=True)
class RaidZone:
    id: int
    name: str
    frozen: bool
    encounters: tuple[EncounterRef, ...]
    difficulties: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class GameCatalog:
    classes: tuple[GameClass, ...]
    raids: tuple[RaidZone, ...]


@dataclass(frozen=True, slots=True)
class RankingQuery:
    encounter_id: int
    difficulty: int
    class_name: str
    spec: str
    metric: str
    region: str | None = None
    page: int = 1


@dataclass(frozen=True, slots=True)
class RankingEntry:
    rank: int
    name: str
    class_name: str
    spec: str
    amount: float
    duration_ms: int
    start_time: int
    """Unix timestamp (ms) of the kill."""
    report_code: str
    fight_id: int
    server: str | None = None
    region: str | None = None
    guild: str | None = None

    @property
    def icon(self) -> str:
        return f"{self.class_name}-{self.spec}"


@dataclass(frozen=True, slots=True)
class RankingsPage:
    query: RankingQuery
    entries: tuple[RankingEntry, ...]
    has_more: bool
