"""« Log » tab: paste a WCL URL or code, pick a fight, tick the players to load."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wcl_notes.domain.models import Actor, Fight, Report, Role, TrackRef
from wcl_notes.labels import (
    ROLE_LABELS,
    difficulty_label,
    fight_label,
    format_duration,
    outcome_label,
    spec_label,
)
from wcl_notes.services.report_navigation import (
    NavigationError,
    boss_fights,
    find_player,
    players_in_fight,
    resolve_fight,
)
from wcl_notes.services.report_reference import ReportReference
from wcl_notes.ui.controller import AppController, TrackState
from wcl_notes.ui.settings import AppSettings
from wcl_notes.ui.style import ERROR, TEXT_DIM, class_color

ID_ROLE = Qt.ItemDataRole.UserRole
STATE_LABELS = {
    TrackState.LOADING: "chargement…",
    TrackState.LOADED: "✓",
    TrackState.ERROR: "erreur",
}


class LogPanel(QWidget):
    def __init__(
        self, controller: AppController, settings: AppSettings, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._settings = settings
        self._report: Report | None = None
        self._fight: Fight | None = None
        self._pending_source: int | None = None
        self._updating = False

        self.input = QComboBox()
        self.input.setEditable(True)
        self.input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        line_edit = self.input.lineEdit()
        assert line_edit is not None
        line_edit.setPlaceholderText(self.tr("URL Warcraft Logs ou code du report"))
        line_edit.returnPressed.connect(self.load)
        self.input.activated.connect(self._on_history_activated)
        self.load_button = QPushButton(self.tr("Charger"))
        self.load_button.clicked.connect(self.load)

        self.report_label = QLabel(self.tr("Aucun report chargé."))
        self.report_label.setWordWrap(True)
        self.kills_only = QCheckBox(self.tr("Kills seulement"))
        self.kills_only.setChecked(True)
        self.kills_only.toggled.connect(self._populate_fights)

        self.fights = QTreeWidget()
        self.fights.setHeaderLabels(
            [self.tr("Fight"), self.tr("Difficulté"), self.tr("Résultat"), self.tr("Durée")]
        )
        self.fights.setRootIsDecorated(True)
        self.fights.currentItemChanged.connect(self._on_fight_selected)

        self.players_label = QLabel(self.tr("Choisissez un fight."))
        self.players_label.setWordWrap(True)
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Rechercher un joueur"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_search)
        self.my_spec_button = QPushButton(self.tr("Cocher ma spé"))
        self.my_spec_button.clicked.connect(self._check_my_spec)
        self.me_button = QPushButton(self.tr("Me cocher"))
        self.me_button.clicked.connect(self._check_me)

        self.players = QTreeWidget()
        self.players.setHeaderLabels([self.tr("Joueur"), self.tr("Spé"), self.tr("État")])
        self.players.itemChanged.connect(self._on_player_changed)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        input_row = QHBoxLayout()
        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.load_button)
        top_layout.addLayout(input_row)
        top_layout.addWidget(self.report_label)
        top_layout.addWidget(self.kills_only)
        top_layout.addWidget(self.fights, 1)

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(self.players_label)
        bottom_layout.addWidget(self.search)
        buttons = QHBoxLayout()
        buttons.addWidget(self.my_spec_button)
        buttons.addWidget(self.me_button)
        bottom_layout.addLayout(buttons)
        bottom_layout.addWidget(self.players, 1)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(top)
        splitter.addWidget(bottom)
        splitter.setSizes([300, 400])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(splitter)

        self._refresh_history()
        self._set_players_enabled(False)
        controller.report_loaded.connect(self._on_report_loaded)
        controller.roles_loaded.connect(self._on_roles_loaded)
        controller.track_state_changed.connect(self._on_track_state)
        controller.workspace_changed.connect(self._refresh_player_states)

    # --- report -------------------------------------------------------------------

    def load(self) -> None:
        text = self.input.currentText().strip()
        if text:
            self._controller.load_report(text)

    def _on_history_activated(self, index: int) -> None:
        code = self.input.itemData(index)
        if isinstance(code, str):
            self.input.setEditText(code)
            self._controller.load_report(code)

    def _refresh_history(self) -> None:
        text = self.input.currentText()
        self.input.blockSignals(True)
        self.input.clear()
        for code, title in self._settings.recent_reports:
            self.input.addItem(f"{title} — {code}", code)
        self.input.setEditText(text)
        self.input.blockSignals(False)

    def _on_report_loaded(self, report: Report, ref: ReportReference) -> None:
        self._report = report
        self._fight = None
        self._settings.add_recent_report(report.code, report.title)
        self._refresh_history()
        self.input.setEditText(report.code)
        boss_count = len(boss_fights(report))
        self.report_label.setText(
            self.tr("{title} ({code}) — {count} pull(s) de boss").format(
                title=report.title, code=report.code, count=boss_count
            )
        )
        self._pending_source = ref.source_id
        selected = None
        if ref.fight is not None:
            try:
                selected = resolve_fight(report, ref.fight)
            except NavigationError as exc:
                self._controller.message.emit(str(exc))
        if selected is not None and not selected.kill:
            self.kills_only.setChecked(False)
        self._populate_fights()
        if selected is not None:
            self._select_fight(selected.id)
        else:
            self._clear_players(self.tr("Choisissez un fight."))

    def _populate_fights(self) -> None:
        self.fights.clear()
        if self._report is None:
            return
        groups: dict[str, list[Fight]] = {}
        for fight in boss_fights(self._report, kills_only=self.kills_only.isChecked()):
            groups.setdefault(fight.name, []).append(fight)
        for name, fights in groups.items():
            kills = sum(1 for f in fights if f.kill)
            boss = QTreeWidgetItem([name, "", self.tr("{n} kill(s)").format(n=kills), ""])
            boss.setFlags(Qt.ItemFlag.ItemIsEnabled)
            font = QFont(boss.font(0))
            font.setBold(True)
            boss.setFont(0, font)
            for fight in fights:
                item = QTreeWidgetItem(
                    [
                        f"#{fight.id}",
                        difficulty_label(fight.difficulty),
                        outcome_label(fight),
                        format_duration(fight.duration_ms),
                    ]
                )
                item.setData(0, ID_ROLE, fight.id)
                if not fight.kill:
                    for column in range(4):
                        item.setForeground(column, QBrush(QColor(TEXT_DIM)))
                boss.addChild(item)
            self.fights.addTopLevelItem(boss)
        self.fights.expandAll()
        for column in range(4):
            self.fights.resizeColumnToContents(column)
        if self._fight is not None:
            self._select_fight(self._fight.id)

    def _select_fight(self, fight_id: int) -> None:
        for i in range(self.fights.topLevelItemCount()):
            boss = self.fights.topLevelItem(i)
            if boss is None:
                continue
            for j in range(boss.childCount()):
                item = boss.child(j)
                if item is not None and item.data(0, ID_ROLE) == fight_id:
                    self.fights.setCurrentItem(item)
                    return

    def _on_fight_selected(self, current: QTreeWidgetItem | None, _: object) -> None:
        if current is None or self._report is None:
            return
        fight_id = current.data(0, ID_ROLE)
        if not isinstance(fight_id, int):
            return
        fight = resolve_fight(self._report, fight_id)
        if self._fight is not None and self._fight.id == fight.id:
            return
        self._fight = fight
        self.players_label.setText(fight_label(fight))
        self._set_players_enabled(True)
        self._populate_players()
        self._controller.load_roles(self._report, fight)

    # --- players ------------------------------------------------------------------

    def _on_roles_loaded(self, code: str, fight_id: int, _: object) -> None:
        if self._report and self._fight and (code, fight_id) == (self._report.code, self._fight.id):
            self._populate_players()

    def _populate_players(self) -> None:
        if self._report is None or self._fight is None:
            return
        report, fight = self._report, self._fight
        roles = self._controller.roles(report, fight) or {}
        players = players_in_fight(report, fight)
        groups: dict[str, list[Actor]] = {}
        if roles:
            for role in (Role.TANK, Role.HEALER, Role.DPS):
                groups[ROLE_LABELS[role]] = [p for p in players if roles.get(p.id) is role]
            others = [p for p in players if p.id not in roles]
            if others:
                groups[self.tr("Autres")] = others
        else:
            groups[self.tr("Joueurs")] = players

        self._updating = True
        self.players.clear()
        for label, actors in groups.items():
            if not actors:
                continue
            group = QTreeWidgetItem([f"{label} ({len(actors)})", "", ""])
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for actor in actors:
                item = QTreeWidgetItem([actor.name, spec_label(actor), ""])
                item.setData(0, ID_ROLE, actor.id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setForeground(1, QBrush(class_color(actor.sub_type)))
                self._apply_state(item, actor.id)
                group.addChild(item)
            self.players.addTopLevelItem(group)
        self.players.expandAll()
        for column in range(3):
            self.players.resizeColumnToContents(column)
        self._updating = False
        self._apply_search()

        if self._pending_source is not None:
            source, self._pending_source = self._pending_source, None
            self._set_checked(source, True)

    def _apply_state(self, item: QTreeWidgetItem, actor_id: int) -> None:
        if self._report is None or self._fight is None:
            return
        state = self._controller.track_state(TrackRef(self._report.code, self._fight.id, actor_id))
        checked = state in (TrackState.LOADING, TrackState.LOADED)
        item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        item.setText(2, STATE_LABELS.get(state or "", ""))
        item.setForeground(2, QBrush(QColor(ERROR if state == TrackState.ERROR else TEXT_DIM)))

    def _player_items(self) -> list[QTreeWidgetItem]:
        items = []
        for i in range(self.players.topLevelItemCount()):
            group = self.players.topLevelItem(i)
            if group is None:
                continue
            for j in range(group.childCount()):
                child = group.child(j)
                if child is not None:
                    items.append(child)
        return items

    def _refresh_player_states(self) -> None:
        self._updating = True
        for item in self._player_items():
            actor_id = item.data(0, ID_ROLE)
            if isinstance(actor_id, int):
                self._apply_state(item, actor_id)
        self._updating = False

    def _on_track_state(self, ref: TrackRef, _: str) -> None:
        if (
            self._report
            and self._fight
            and (ref.report_code, ref.fight_id)
            == (
                self._report.code,
                self._fight.id,
            )
        ):
            self._refresh_player_states()

    def _on_player_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating or column != 0 or self._report is None or self._fight is None:
            return
        actor_id = item.data(0, ID_ROLE)
        if not isinstance(actor_id, int):
            return
        report, fight = self._report, self._fight
        if item.checkState(0) == Qt.CheckState.Checked:
            self._request_add(report, fight, report.actors[actor_id])
        else:
            self._controller.remove_track(TrackRef(report.code, fight.id, actor_id))

    def _request_add(self, report: Report, fight: Fight, actor: Actor) -> None:
        if not self._controller.workspace.accepts(fight.encounter_id):
            answer = QMessageBox.question(
                self,
                self.tr("Autre boss"),
                self.tr(
                    "La timeline contient des pistes d'un autre boss. "
                    "La vider pour ajouter {boss} ?"
                ).format(boss=fight.name),
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._refresh_player_states()
                return
            self._controller.clear()
        origin = f"Log {report.code} #{fight.id}"
        self._controller.add_track(report, fight, actor, origin)

    def _set_checked(self, actor_id: int, checked: bool) -> None:
        for item in self._player_items():
            if item.data(0, ID_ROLE) == actor_id:
                item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def _check_my_spec(self) -> None:
        if self._report is None or self._fight is None:
            return
        my_spec = self._settings.my_spec
        matches = [p for p in players_in_fight(self._report, self._fight) if p.icon == my_spec]
        if not matches:
            self._controller.message.emit(
                self.tr("Aucun joueur {spec} dans ce fight.").format(spec=my_spec)
            )
        for player in matches:
            self._set_checked(player.id, True)

    def _check_me(self) -> None:
        if self._report is None or self._fight is None:
            return
        try:
            me = find_player(
                players_in_fight(self._report, self._fight), self._settings.player_name
            )
        except NavigationError as exc:
            self._controller.message.emit(str(exc))
            return
        self._set_checked(me.id, True)

    def _apply_search(self) -> None:
        needle = self.search.text().strip().casefold()
        for item in self._player_items():
            item.setHidden(bool(needle) and needle not in item.text(0).casefold())

    def _clear_players(self, message: str) -> None:
        self.players.clear()
        self.players_label.setText(message)
        self._set_players_enabled(False)

    def _set_players_enabled(self, enabled: bool) -> None:
        for widget in (self.search, self.my_spec_button, self.me_button, self.players):
            widget.setEnabled(enabled)
        if not enabled:
            self.players_label.setStyleSheet(f"color: {TEXT_DIM};")
        else:
            self.players_label.setStyleSheet("")
