"""Pure domain models: no Qt, no httpx, no pydantic.

Times suffixed ``_ms`` are integer milliseconds. Fight and phase timestamps are
relative to the start of the report (WCL convention); cast times on a track are
relative to the pull.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum


class Difficulty(IntEnum):
    LFR = 1
    NORMAL = 3
    HEROIC = 4
    MYTHIC = 5


class CastKind(StrEnum):
    BEGIN_CAST = "begincast"
    CAST = "cast"


@dataclass(frozen=True, slots=True)
class Actor:
    id: int
    name: str
    type: str  # "Player", "NPC" or "Pet"
    sub_type: str  # class for players ("Mage"), "Boss" / "NPC" for NPCs
    server: str | None = None
    icon: str | None = None  # "Class-Spec" for players ("Mage-Frost"), sometimes just "Class"
    pet_owner: int | None = None

    @property
    def is_player(self) -> bool:
        return self.type == "Player"

    @property
    def spec(self) -> str | None:
        if not self.is_player or not self.icon or "-" not in self.icon:
            return None
        return self.icon.split("-", 1)[1]


@dataclass(frozen=True, slots=True)
class Spell:
    id: int
    name: str
    icon: str | None = None


@dataclass(frozen=True, slots=True)
class PhaseInfo:
    id: int
    name: str
    is_intermission: bool


@dataclass(frozen=True, slots=True)
class PhaseTransition:
    phase_id: int
    """WCL phase ID; the same ID repeats when a boss alternates phases."""
    start_ms: int


@dataclass(frozen=True, slots=True)
class FightPet:
    id: int
    owner_id: int


@dataclass(frozen=True, slots=True)
class Fight:
    id: int
    encounter_id: int
    """0 for trash fights."""
    name: str
    difficulty: int | None
    kill: bool | None
    start_ms: int
    end_ms: int
    boss_percentage: float | None = None
    player_ids: tuple[int, ...] = ()
    pets: tuple[FightPet, ...] = ()
    phase_transitions: tuple[PhaseTransition, ...] = ()

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def is_boss(self) -> bool:
        return self.encounter_id != 0


@dataclass(frozen=True, slots=True)
class Report:
    code: str
    title: str
    start_time: int
    """Unix timestamp (ms) of the start of the report."""
    fights: tuple[Fight, ...]
    actors: Mapping[int, Actor]
    spells: Mapping[int, Spell]
    phases: Mapping[int, tuple[PhaseInfo, ...]]
    """Phase metadata by encounter ID."""


@dataclass(frozen=True, slots=True)
class CastEvent:
    """A cast as returned by WCL, timestamp relative to the report start."""

    timestamp: int
    kind: CastKind
    source_id: int
    spell_id: int
    fake: bool = False
    """WCL synthesises some casts (e.g. off-hand Mutilate); they duplicate real ones."""


@dataclass(frozen=True, slots=True)
class Cast:
    """A cast on a track, time relative to the pull (negative = pre-pull)."""

    time_ms: int
    spell_id: int
    source_id: int
    kind: CastKind = CastKind.CAST


@dataclass(frozen=True, slots=True)
class TrackRef:
    report_code: str
    fight_id: int
    source_id: int


@dataclass(frozen=True, slots=True)
class Track:
    ref: TrackRef
    player: Actor
    fight: Fight
    casts: tuple[Cast, ...]
