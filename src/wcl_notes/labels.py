"""Labels shared by the CLI and the UI, translated with ``tr`` (no Qt here)."""

from wcl_notes.domain.models import Actor, Fight, Role
from wcl_notes.domain.spells import SpellCategory
from wcl_notes.i18n import tr

# French source texts; always displayed through the functions below.
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
    return tr(DIFFICULTY_LABELS.get(difficulty, str(difficulty)))


def role_label(role: Role) -> str:
    return tr(ROLE_LABELS[role])


def category_label(category: SpellCategory | None) -> str:
    return tr(CATEGORY_LABELS[category] if category else OTHER_CATEGORY_LABEL)


def format_duration(ms: int) -> str:
    minutes, seconds = divmod(round(ms / 1000), 60)
    return f"{minutes}:{seconds:02d}"


def spec_label(actor: Actor) -> str:
    return f"{actor.sub_type} {actor.spec}" if actor.spec else actor.sub_type


def outcome_label(fight: Fight) -> str:
    if fight.kill:
        return "kill"
    if fight.boss_percentage is not None:
        return tr("wipe ({percent:.1f} %)").format(percent=fight.boss_percentage)
    return "wipe"


def fight_label(fight: Fight) -> str:
    outcome = "kill" if fight.kill else "wipe"
    return (
        f"{fight.name} ({difficulty_label(fight.difficulty)}, {outcome}, "
        f"{format_duration(fight.duration_ms)})"
    )
