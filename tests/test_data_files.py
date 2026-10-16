from wcl_notes.domain.encounters import IDENTITY_MAPPING, MappingStatus, PhaseStrategy
from wcl_notes.domain.spells import SpellCategory
from wcl_notes.services.data_files import (
    all_spec_files,
    load_encounters,
    load_spec_spells,
    nsrt_mapping,
    spec_file_name,
)

VENOMOUS_ABYSS = {3470, 3445, 3455, 3497, 3420, 3421, 3429, 3492, 3379, 3513}


def test_every_venomous_abyss_boss_has_a_mapping() -> None:
    encounters = load_encounters()
    assert set(encounters) >= VENOMOUS_ABYSS
    for info in encounters.values():
        if info.nsrt.strategy is PhaseStrategy.COUNT:
            assert info.nsrt.count_on
        assert info.nsrt.status is not MappingStatus.UNVERIFIED


def test_known_mappings() -> None:
    assert nsrt_mapping(3470).phases == {1: 1, 2: 1.5, 3: 2}
    assert nsrt_mapping(3470).status is MappingStatus.APPROXIMATE
    assert nsrt_mapping(3445).count_on == frozenset({1})
    assert nsrt_mapping(3492).strategy is PhaseStrategy.SINGLE


def test_unknown_boss_falls_back_to_identity() -> None:
    assert nsrt_mapping(999_999) is IDENTITY_MAPPING


def test_rogue_assassination_spells() -> None:
    spells = load_spec_spells("Rogue", "Assassination")
    assert spells is not None
    defaults = spells.default_ids()
    assert {360194, 385627, 1856} <= defaults  # Deathmark, Kingsbane, Vanish
    assert 1236994 in defaults  # Potion of Recklessness, from the common file
    assert 1766 not in defaults  # Kick
    by_id = {s.id: s for s in spells.spells}
    assert by_id[31224].category is SpellCategory.DEFENSIVE
    assert len(by_id) == len(spells.spells)


def test_missing_spec_file() -> None:
    assert load_spec_spells("Mage", "Frost") is None


def test_spec_file_names() -> None:
    assert spec_file_name("Rogue", "Assassination") == "rogue_assassination.yaml"
    assert spec_file_name("DemonHunter", "Havoc") == "demonhunter_havoc.yaml"
    assert spec_file_name("Hunter", "BeastMastery") == "hunter_beastmastery.yaml"
    assert "_common.yaml" not in all_spec_files()
    assert "rogue_assassination.yaml" in all_spec_files()
