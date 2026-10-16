"""The tracks on the timeline (one boss) and what is selected for the note."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from wcl_notes.domain.models import Actor, Cast, PhaseInfo, Spell, Track, TrackRef
from wcl_notes.domain.spells import SpecSpells, SpellCategory, SpellPreset
from wcl_notes.i18n import tr
from wcl_notes.services.data_files import load_spec_spells
from wcl_notes.services.notes import NoteAssignment
from wcl_notes.services.presets import apply_preset
from wcl_notes.services.selection import Selection, candidate_spells, default_spells

TRACK_COLORS = (
    "#4FC3F7",
    "#FFB74D",
    "#81C784",
    "#E57373",
    "#BA68C8",
    "#FFF176",
    "#4DB6AC",
    "#F06292",
    "#A1887F",
    "#90A4AE",
)
COMFORTABLE_TRACK_COUNT = 10
CATEGORY_ORDER = (
    SpellCategory.OFFENSIVE,
    SpellCategory.RAID_CD,
    SpellCategory.DEFENSIVE,
    SpellCategory.CONSUMABLE,
    SpellCategory.TRINKET,
    SpellCategory.UTILITY,
    SpellCategory.MOVEMENT,
)


class DifferentEncounterError(ValueError):
    """A timeline holds a single boss. Message is user-facing."""


def spec_spells_for(actor: Actor) -> SpecSpells | None:
    return load_spec_spells(actor.sub_type, actor.spec) if actor.spec else None


@dataclass
class TrackEntry:
    track: Track
    spells: Mapping[int, Spell]
    """Spell names and icons of the source report."""
    phase_infos: tuple[PhaseInfo, ...]
    report_title: str
    origin: str
    color: str
    visible: bool = True

    @property
    def ref(self) -> TrackRef:
        return self.track.ref

    @property
    def wcl_url(self) -> str:
        ref = self.track.ref
        return (
            f"https://www.warcraftlogs.com/reports/{ref.report_code}"
            f"#fight={ref.fight_id}&type=casts&source={ref.source_id}"
        )


@dataclass(frozen=True, slots=True)
class LegendEntry:
    spell: Spell
    category: SpellCategory | None
    count: int
    included: bool


class Workspace:
    def __init__(self) -> None:
        self.entries: list[TrackEntry] = []
        self.selection = Selection()

    @property
    def encounter_id(self) -> int | None:
        return self.entries[0].track.fight.encounter_id if self.entries else None

    def accepts(self, encounter_id: int) -> bool:
        return self.encounter_id is None or self.encounter_id == encounter_id

    def entry(self, ref: TrackRef) -> TrackEntry | None:
        return next((e for e in self.entries if e.ref == ref), None)

    def add(
        self,
        track: Track,
        *,
        spells: Mapping[int, Spell],
        phase_infos: tuple[PhaseInfo, ...] = (),
        report_title: str = "",
        origin: str = "",
        preset: SpellPreset | None = None,
    ) -> TrackEntry:
        """Add a track; its spells are pre-selected from ``preset``, else the spec defaults."""
        if not self.accepts(track.fight.encounter_id):
            raise DifferentEncounterError(
                tr(
                    "La timeline contient déjà un autre boss que {boss} : "
                    "videz-la avant d'ajouter cette piste."
                ).format(boss=track.fight.name)
            )
        existing = self.entry(track.ref)
        if existing is not None:
            return existing
        used = {e.color for e in self.entries}
        color = next(
            (c for c in TRACK_COLORS if c not in used), TRACK_COLORS[len(self.entries) % 10]
        )
        entry = TrackEntry(
            track=track,
            spells=spells,
            phase_infos=phase_infos,
            report_title=report_title,
            origin=origin,
            color=color,
        )
        self.entries.append(entry)
        self.selection.included_spells |= apply_preset(
            self.default_spells(entry), preset, {c.spell_id for c in track.casts}
        )
        return entry

    def default_spells(self, entry: TrackEntry) -> set[int]:
        return default_spells(entry.track, spec_spells_for(entry.track.player))

    def reset_selection(self) -> None:
        """Back to the spec defaults of the current tracks (disabled casts are kept)."""
        self.selection.included_spells = set().union(
            *(self.default_spells(entry) for entry in self.entries)
        )

    def remove(self, ref: TrackRef) -> None:
        self.entries = [e for e in self.entries if e.ref != ref]
        self.selection.forget_track(ref)

    def clear(self) -> None:
        self.entries = []
        self.selection = Selection(show_all=self.selection.show_all)

    def visible_entries(self) -> list[TrackEntry]:
        return [e for e in self.entries if e.visible]

    def spell(self, spell_id: int) -> Spell:
        for entry in self.entries:
            if spell_id in entry.spells:
                return entry.spells[spell_id]
        return Spell(id=spell_id, name=str(spell_id))

    def candidates(self, entry: TrackEntry) -> set[int]:
        return candidate_spells(
            entry.track, spec_spells_for(entry.track.player), show_all=self.selection.show_all
        )

    def displayed_casts(self, entry: TrackEntry) -> list[Cast]:
        """Casts drawn on the timeline: legend spells that are included in the note."""
        shown = self.candidates(entry) & self.selection.included_spells
        return [c for c in entry.track.casts if c.spell_id in shown]

    def legend(self) -> list[LegendEntry]:
        counts: Counter[int] = Counter()
        categories: dict[int, SpellCategory] = {}
        for entry in self.visible_entries():
            candidates = self.candidates(entry)
            counts.update(c.spell_id for c in entry.track.casts if c.spell_id in candidates)
            spec_spells = spec_spells_for(entry.track.player)
            for spell in spec_spells.spells if spec_spells else ():
                categories.setdefault(spell.id, spell.category)
        legend = [
            LegendEntry(
                spell=self.spell(spell_id),
                category=categories.get(spell_id),
                count=count,
                included=self.selection.is_included(spell_id),
            )
            for spell_id, count in counts.items()
        ]
        order = {category: index for index, category in enumerate(CATEGORY_ORDER)}
        legend.sort(
            key=lambda e: (
                order.get(e.category, len(order)) if e.category else len(order),
                e.spell.name.casefold(),
            )
        )
        return legend

    def note_assignments(self, targets: Sequence[tuple[TrackRef, str]]) -> list[NoteAssignment]:
        """``targets`` = (track, name written in the note) for each track to export."""
        assignments = []
        for ref, name in targets:
            entry = self.entry(ref)
            if entry is not None:
                assignments.append(
                    NoteAssignment(
                        track=entry.track,
                        casts=self.selection.note_casts(entry.track),
                        player_name=name,
                    )
                )
        return assignments
