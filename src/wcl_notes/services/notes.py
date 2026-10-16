"""Build an MRT or NSRT note from one track, or several tracks of the same boss."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from wcl_notes.domain.encounters import MappingStatus
from wcl_notes.domain.models import Cast, PhasedCast, Track
from wcl_notes.domain.names import character_name
from wcl_notes.exporters.mrt import export_mrt_entries, format_mrt_time
from wcl_notes.exporters.nsrt import (
    NSRT_DIFFICULTY,
    NsrtHeader,
    export_nsrt_entries,
    format_nsrt_phase,
)
from wcl_notes.services.data_files import nsrt_mapping
from wcl_notes.services.phases import nsrt_segments, phase_casts

KILL_TIME_TOLERANCE = 0.10
MAPPING_STATUS_LABELS = {
    MappingStatus.APPROXIMATE: "phases NSRT approximatives",
    MappingStatus.UNVERIFIED: "phases NSRT non vérifiées",
}


class NoteFormat(StrEnum):
    MRT = "mrt"
    NSRT = "nsrt"


@dataclass(frozen=True, slots=True)
class NoteOptions:
    format: NoteFormat = NoteFormat.MRT
    offset_ms: int = 0
    dur: int | None = None
    my_kill_ms: int | None = None
    """Kill time of my raid, to warn when a source kill is much shorter or longer."""


@dataclass(frozen=True, slots=True)
class NoteAssignment:
    track: Track
    casts: Sequence[Cast]
    player_name: str
    """Name written in the note instead of the source player."""


@dataclass(frozen=True, slots=True)
class NoteResult:
    text: str
    warnings: tuple[str, ...] = ()
    infos: tuple[str, ...] = ()


def build_note(assignments: Sequence[NoteAssignment], options: NoteOptions) -> NoteResult:
    if not assignments:
        return NoteResult(text="")
    if len({a.track.fight.encounter_id for a in assignments}) > 1:
        raise ValueError("Une note ne peut couvrir qu'un seul boss.")

    warnings = _kill_time_warnings(assignments, options.my_kill_ms)
    if options.format is NoteFormat.MRT:
        entries = [(a.player_name, c) for a in assignments for c in a.casts]
        return NoteResult(
            text=export_mrt_entries(entries, offset_ms=options.offset_ms),
            warnings=tuple(warnings),
        )

    fight = assignments[0].track.fight
    mapping = nsrt_mapping(fight.encounter_id)
    infos: list[str] = []
    phased: list[tuple[str, PhasedCast]] = []
    for assignment in assignments:
        segments = nsrt_segments(assignment.track.fight, mapping)
        label = "Phases NSRT"
        if len(assignments) > 1:
            label += f" ({character_name(assignment.track.player.name)})"
        phases = ", ".join(
            f"{format_nsrt_phase(s.phase)} à {format_mrt_time(s.start_ms)}" for s in segments
        )
        infos.append(f"{label} : {phases}")
        phased.extend(
            (assignment.player_name, cast)
            for cast in phase_casts(assignment.casts, segments, offset_ms=options.offset_ms)
        )
    if len(assignments) > 1:
        phased.sort(key=lambda entry: (entry[1].phase, entry[1].time_ms))
    if mapping.status is not MappingStatus.VERIFIED:
        warnings.append(f"{MAPPING_STATUS_LABELS[mapping.status]} : {mapping.note}")

    header = NsrtHeader(
        encounter_id=fight.encounter_id,
        name=fight.name,
        difficulty=NSRT_DIFFICULTY.get(fight.difficulty) if fight.difficulty else None,
    )
    return NoteResult(
        text=export_nsrt_entries(phased, header, dur=options.dur),
        warnings=tuple(warnings),
        infos=tuple(infos),
    )


def _kill_time_warnings(assignments: Sequence[NoteAssignment], my_kill_ms: int | None) -> list[str]:
    if not my_kill_ms or my_kill_ms <= 0:
        return []
    warnings = []
    for assignment in assignments:
        source_ms = assignment.track.fight.duration_ms
        if abs(source_ms - my_kill_ms) / my_kill_ms > KILL_TIME_TOLERANCE:
            warnings.append(
                f"Le kill de {character_name(assignment.track.player.name)} dure "
                f"{_mm_ss(source_ms)} contre {_mm_ss(my_kill_ms)} pour votre raid : "
                "adaptez les timings."
            )
    return warnings


def _mm_ss(ms: int) -> str:
    minutes, seconds = divmod(round(ms / 1000), 60)
    return f"{minutes}:{seconds:02d}"
