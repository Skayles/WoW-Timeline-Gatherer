"""High-level WCL fetches, mapped from pydantic responses to domain models."""

from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from wcl_notes.api.client import WclClient
from wcl_notes.api.errors import ReportNotFoundError, WclApiError
from wcl_notes.api.models import (
    CastEventModel,
    EventsQueryModel,
    FightModel,
    ReportModel,
    ReportQueryModel,
)
from wcl_notes.domain.models import (
    Actor,
    CastEvent,
    CastKind,
    Fight,
    FightPet,
    PhaseInfo,
    PhaseTransition,
    Report,
    Spell,
)

_MAX_PAGES = 200
_CAST_KINDS = {kind.value: kind for kind in CastKind}


def fetch_report(client: WclClient, code: str) -> Report:
    data = client.execute("report", {"code": code})
    report = ReportQueryModel.model_validate(data).report_data.report
    if report is None:
        raise ReportNotFoundError("Ce report n'existe pas : vérifiez le code ou l'URL.")
    return report_from_model(report)


def fetch_player_casts(
    client: WclClient, code: str, fight: Fight, source_id: int
) -> list[CastEvent]:
    """Casts of one player. WCL's ``Casts`` data type leaves out pets."""
    return _fetch_paginated(client, "player_casts", code, fight, source_id)


def fetch_pet_casts(client: WclClient, code: str, fight: Fight, pet_id: int) -> list[CastEvent]:
    return _fetch_paginated(client, "pet_casts", code, fight, pet_id)


def _fetch_paginated(
    client: WclClient, query_name: str, code: str, fight: Fight, source_id: int
) -> list[CastEvent]:
    events: list[CastEvent] = []
    start: float = fight.start_ms
    for _ in range(_MAX_PAGES):
        data = client.execute(
            query_name,
            {
                "code": code,
                "fightID": fight.id,
                "sourceID": source_id,
                "startTime": start,
                "endTime": fight.end_ms,
            },
        )
        report = EventsQueryModel.model_validate(data).report_data.report
        if report is None or report.events is None:
            raise ReportNotFoundError("Ce report n'existe pas : vérifiez le code ou l'URL.")
        events.extend(parse_cast_events(report.events.data))
        next_page = report.events.next_page_timestamp
        if next_page is None:
            return events
        if next_page <= start:
            raise WclApiError("Pagination des événements WCL bloquée (timestamp non croissant).")
        start = next_page
    raise WclApiError(f"Trop de pages d'événements (plus de {_MAX_PAGES}).")


def parse_cast_events(raw_events: Iterable[dict[str, Any]]) -> list[CastEvent]:
    """Keep ``cast`` / ``begincast`` events; ignore anything else WCL may return."""
    events: list[CastEvent] = []
    for raw in raw_events:
        kind = _CAST_KINDS.get(str(raw.get("type")))
        if kind is None:
            continue
        try:
            model = CastEventModel.model_validate(raw)
        except ValidationError:
            continue
        events.append(
            CastEvent(
                timestamp=round(model.timestamp),
                kind=kind,
                source_id=model.source_id,
                spell_id=model.ability_game_id,
                fake=model.fake,
            )
        )
    return events


def report_from_model(model: ReportModel) -> Report:
    master = model.master_data
    actors = {
        a.id: Actor(
            id=a.id,
            name=a.name or f"#{a.id}",
            type=a.type or "",
            sub_type=a.sub_type or "",
            server=a.server,
            icon=a.icon,
            pet_owner=a.pet_owner,
        )
        for a in (master.actors or [] if master else [])
        if a is not None and a.id is not None
    }
    spells = {
        int(a.game_id): Spell(id=int(a.game_id), name=a.name or str(int(a.game_id)), icon=a.icon)
        for a in (master.abilities or [] if master else [])
        if a is not None and a.game_id is not None
    }
    phases = {
        p.encounter_id: tuple(
            PhaseInfo(id=m.id, name=m.name, is_intermission=bool(m.is_intermission))
            for m in p.phases or []
        )
        for p in model.phases or []
    }
    return Report(
        code=model.code,
        title=model.title,
        start_time=round(model.start_time),
        fights=tuple(_fight_from_model(f) for f in model.fights or [] if f is not None),
        actors=actors,
        spells=spells,
        phases=phases,
    )


def _fight_from_model(f: FightModel) -> Fight:
    return Fight(
        id=f.id,
        encounter_id=f.encounter_id,
        name=f.name,
        difficulty=f.difficulty,
        kill=f.kill,
        start_ms=round(f.start_time),
        end_ms=round(f.end_time),
        boss_percentage=f.boss_percentage,
        player_ids=tuple(f.friendly_players or ()),
        pets=tuple(
            FightPet(id=p.id, owner_id=p.pet_owner)
            for p in f.friendly_pets or []
            if p.pet_owner is not None
        ),
        phase_transitions=tuple(
            PhaseTransition(phase_id=t.id, start_ms=round(t.start_time))
            for t in f.phase_transitions or []
        ),
    )
