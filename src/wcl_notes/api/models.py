"""Pydantic models of WCL responses. ``extra="ignore"`` survives new WCL fields."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class WclModel(BaseModel):
    model_config = ConfigDict(extra="ignore", alias_generator=to_camel, frozen=True)


# --- report ------------------------------------------------------------------


class PhaseTransitionModel(WclModel):
    id: int
    start_time: float


class FightPetModel(WclModel):
    id: int
    pet_owner: int | None = None


class FightModel(WclModel):
    id: int
    encounter_id: int = Field(alias="encounterID")
    name: str
    difficulty: int | None = None
    kill: bool | None = None
    in_progress: bool | None = None
    start_time: float
    end_time: float
    boss_percentage: float | None = None
    friendly_players: list[int] | None = None
    friendly_pets: list[FightPetModel] | None = None
    phase_transitions: list[PhaseTransitionModel] | None = None


class PhaseMetadataModel(WclModel):
    id: int
    name: str
    is_intermission: bool | None = None


class EncounterPhasesModel(WclModel):
    encounter_id: int = Field(alias="encounterID")
    phases: list[PhaseMetadataModel] | None = None


class ActorModel(WclModel):
    id: int | None = None
    name: str | None = None
    server: str | None = None
    type: str | None = None
    sub_type: str | None = None
    pet_owner: int | None = None
    icon: str | None = None


class AbilityModel(WclModel):
    game_id: float | None = Field(default=None, alias="gameID")
    name: str | None = None
    icon: str | None = None


class MasterDataModel(WclModel):
    actors: list[ActorModel | None] | None = None
    abilities: list[AbilityModel | None] | None = None


class ReportModel(WclModel):
    code: str
    title: str = ""
    start_time: float
    fights: list[FightModel | None] | None = None
    phases: list[EncounterPhasesModel] | None = None
    master_data: MasterDataModel | None = None


class ReportDataModel(WclModel):
    report: ReportModel | None = None


class ReportQueryModel(WclModel):
    report_data: ReportDataModel


# --- events ------------------------------------------------------------------


class EventPageModel(WclModel):
    data: list[dict[str, Any]] = Field(default_factory=list)
    next_page_timestamp: float | None = None


class EventsReportModel(WclModel):
    events: EventPageModel | None = None


class EventsReportDataModel(WclModel):
    report: EventsReportModel | None = None


class EventsQueryModel(WclModel):
    report_data: EventsReportDataModel


class CastEventModel(WclModel):
    timestamp: float
    type: str
    source_id: int = Field(alias="sourceID")
    ability_game_id: int = Field(alias="abilityGameID")
    fake: bool = False
