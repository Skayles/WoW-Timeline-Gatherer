"""Spells worth putting in a note, per spec (``data/spells/<class>_<spec>.yaml``)."""

from dataclasses import dataclass
from enum import StrEnum


class SpellCategory(StrEnum):
    OFFENSIVE = "offensive"
    DEFENSIVE = "defensive"
    RAID_CD = "raid_cd"
    UTILITY = "utility"
    MOVEMENT = "movement"
    CONSUMABLE = "consumable"
    TRINKET = "trinket"


@dataclass(frozen=True, slots=True)
class ImportantSpell:
    id: int
    name: str
    category: SpellCategory
    selected_by_default: bool = False
    cooldown: float | None = None
    """Base cooldown in seconds, when verified; informative only."""


@dataclass(frozen=True, slots=True)
class SpecSpells:
    class_name: str
    spec: str
    spells: tuple[ImportantSpell, ...]

    def default_ids(self) -> frozenset[int]:
        return frozenset(s.id for s in self.spells if s.selected_by_default)
