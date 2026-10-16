"""How NSRT numbers the phases of a boss, compared to WCL phase transitions.

NSRT detects phases at runtime with per-boss heuristics (``DetectPhaseChange`` in
``EncounterAlerts/<season>/<Boss>.lua``); its numbering often differs from WCL's.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class PhaseStrategy(StrEnum):
    SINGLE = "single"
    """NSRT never changes phase on this boss: every reminder is ph 1, timed from the pull."""
    MAP = "map"
    """Each WCL phase ID maps to an NSRT phase (unmapped IDs keep their own number)."""
    COUNT = "count"
    """NSRT adds 1 to its phase on each WCL transition into one of ``count_on``."""


class MappingStatus(StrEnum):
    VERIFIED = "verified"
    APPROXIMATE = "approximate"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class NsrtPhaseMapping:
    strategy: PhaseStrategy
    status: MappingStatus
    phases: Mapping[int, float] = field(default_factory=dict)
    count_on: frozenset[int] = frozenset()
    note: str = ""


IDENTITY_MAPPING = NsrtPhaseMapping(
    strategy=PhaseStrategy.MAP,
    status=MappingStatus.UNVERIFIED,
    note=(
        "Aucun mapping vérifié pour ce boss : les numéros de phase WCL sont repris tels quels. "
        "Vérifiez en jeu que NSRT change bien de phase aux mêmes moments."
    ),
)


@dataclass(frozen=True, slots=True)
class EncounterInfo:
    encounter_id: int
    name: str
    nsrt: NsrtPhaseMapping
