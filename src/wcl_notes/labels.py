"""French labels shared by the CLI and the UI (no Qt here)."""

from wcl_notes.domain.models import Actor, Fight, Role
from wcl_notes.domain.spells import SpellCategory

DIFFICULTY_LABELS = {1: "LFR", 3: "Normal", 4: "Héroïque", 5: "Mythique", 10: "Mythique+"}
ROLE_LABELS = {Role.TANK: "Tanks", Role.HEALER: "Heals", Role.DPS: "DPS"}
CATEGORY_LABELS = {
    SpellCategory.OFFENSIVE: "Offensifs",
    SpellCategory.RAID_CD: "CD de raid",
    SpellCategory.DEFENSIVE: "Défensifs",
    SpellCategory.CONSUMABLE: "Consommables",
    SpellCategory.TRINKET: "Bijoux",
    SpellCategory.UTILITY: "Utilitaires",
    SpellCategory.MOVEMENT: "Mouvement",
}
OTHER_CATEGORY_LABEL = "Autres sorts"


def difficulty_label(difficulty: int | None) -> str:
    if difficulty is None:
        return "?"
    return DIFFICULTY_LABELS.get(difficulty, str(difficulty))


def format_duration(ms: int) -> str:
    minutes, seconds = divmod(round(ms / 1000), 60)
    return f"{minutes}:{seconds:02d}"


def spec_label(actor: Actor) -> str:
    return f"{actor.sub_type} {actor.spec}" if actor.spec else actor.sub_type


def outcome_label(fight: Fight) -> str:
    if fight.kill:
        return "kill"
    if fight.boss_percentage is not None:
        return f"wipe ({fight.boss_percentage:.1f} %)"
    return "wipe"


def fight_label(fight: Fight) -> str:
    outcome = "kill" if fight.kill else "wipe"
    return (
        f"{fight.name} ({difficulty_label(fight.difficulty)}, {outcome}, "
        f"{format_duration(fight.duration_ms)})"
    )
