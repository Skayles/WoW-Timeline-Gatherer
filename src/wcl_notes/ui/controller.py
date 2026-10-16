"""Glue between the widgets, the WCL API (through background tasks) and the workspace."""

import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from wcl_notes.api.client import WclClient
from wcl_notes.api.credentials import load_credentials
from wcl_notes.api.reports import fetch_player_casts, fetch_player_roles, fetch_report
from wcl_notes.domain.models import Actor, Cast, Fight, Report, Role, Track, TrackRef
from wcl_notes.services.report_reference import (
    InvalidReportReferenceError,
    ReportReference,
    parse_report_reference,
)
from wcl_notes.services.timeline import build_casts
from wcl_notes.services.workspace import COMFORTABLE_TRACK_COUNT, DifferentEncounterError, Workspace
from wcl_notes.ui.workers import TaskRunner

ClientFactory = Callable[[], WclClient]


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
    ) -> None:
        super().__init__(parent)
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
            self.message.emit(f"Report {report.code} chargé : {report.title}")
            self.report_loaded.emit(report, ref)

        self.message.emit(f"Chargement du report {ref.code}…")
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
            self.message.emit(f"Rôles indisponibles : {message}")

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
                f"La timeline contient déjà un autre boss que {fight.name} : videz-la d'abord."
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
            try:
                self.workspace.add(
                    track,
                    spells=report.spells,
                    phase_infos=report.phases.get(fight.encounter_id, ()),
                    report_title=report.title,
                    origin=origin,
                )
            except DifferentEncounterError as exc:
                self.track_state_changed.emit(ref, TrackState.REMOVED)
                self.error.emit(str(exc))
                return
            self.track_state_changed.emit(ref, TrackState.LOADED)
            self.workspace_changed.emit()
            if len(self.workspace.entries) > COMFORTABLE_TRACK_COUNT:
                self.message.emit(
                    f"Plus de {COMFORTABLE_TRACK_COUNT} pistes : la timeline devient chargée "
                    "et chaque piste consomme du quota API."
                )

        def failed(message: str) -> None:
            self._loading.discard(ref)
            self._cancelled.discard(ref)
            self._failed.add(ref)
            self.track_state_changed.emit(ref, TrackState.ERROR)
            self.error.emit(f"{actor.name} : {message}")

        self._runner.run(work, loaded, failed)

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
        self.selection_changed.emit()

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
