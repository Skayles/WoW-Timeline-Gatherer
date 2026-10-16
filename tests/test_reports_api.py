from conftest import (
    ABSENT_PLAYER_ID,
    FIGHT_7_START,
    FIRE_ELEMENTAL_ID,
    MAGE_ID,
    REPORT_CODE,
    ROGUE_ID,
    SHAMAN_ID,
    FakeWcl,
)
from wcl_notes.api.reports import (
    fetch_pet_casts,
    fetch_player_casts,
    fetch_report,
    parse_cast_events,
)
from wcl_notes.domain.models import CastKind, PhaseTransition, Report
from wcl_notes.services.report_navigation import pet_ids, players_in_fight, resolve_fight


def test_report_mapping(report: Report) -> None:
    assert report.code == REPORT_CODE
    assert [f.id for f in report.fights] == [2, 7, 15, 25]

    fight = resolve_fight(report, 7)
    assert fight.encounter_id == 3470
    assert fight.kill is True
    assert fight.start_ms == FIGHT_7_START
    assert fight.duration_ms == 352_392
    assert len(fight.player_ids) == 20

    rogue = report.actors[ROGUE_ID]
    assert rogue.name == "Vénéfique"
    assert (rogue.sub_type, rogue.spec) == ("Rogue", "Assassination")
    assert report.spells[360194].name == "Deathmark"


def test_trash_fight_has_no_encounter(report: Report) -> None:
    trash = resolve_fight(report, 2)
    assert trash.encounter_id == 0
    assert not trash.is_boss


def test_phase_transitions_and_metadata(report: Report) -> None:
    fight = resolve_fight(report, 7)
    assert [t.phase_id for t in fight.phase_transitions] == [1, 2, 3]
    assert fight.phase_transitions[0] == PhaseTransition(phase_id=1, start_ms=FIGHT_7_START)
    phases = report.phases[3470]
    assert [(p.id, p.is_intermission) for p in phases] == [(1, False), (2, True), (3, False)]

    # Entombed Sentinels alternates stage and intermission: WCL phase IDs repeat.
    alternating = resolve_fight(report, 15)
    assert [t.phase_id for t in alternating.phase_transitions] == [1, 2, 1, 2, 1, 2, 1, 2, 1]

    # Single-phase boss: WCL sends no transitions at all.
    assert resolve_fight(report, 25).phase_transitions == ()


def test_players_in_fight_excludes_players_absent_from_the_fight(report: Report) -> None:
    assert ABSENT_PLAYER_ID in report.actors
    players = players_in_fight(report, resolve_fight(report, 7))
    ids = {p.id for p in players}
    assert ABSENT_PLAYER_ID not in ids
    assert len(players) == 20
    assert all(p.is_player for p in players)


def test_pets_are_linked_to_their_owner(report: Report) -> None:
    assert pet_ids(resolve_fight(report, 7), SHAMAN_ID) == [FIRE_ELEMENTAL_ID, 152]


def test_fetch_report_through_the_client(fake_wcl: FakeWcl) -> None:
    with fake_wcl.client() as client:
        report = fetch_report(client, REPORT_CODE)
    assert len(report.fights) == 4
    assert fake_wcl.calls == [("Report", {"code": REPORT_CODE})]


def test_player_casts_follow_pagination(fake_wcl: FakeWcl, report: Report) -> None:
    fight = resolve_fight(report, 7)
    with fake_wcl.client() as client:
        events = fetch_player_casts(client, REPORT_CODE, fight, MAGE_ID)

    starts = [variables["startTime"] for _, variables in fake_wcl.calls]
    assert starts == [FIGHT_7_START, 3278876, 3388431, 3493504]
    assert all(variables["endTime"] == fight.end_ms for _, variables in fake_wcl.calls)
    assert len(events) == 341
    assert [e.timestamp for e in events] == sorted(e.timestamp for e in events)
    assert {e.source_id for e in events} == {MAGE_ID}
    assert fake_wcl.token_requests == 1


def test_fake_casts_are_flagged(fake_wcl: FakeWcl, report: Report) -> None:
    with fake_wcl.client() as client:
        events = fetch_player_casts(client, REPORT_CODE, resolve_fight(report, 7), ROGUE_ID)
    fake = [e for e in events if e.fake]
    assert len(events) == 466
    assert len(fake) == 128
    assert {e.spell_id for e in fake} == {27576}  # off-hand Mutilate


def test_pet_casts(fake_wcl: FakeWcl, report: Report) -> None:
    with fake_wcl.client() as client:
        events = fetch_pet_casts(client, REPORT_CODE, resolve_fight(report, 7), FIRE_ELEMENTAL_ID)
    assert fake_wcl.calls[0][0] == "PetCasts"
    assert {e.source_id for e in events} == {FIRE_ELEMENTAL_ID}
    meteor = 117588
    assert any(e.spell_id == meteor and e.kind is CastKind.CAST for e in events)
    assert any(e.kind is CastKind.BEGIN_CAST for e in events)


def test_parse_cast_events_ignores_other_event_types() -> None:
    raw = [
        {"timestamp": 10.0, "type": "cast", "sourceID": 1, "abilityGameID": 5},
        {"timestamp": 11.0, "type": "damage", "sourceID": 1, "abilityGameID": 5},
        {"timestamp": 12.0, "type": "begincast", "sourceID": 1, "abilityGameID": 6},
        {"timestamp": 13.0, "type": "cast", "sourceID": 1},
    ]
    events = parse_cast_events(raw)
    assert [(e.timestamp, e.kind, e.spell_id) for e in events] == [
        (10, CastKind.CAST, 5),
        (12, CastKind.BEGIN_CAST, 6),
    ]
