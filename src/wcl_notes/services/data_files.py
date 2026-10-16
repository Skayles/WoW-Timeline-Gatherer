"""Load the bundled YAML data: boss phase mappings and important spells per spec."""

import re
from functools import cache
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from wcl_notes.domain.encounters import (
    IDENTITY_MAPPING,
    EncounterInfo,
    MappingStatus,
    NsrtPhaseMapping,
    PhaseStrategy,
)
from wcl_notes.domain.spells import ImportantSpell, SpecSpells, SpellCategory


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _NsrtModel(_Strict):
    strategy: PhaseStrategy
    status: MappingStatus
    phases: dict[int, float] = {}
    count_on: list[int] = []
    note: str = ""
    source: str = ""


class _EncounterFileModel(_Strict):
    encounter_id: int
    name: str
    zone: str = ""
    wcl_phases: dict[int, str] = {}
    nsrt: _NsrtModel


class _SpellModel(_Strict):
    id: int
    name: str
    category: SpellCategory
    selected_by_default: bool = False
    cooldown: float | None = None


class _CommonSpellsModel(_Strict):
    spells: list[_SpellModel]


class _SpecFileModel(_CommonSpellsModel):
    class_name: str
    spec: str


COMMON_SPELLS_FILE = "_common.yaml"


def _data_dir(kind: str) -> Traversable:
    return resources.files("wcl_notes").joinpath("data", kind)


def _yaml_files(kind: str) -> list[Traversable]:
    return sorted(
        (f for f in _data_dir(kind).iterdir() if f.name.endswith(".yaml")), key=lambda f: f.name
    )


def _load_yaml(file: Traversable) -> Any:
    return yaml.safe_load(file.read_text(encoding="utf-8"))


@cache
def load_encounters() -> dict[int, EncounterInfo]:
    encounters: dict[int, EncounterInfo] = {}
    for file in _yaml_files("encounters"):
        model = _EncounterFileModel.model_validate(_load_yaml(file))
        if model.encounter_id in encounters:
            raise ValueError(f"encounter_id {model.encounter_id} en double ({file.name})")
        encounters[model.encounter_id] = EncounterInfo(
            encounter_id=model.encounter_id,
            name=model.name,
            nsrt=NsrtPhaseMapping(
                strategy=model.nsrt.strategy,
                status=model.nsrt.status,
                phases=dict(model.nsrt.phases),
                count_on=frozenset(model.nsrt.count_on),
                note=model.nsrt.note,
            ),
        )
    return encounters


def nsrt_mapping(encounter_id: int) -> NsrtPhaseMapping:
    info = load_encounters().get(encounter_id)
    return info.nsrt if info else IDENTITY_MAPPING


def spec_file_name(class_name: str, spec: str) -> str:
    """Spec file of a WCL class/spec: ("Rogue", "Assassination") -> rogue_assassination.yaml."""
    slug = "_".join(re.sub(r"[^a-z0-9]", "", part.lower()) for part in (class_name, spec))
    return f"{slug}.yaml"


@cache
def load_spec_spells(class_name: str, spec: str) -> SpecSpells | None:
    """Spells of the spec plus the common ones (potions, trinkets); None if no spec file."""
    file = _data_dir("spells").joinpath(spec_file_name(class_name, spec))
    if not file.is_file():
        return None
    model = _SpecFileModel.model_validate(_load_yaml(file))
    common = _CommonSpellsModel.model_validate(
        _load_yaml(_data_dir("spells").joinpath(COMMON_SPELLS_FILE))
    )
    own_ids = {s.id for s in model.spells}
    return SpecSpells(
        class_name=model.class_name,
        spec=model.spec,
        spells=tuple(
            ImportantSpell(
                id=s.id,
                name=s.name,
                category=s.category,
                selected_by_default=s.selected_by_default,
                cooldown=s.cooldown,
            )
            for s in [*model.spells, *(c for c in common.spells if c.id not in own_ids)]
        ),
    )


def all_spec_files() -> list[str]:
    return [f.name for f in _yaml_files("spells") if not f.name.startswith("_")]
