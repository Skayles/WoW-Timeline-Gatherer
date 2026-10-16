"""Remember which spells I keep in the note, per boss and per spec.

A preset stores what I explicitly kept and dropped among the spells I have seen, so a
choice survives logs where the spell was not cast.
"""

from collections.abc import Iterable
from typing import Protocol

from wcl_notes.domain.models import Track
from wcl_notes.domain.spells import SpellPreset

PresetKey = tuple[int, str]  # encounter id, WCL "Class-Spec" icon


class PresetStore(Protocol):
    def get_preset(self, key: PresetKey) -> SpellPreset | None: ...

    def set_preset(self, key: PresetKey, preset: SpellPreset) -> None: ...

    def delete_preset(self, key: PresetKey) -> None: ...


def preset_key(track: Track) -> PresetKey | None:
    player = track.player
    if not player.spec or not player.icon:
        return None
    return (track.fight.encounter_id, player.icon)


def apply_preset(defaults: set[int], preset: SpellPreset | None, cast_ids: set[int]) -> set[int]:
    """Spells to pre-select for a new track."""
    if preset is None:
        return set(defaults)
    return ((defaults | preset.include) - preset.exclude) & cast_ids


def merge_preset(old: SpellPreset | None, included: set[int], seen: set[int]) -> SpellPreset:
    """Update ``old`` with the current choices about the ``seen`` spells only."""
    old = old or SpellPreset()
    return SpellPreset(
        include=frozenset((old.include - seen) | (included & seen)),
        exclude=frozenset((old.exclude - seen) | (seen - included)),
    )


def seen_spells(tracks: Iterable[Track]) -> dict[PresetKey, set[int]]:
    """Spells cast by the tracks, grouped by preset key."""
    seen: dict[PresetKey, set[int]] = {}
    for track in tracks:
        key = preset_key(track)
        if key is not None:
            seen.setdefault(key, set()).update(c.spell_id for c in track.casts)
    return seen
