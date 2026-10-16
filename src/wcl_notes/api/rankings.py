"""WCL rankings and game catalog, mapped to domain models."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from wcl_notes.api.client import CacheRule, WclClient
from wcl_notes.api.errors import WclApiError
from wcl_notes.domain.rankings import (
    EncounterRef,
    GameCatalog,
    GameClass,
    GameSpec,
    RaidZone,
    RankingEntry,
    RankingQuery,
    RankingsPage,
)
from wcl_notes.i18n import tr

MYTHIC_PLUS_DIFFICULTY = 10
RANKINGS_PER_PAGE = 100
RANKINGS_CACHE = CacheRule(ttl_s=3600)  # rankings move: refresh after an hour
CATALOG_CACHE = CacheRule(ttl_s=24 * 3600)  # classes and raids change with a new tier


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class _RankedReport(_Loose):
    code: str
    fight_id: int = Field(alias="fightID")


class _RankedServer(_Loose):
    name: str | None = None
    region: str | None = None


class _RankedGuild(_Loose):
    name: str | None = None


class _RankingModel(_Loose):
    name: str
    class_name: str = Field(alias="class")
    spec: str
    amount: float
    duration: float
    start_time: float = Field(alias="startTime")
    report: _RankedReport
    server: _RankedServer | None = None
    guild: _RankedGuild | None = None


def fetch_catalog(client: WclClient) -> GameCatalog:
    """Classes/specs, and the raids of the latest expansion (current tier first)."""
    data = client.execute("game_catalog", {}, cache=CATALOG_CACHE)
    classes = parse_classes(((data.get("gameData") or {}).get("classes")) or [])
    expansions = ((data.get("worldData") or {}).get("expansions")) or []
    ids = [e["id"] for e in expansions if isinstance(e, dict) and isinstance(e.get("id"), int)]
    if not ids:
        raise WclApiError(tr("Warcraft Logs n'a renvoyé aucune extension."))
    zones = client.execute("raid_zones", {"expansionID": max(ids)}, cache=CATALOG_CACHE)
    raids = parse_raid_zones(((zones.get("worldData") or {}).get("zones")) or [])
    return GameCatalog(classes=classes, raids=raids)


def parse_classes(raw: list[Any]) -> tuple[GameClass, ...]:
    classes = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        specs = tuple(
            GameSpec(name=str(s["name"]), slug=str(s["slug"]))
            for s in item.get("specs") or []
            if isinstance(s, dict) and s.get("slug")
        )
        classes.append(
            GameClass(
                id=int(item["id"]), name=str(item["name"]), slug=str(item["slug"]), specs=specs
            )
        )
    return tuple(sorted(classes, key=lambda c: c.name))


def parse_raid_zones(raw: list[Any]) -> tuple[RaidZone, ...]:
    """Raids only (no Mythic+ zone), the current tier first."""
    raids = []
    for zone in raw:
        if not isinstance(zone, dict):
            continue
        difficulties = tuple(
            d["id"] for d in zone.get("difficulties") or [] if isinstance(d, dict) and "id" in d
        )
        if not difficulties or MYTHIC_PLUS_DIFFICULTY in difficulties:
            continue
        encounters = tuple(
            EncounterRef(id=int(e["id"]), name=str(e["name"]))
            for e in zone.get("encounters") or []
            if isinstance(e, dict)
        )
        if encounters:
            raids.append(
                RaidZone(
                    id=int(zone["id"]),
                    name=str(zone["name"]),
                    frozen=bool(zone.get("frozen")),
                    encounters=encounters,
                    difficulties=difficulties,
                )
            )
    return tuple(sorted(raids, key=lambda z: (z.frozen, -z.id)))


def fetch_rankings(client: WclClient, query: RankingQuery) -> RankingsPage:
    data = client.execute(
        "character_rankings",
        {
            "encounterID": query.encounter_id,
            "difficulty": query.difficulty,
            "className": query.class_name,
            "specName": query.spec,
            "metric": query.metric,
            "page": query.page,
            "serverRegion": query.region or "",
        },
        cache=RANKINGS_CACHE,
    )
    encounter = (data.get("worldData") or {}).get("encounter")
    if not isinstance(encounter, dict):
        raise WclApiError(
            tr("Boss {boss} inconnu de Warcraft Logs.").format(boss=query.encounter_id)
        )
    return parse_rankings(encounter.get("characterRankings"), query)


def parse_rankings(raw: Any, query: RankingQuery) -> RankingsPage:
    """``characterRankings`` is untyped JSON: invalid entries are skipped."""
    if not isinstance(raw, dict):
        return RankingsPage(query=query, entries=(), has_more=False)
    entries = []
    first_rank = (query.page - 1) * RANKINGS_PER_PAGE + 1
    for index, item in enumerate(raw.get("rankings") or []):
        try:
            model = _RankingModel.model_validate(item)
        except ValidationError:
            continue
        entries.append(
            RankingEntry(
                rank=first_rank + index,
                name=model.name,
                class_name=model.class_name,
                spec=model.spec,
                amount=model.amount,
                duration_ms=round(model.duration),
                start_time=round(model.start_time),
                report_code=model.report.code,
                fight_id=model.report.fight_id,
                server=model.server.name if model.server else None,
                region=model.server.region if model.server else None,
                guild=model.guild.name if model.guild else None,
            )
        )
    return RankingsPage(query=query, entries=tuple(entries), has_more=bool(raw.get("hasMorePages")))
