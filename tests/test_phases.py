from conftest import FIGHT_7_START
from wcl_notes.domain.encounters import (
    IDENTITY_MAPPING,
    MappingStatus,
    NsrtPhaseMapping,
    PhaseStrategy,
)
from wcl_notes.domain.models import Cast, Fight, PhasedCast, PhaseTransition, Report
from wcl_notes.services.data_files import nsrt_mapping
from wcl_notes.services.phases import PhaseSegment, nsrt_segments, phase_casts
from wcl_notes.services.report_navigation import resolve_fight

SINGLE = NsrtPhaseMapping(PhaseStrategy.SINGLE, MappingStatus.VERIFIED)


def _segments(segments: tuple[PhaseSegment, ...]) -> list[tuple[float, int]]:
    return [(s.phase, s.start_ms) for s in segments]


def test_map_strategy_nekzali(report: Report) -> None:
    fight = resolve_fight(report, 7)
    segments = nsrt_segments(fight, nsrt_mapping(fight.encounter_id))
    assert _segments(segments) == [(1, 0), (1.5, 3322113 - FIGHT_7_START), (2, 230_845)]


def test_count_strategy_entombed_counts_returns_to_stage_one(report: Report) -> None:
    fight = resolve_fight(report, 15)  # WCL: 1, 2, 1, 2, 1, 2, 1, 2, 1
    segments = nsrt_segments(fight, nsrt_mapping(fight.encounter_id))
    starts = [t.start_ms - fight.start_ms for t in fight.phase_transitions if t.phase_id == 1]
    assert _segments(segments) == [(1, 0), *[(n, at) for n, at in enumerate(starts[1:], 2)]]
    assert [s.phase for s in segments] == [1, 2, 3, 4, 5]


def test_count_strategy_ignores_other_phases() -> None:
    explorers = nsrt_mapping(3497)
    fight = _fight([(1, 0), (3, 60_800), (1, 120_800), (2, 185_700), (1, 245_700)])
    assert _segments(nsrt_segments(fight, explorers)) == [(1, 0), (2, 60_800), (3, 185_700)]


def test_single_strategy_ignores_wcl_phases(report: Report) -> None:
    assert _segments(nsrt_segments(resolve_fight(report, 15), SINGLE)) == [(1, 0)]


def test_boss_without_transitions(report: Report) -> None:
    fight = resolve_fight(report, 25)
    assert _segments(nsrt_segments(fight, IDENTITY_MAPPING)) == [(1, 0)]


def test_identity_mapping_for_unknown_boss() -> None:
    fight = _fight([(1, 0), (2, 10_000), (1, 20_000)])
    assert _segments(nsrt_segments(fight, IDENTITY_MAPPING)) == [(1, 0), (2, 10_000), (1, 20_000)]


def test_map_strategy_merges_transitions_to_the_same_nsrt_phase() -> None:
    mapping = NsrtPhaseMapping(PhaseStrategy.MAP, MappingStatus.VERIFIED, phases={1: 1, 2: 1, 3: 2})
    fight = _fight([(1, 0), (2, 10_000), (3, 20_000)])
    assert _segments(nsrt_segments(fight, mapping)) == [(1, 0), (2, 20_000)]


def test_cast_exactly_on_a_transition_belongs_to_the_new_phase() -> None:
    segments = (PhaseSegment(1, 0), PhaseSegment(2, 60_000))
    phased = phase_casts([_cast(60_000), _cast(59_999)], segments)
    assert phased == [PhasedCast(1, 59_999, 7, 1), PhasedCast(2, 0, 7, 1)]


def test_offset_is_clamped_at_the_phase_start() -> None:
    segments = (PhaseSegment(1, 0), PhaseSegment(2, 60_000))
    phased = phase_casts([_cast(62_000), _cast(70_000), _cast(1_000)], segments, offset_ms=5_000)
    assert [(c.phase, c.time_ms) for c in phased] == [(1, 0), (2, 0), (2, 5_000)]


def test_pre_pull_cast_stays_negative_in_phase_one() -> None:
    segments = (PhaseSegment(1, 0), PhaseSegment(2, 60_000))
    assert phase_casts([_cast(-2_500)], segments) == [PhasedCast(1, -2_500, 7, 1)]


def test_cast_late_in_long_fight() -> None:
    segments = (PhaseSegment(1, 0), PhaseSegment(2, 400_000))
    assert phase_casts([_cast(655_300)], segments) == [PhasedCast(2, 255_300, 7, 1)]


def _cast(time_ms: int) -> Cast:
    return Cast(time_ms=time_ms, spell_id=7, source_id=1)


def _fight(transitions: list[tuple[int, int]]) -> Fight:
    start = 1_000_000
    return Fight(
        id=1,
        encounter_id=1,
        name="Boss",
        difficulty=5,
        kill=True,
        start_ms=start,
        end_ms=start + 600_000,
        phase_transitions=tuple(PhaseTransition(pid, start + at) for pid, at in transitions),
    )
