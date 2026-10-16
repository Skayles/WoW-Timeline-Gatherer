"""Convert pull-relative casts into NSRT phases (time relative to the phase start)."""

from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass

from wcl_notes.domain.encounters import NsrtPhaseMapping, PhaseStrategy
from wcl_notes.domain.models import Cast, Fight, PhasedCast


@dataclass(frozen=True, slots=True)
class PhaseSegment:
    phase: float
    start_ms: int
    """Pull-relative start of the NSRT phase."""


def nsrt_segments(fight: Fight, mapping: NsrtPhaseMapping) -> tuple[PhaseSegment, ...]:
    """NSRT phases of a fight, in order. NSRT always starts the pull in phase 1."""
    segments = [PhaseSegment(phase=1, start_ms=0)]
    if mapping.strategy is PhaseStrategy.SINGLE:
        return tuple(segments)

    for transition in fight.phase_transitions:
        at = max(transition.start_ms - fight.start_ms, 0)
        current = segments[-1]
        if mapping.strategy is PhaseStrategy.MAP:
            phase = mapping.phases.get(transition.phase_id, float(transition.phase_id))
            if phase == current.phase:
                continue
        else:
            # The first transition is the pull itself, not a phase change.
            if at == 0 or transition.phase_id not in mapping.count_on:
                continue
            phase = current.phase + 1
        segment = PhaseSegment(phase=phase, start_ms=at)
        if at == current.start_ms:
            segments[-1] = segment
        else:
            segments.append(segment)
    return tuple(segments)


def phase_casts(
    casts: Iterable[Cast], segments: tuple[PhaseSegment, ...], *, offset_ms: int = 0
) -> list[PhasedCast]:
    """Express each cast in the phase where it happened.

    A cast exactly on a transition belongs to the new phase. ``offset_ms`` moves the
    reminder earlier but never into the previous phase (NSRT clears reminders on each
    phase change), so it is clamped at the phase start. Pre-pull casts stay negative:
    NSRT turns them into pre-pull reminders in phase 1.
    """
    starts = [s.start_ms for s in segments]
    phased: list[PhasedCast] = []
    for cast in sorted(casts, key=lambda c: c.time_ms):
        segment = segments[max(bisect_right(starts, cast.time_ms) - 1, 0)]
        if cast.time_ms < 0:
            time_ms = cast.time_ms - offset_ms
        else:
            time_ms = max(cast.time_ms - segment.start_ms - offset_ms, 0)
        phased.append(
            PhasedCast(
                phase=segment.phase,
                time_ms=time_ms,
                spell_id=cast.spell_id,
                source_id=cast.source_id,
            )
        )
    return phased
