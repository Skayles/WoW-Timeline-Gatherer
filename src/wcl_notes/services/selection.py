"""What goes into the note: spells toggled in the legend and casts disabled one by one."""

from collections import Counter
from dataclasses import dataclass, field

from wcl_notes.domain.models import Cast, Track, TrackRef
from wcl_notes.domain.spells import SpecSpells

# Without a spell list for the spec, spells cast at most this many times are pre-selected:
# fillers are cast dozens of times, cooldowns, potions and trinkets only a few.
UNKNOWN_SPEC_MAX_CASTS = 8

CastKey = tuple[TrackRef, Cast]


@dataclass
class Selection:
    included_spells: set[int] = field(default_factory=set)
    disabled_casts: set[CastKey] = field(default_factory=set)
    show_all: bool = False

    def is_included(self, spell_id: int) -> bool:
        return spell_id in self.included_spells

    def is_disabled(self, ref: TrackRef, cast: Cast) -> bool:
        return (ref, cast) in self.disabled_casts

    def toggle_spell(self, spell_id: int) -> bool:
        """Include or exclude a spell; returns the new state."""
        if spell_id in self.included_spells:
            self.included_spells.discard(spell_id)
            return False
        self.included_spells.add(spell_id)
        return True

    def toggle_cast(self, ref: TrackRef, cast: Cast) -> bool:
        """Disable or re-enable one cast; returns True when the cast is now enabled."""
        key = (ref, cast)
        if key in self.disabled_casts:
            self.disabled_casts.discard(key)
            return True
        self.disabled_casts.add(key)
        return False

    def note_casts(self, track: Track) -> list[Cast]:
        return [
            c
            for c in track.casts
            if c.spell_id in self.included_spells and (track.ref, c) not in self.disabled_casts
        ]

    def forget_track(self, ref: TrackRef) -> None:
        self.disabled_casts = {key for key in self.disabled_casts if key[0] != ref}


def default_spells(track: Track, spec_spells: SpecSpells | None) -> set[int]:
    """Spells pre-selected when a track is added."""
    counts = Counter(c.spell_id for c in track.casts)
    if spec_spells is not None:
        return set(counts) & spec_spells.default_ids()
    return {spell_id for spell_id, n in counts.items() if n <= UNKNOWN_SPEC_MAX_CASTS}


def candidate_spells(track: Track, spec_spells: SpecSpells | None, *, show_all: bool) -> set[int]:
    """Spells listed in the legend (and drawable on the timeline) for this track."""
    cast_ids = {c.spell_id for c in track.casts}
    if show_all or spec_spells is None:
        return cast_ids
    return cast_ids & {s.id for s in spec_spells.spells}
