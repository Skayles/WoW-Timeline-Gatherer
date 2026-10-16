"""Glue between the widgets, the WCL API (through background tasks) and the workspace."""

import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from wcl_notes.api.client import WclClient
from wcl_notes.api.credentials import load_credentials
from wcl_notes.api.rankings import fetch_catalog, fetch_rankings
from wcl_notes.api.reports import fetch_player_casts, fetch_player_roles, fetch_report
from wcl_notes.domain.models import Actor, Cast, Fight, Report, Role, Track, TrackRef
from wcl_notes.domain.rankings import GameCatalog, RankingEntry, RankingQuery, RankingsPage
from wcl_notes.i18n import tr
from wcl_notes.services.presets import PresetStore, merge_preset, preset_key, seen_spells
from wcl_notes.services.rankings import find_ranked_player
from wcl_notes.services.report_navigation import resolve_fight
from wcl_notes.services.report_reference import (
    InvalidReportReferenceError,
    ReportReference,
    parse_report_reference,
)
from wcl_notes.services.timeline import build_casts
from wcl_notes.services.workspace import COMFORTABLE_TRACK_COUNT, DifferentEncounterError, Workspace
from wcl_notes.ui.workers import TaskRunner

ClientFactory = Callable[[], WclClient]
RankingKey = tuple[str, int, str]  # report code, fight id, character name


def ranking_key(entry: RankingEntry) -> RankingKey:
    return (entry.report_code, entry.fight_id, entry.name)


def default_client_factory() -> WclClient:
    return WclClient(load_credentials(Path(".env")))


class TrackState:
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"
    REMOVED = "removed"


class AppController(QObject):
    report_loaded = Signal(object, object)  # Report, ReportReference
    roles_loaded = Signal(str, int, object)  # report code, fight id, dict[int, Role]
    catalog_loaded = Signal(object)  # GameCatalog
    rankings_loaded = Signal(object)  # RankingsPage
    ranking_state_changed = Signal(object)  # RankingKey
    workspace_changed = Signal()
    selection_changed = Signal()
    track_state_changed = Signal(object, str)  # TrackRef, TrackState
    error = Signal(str)
    message = Signal(str)

    def __init__(
        self,
        runner: TaskRunner,
        client_factory: ClientFactory = default_client_factory,
        parent: QObject | None = None,
        *,
        presets: PresetStore | None = None,
    ) -> None:
        super().__init__(parent)
        self._presets = presets
        self.workspace = Workspace()
        self._runner = runner
        self._client_factory = client_factory
        self._client: WclClient | None = None
        self._client_lock = threading.Lock()
        self._reports: dict[str, Report] = {}
        self._roles: dict[tuple[str, int], dict[int, Role]] = {}
        self._loading: set[TrackRef] = set()
        self._cancelled: set[TrackRef] = set()
        self._failed: set[TrackRef] = set()
        self._catalog: GameCatalog | None = None
        self._ranked_refs: dict[RankingKey, TrackRef] = {}
        self._ranked_loading: set[RankingKey] = set()
        self._ranked_cancelled: set[RankingKey] = set()
        self._ranked_failed: set[RankingKey] = set()

    # --- WCL access ---------------------------------------------------------------

    def client(self) -> WclClient:
        """Created on first use (credentials may be entered after start-up)."""
        with self._client_lock:
            if self._client is None:
                self._client = self._client_factory()
            return self._client

    def reset_client(self) -> None:
        with self._client_lock:
            if self._client is not None:
                self._client.close()
            self._client = None

    def load_report(self, text: str) -> None:
        try:
            ref = parse_report_reference(text)
        except InvalidReportReferenceError as exc:
            self.error.emit(str(exc))
            return
        cached = self._reports.get(ref.code)
        if cached is not None:
            self.report_loaded.emit(cached, ref)
            return

        def loaded(report: object) -> None:
            assert isinstance(report, Report)
            self._reports[report.code] = report
            self.message.emit(
                tr("Report {code} chargé : {title}").format(code=report.code, title=report.title)
            )
            self.report_loaded.emit(report, ref)

        self.message.emit(tr("Chargement du report {code}…").format(code=ref.code))
        self._runner.run(lambda: fetch_report(self.client(), ref.code), loaded, self.error.emit)

    def roles(self, report: Report, fight: Fight) -> dict[int, Role] | None:
        return self._roles.get((report.code, fight.id))

    def load_roles(self, report: Report, fight: Fight) -> None:
        key = (report.code, fight.id)
        if key in self._roles:
            self.roles_loaded.emit(report.code, fight.id, self._roles[key])
            return

        def loaded(roles: object) -> None:
            assert isinstance(roles, dict)
            self._roles[key] = roles
            self.roles_loaded.emit(report.code, fight.id, roles)

        def failed(message: str) -> None:
            # Roles only group the list: fall back to an ungrouped list.
            self._roles[key] = {}
            self.roles_loaded.emit(report.code, fight.id, {})
            self.message.emit(tr("Rôles indisponibles : {error}").format(error=message))

        self._runner.run(
            lambda: fetch_player_roles(self.client(), report.code, fight), loaded, failed
        )

    # --- tracks -------------------------------------------------------------------

    def track_state(self, ref: TrackRef) -> str | None:
        if ref in self._loading:
            return TrackState.LOADING
        if self.workspace.entry(ref) is not None:
            return TrackState.LOADED
        if ref in self._failed:
            return TrackState.ERROR
        return None

    def add_track(self, report: Report, fight: Fight, actor: Actor, origin: str) -> None:
        """Download the casts of ``actor`` in ``fight`` (lazy: only when ticked)."""
        ref = TrackRef(report.code, fight.id, actor.id)
        if self.workspace.entry(ref) is not None or ref in self._loading:
            return
        if not self.workspace.accepts(fight.encounter_id):
            self.error.emit(
                tr("La timeline contient déjà un autre boss que {boss} : videz-la d'abord.").format(
                    boss=fight.name
                )
            )
            self.track_state_changed.emit(ref, TrackState.REMOVED)
            return
        self._loading.add(ref)
        self._cancelled.discard(ref)
        self._failed.discard(ref)
        self.track_state_changed.emit(ref, TrackState.LOADING)

        def work() -> Track:
            events = fetch_player_casts(self.client(), report.code, fight, actor.id)
            return Track(ref, actor, fight, build_casts(events, fight))

        def loaded(track: object) -> None:
            assert isinstance(track, Track)
            self._loading.discard(ref)
            if ref in self._cancelled:
                self._cancelled.discard(ref)
                self.track_state_changed.emit(ref, TrackState.REMOVED)
                return
            self._add_loaded_track(report, track, origin)

        def failed(message: str) -> None:
            self._loading.discard(ref)
            self._cancelled.discard(ref)
            self._failed.add(ref)
            self.track_state_changed.emit(ref, TrackState.ERROR)
            self.error.emit(f"{actor.name} : {message}")

        self._runner.run(work, loaded, failed)

    def _add_loaded_track(self, report: Report, track: Track, origin: str) -> bool:
        ref = track.ref
        key = preset_key(track)
        preset = self._presets.get_preset(key) if self._presets and key else None
        try:
            self.workspace.add(
                track,
                spells=report.spells,
                phase_infos=report.phases.get(track.fight.encounter_id, ()),
                report_title=report.title,
                origin=origin,
                preset=preset,
            )
        except DifferentEncounterError as exc:
            self.track_state_changed.emit(ref, TrackState.REMOVED)
            self.error.emit(str(exc))
            return False
        self.track_state_changed.emit(ref, TrackState.LOADED)
        self.workspace_changed.emit()
        if len(self.workspace.entries) > COMFORTABLE_TRACK_COUNT:
            self.message.emit(
                tr(
                    "Plus de {n} pistes : la timeline devient chargée "
                    "et chaque piste consomme du quota API."
                ).format(n=COMFORTABLE_TRACK_COUNT)
            )
        return True

    def remove_track(self, ref: TrackRef) -> None:
        if ref in self._loading:
            self._cancelled.add(ref)
            return
        self._failed.discard(ref)
        if self.workspace.entry(ref) is None:
            return
        self.workspace.remove(ref)
        self.track_state_changed.emit(ref, TrackState.REMOVED)
        self.workspace_changed.emit()

    def clear(self) -> None:
        refs = [e.ref for e in self.workspace.entries]
        self._cancelled |= self._loading
        self._ranked_cancelled |= self._ranked_loading
        self.workspace.clear()
        for ref in refs:
            self.track_state_changed.emit(ref, TrackState.REMOVED)
        self.workspace_changed.emit()

    def set_visible(self, ref: TrackRef, visible: bool) -> None:
        entry = self.workspace.entry(ref)
        if entry is not None and entry.visible != visible:
            entry.visible = visible
            self.workspace_changed.emit()

    def set_color(self, ref: TrackRef, color: str) -> None:
        entry = self.workspace.entry(ref)
        if entry is not None:
            entry.color = color
            self.workspace_changed.emit()

    # --- selection ----------------------------------------------------------------

    def toggle_spell(self, spell_id: int) -> None:
        self.workspace.selection.toggle_spell(spell_id)
        self._save_presets()
        self.selection_changed.emit()

    def reset_selection(self) -> None:
        """Back to the spec defaults, and forget the presets of the current tracks."""
        if self._presets is not None:
            for key in seen_spells(e.track for e in self.workspace.entries):
                self._presets.delete_preset(key)
        self.workspace.reset_selection()
        self.selection_changed.emit()

    def _save_presets(self) -> None:
        if self._presets is None:
            return
        included = self.workspace.selection.included_spells
        for key, seen in seen_spells(e.track for e in self.workspace.entries).items():
            self._presets.set_preset(
                key, merge_preset(self._presets.get_preset(key), included, seen)
            )

    def set_spell_included(self, spell_id: int, included: bool) -> None:
        if self.workspace.selection.is_included(spell_id) != included:
            self.toggle_spell(spell_id)

    def toggle_cast(self, ref: TrackRef, cast: Cast) -> None:
        self.workspace.selection.toggle_cast(ref, cast)
        self.selection_changed.emit()

    def set_show_all(self, show_all: bool) -> None:
        if self.workspace.selection.show_all != show_all:
            self.workspace.selection.show_all = show_all
            self.selection_changed.emit()

    def cached_report(self, ref: ReportReference) -> Report | None:
        return self._reports.get(ref.code)

    # --- rankings -----------------------------------------------------------------

    @property
    def catalog(self) -> GameCatalog | None:
        return self._catalog

    def load_catalog(self) -> None:
        if self._catalog is not None:
            self.catalog_loaded.emit(self._catalog)
            return

        def loaded(catalog: object) -> None:
            assert isinstance(catalog, GameCatalog)
            self._catalog = catalog
            self.catalog_loaded.emit(catalog)

        self._runner.run(lambda: fetch_catalog(self.client()), loaded, self.error.emit)

    def load_rankings(self, query: RankingQuery) -> None:
        """Rankings are cached one hour by the client's SQLite cache."""

        def loaded(page: object) -> None:
            assert isinstance(page, RankingsPage)
            self.message.emit(
                tr("{n} classements chargés (page {page}).").format(
                    n=len(page.entries), page=query.page
                )
            )
            self.rankings_loaded.emit(page)

        self.message.emit(tr("Chargement des classements…"))
        self._runner.run(lambda: fetch_rankings(self.client(), query), loaded, self.error.emit)

    def ranked_track_state(self, entry: RankingEntry) -> str | None:
        key = ranking_key(entry)
        if key in self._ranked_loading:
            return TrackState.LOADING
        ref = self._ranked_refs.get(key)
        if ref is not None and self.workspace.entry(ref) is not None:
            return TrackState.LOADED
        if key in self._ranked_failed:
            return TrackState.ERROR
        return None

    def add_ranked_track(self, entry: RankingEntry, encounter_id: int) -> None:
        """Load the report of a top log, find the ranked player in it, then its casts."""
        key = ranking_key(entry)
        if self.ranked_track_state(entry) in (TrackState.LOADING, TrackState.LOADED):
            return
        if not self.workspace.accepts(encounter_id):
            self.error.emit(tr("La timeline contient déjà un autre boss : videz-la d'abord."))
            self.ranking_state_changed.emit(key)
            return
        self._ranked_loading.add(key)
        self._ranked_cancelled.discard(key)
        self._ranked_failed.discard(key)
        self.ranking_state_changed.emit(key)
        cached = self._reports.get(entry.report_code)

        def work() -> tuple[Report, Track]:
            client = self.client()
            report = cached or fetch_report(client, entry.report_code)
            fight = resolve_fight(report, entry.fight_id)
            actor = find_ranked_player(report, fight, entry)
            events = fetch_player_casts(client, report.code, fight, actor.id)
            ref = TrackRef(report.code, fight.id, actor.id)
            return report, Track(ref, actor, fight, build_casts(events, fight))

        def loaded(result: object) -> None:
            assert isinstance(result, tuple)
            report, track = result
            self._reports[report.code] = report
            self._ranked_loading.discard(key)
            if key in self._ranked_cancelled:
                self._ranked_cancelled.discard(key)
            else:
                self._ranked_refs[key] = track.ref
                self._add_loaded_track(
                    report, track, tr("Classement #{rank}").format(rank=entry.rank)
                )
            self.ranking_state_changed.emit(key)

        def failed(message: str) -> None:
            self._ranked_loading.discard(key)
            self._ranked_cancelled.discard(key)
            self._ranked_failed.add(key)
            self.ranking_state_changed.emit(key)
            self.error.emit(f"{entry.name} (#{entry.rank}) : {message}")

        self._runner.run(work, loaded, failed)

    def remove_ranked_track(self, entry: RankingEntry) -> None:
        key = ranking_key(entry)
        if key in self._ranked_loading:
            self._ranked_cancelled.add(key)
            return
        self._ranked_failed.discard(key)
        ref = self._ranked_refs.pop(key, None)
        if ref is not None:
            self.remove_track(ref)
        self.ranking_state_changed.emit(key)
