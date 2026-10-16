"""Northern Sky Raid Tools note, as parsed by ``NSI:ProcessReminder`` (Reminders.lua).

    EncounterID:3470;Name:Nek'zali the Soulcoiler;Difficulty:Mythic
    tag:Kràùck;time:22.3;spellid:360194;ph:1;dur:5

Header and field order follow NSRT's own writer (NorthernSkyRaidTools_UI/Timeline.lua).
``time`` is relative to the start of ``ph``, never to the pull.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from wcl_notes.domain.models import PhasedCast
from wcl_notes.domain.names import character_name

NSRT_DIFFICULTY = {1: "LFR", 3: "Normal", 4: "Heroic", 5: "Mythic"}


@dataclass(frozen=True, slots=True)
class NsrtHeader:
    encounter_id: int
    name: str
    difficulty: str | None = None


def format_nsrt_time(time_ms: int) -> str:
    """Seconds with one decimal, rounded half away from zero; negative = pre-pull."""
    tenths = (abs(time_ms) + 50) // 100
    sign = "-" if time_ms < 0 and tenths else ""
    return f"{sign}{tenths // 10}.{tenths % 10}"


def format_nsrt_phase(phase: float) -> str:
    return str(int(phase)) if phase.is_integer() else f"{phase:g}"


def _clean(value: str) -> str:
    # NSRT splits fields on ";" and reminders on newlines.
    return " ".join(value.replace(";", " ").split())


def export_nsrt(
    casts: Iterable[PhasedCast],
    player_name: str,
    header: NsrtHeader,
    *,
    dur: int | None = None,
) -> str:
    """Casts are written in the order given (chronological from ``phase_casts``)."""
    first = f"EncounterID:{header.encounter_id};Name:{_clean(header.name)}"
    if header.difficulty:
        first += f";Difficulty:{header.difficulty}"
    tag = _clean(character_name(player_name))
    lines = [first]
    for cast in casts:
        fields = [
            f"tag:{tag}",
            f"time:{format_nsrt_time(cast.time_ms)}",
            f"spellid:{cast.spell_id}",
            f"ph:{format_nsrt_phase(cast.phase)}",
        ]
        if dur is not None:
            fields.append(f"dur:{dur}")
        lines.append(";".join(fields))
    return "\n".join(lines)
