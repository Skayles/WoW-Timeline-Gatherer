"""« Classements » tab: top logs of a spec on a boss, ticked rows go on the timeline."""

from dataclasses import replace
from datetime import datetime

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wcl_notes.domain.models import Difficulty
from wcl_notes.domain.rankings import GameCatalog, RankingEntry, RankingQuery, RankingsPage
from wcl_notes.labels import difficulty_label, format_duration
from wcl_notes.services.rankings import (
    METRICS,
    RankingSort,
    default_metric,
    filter_rankings,
    sort_rankings,
)
from wcl_notes.ui.controller import AppController, RankingKey, TrackState, ranking_key
from wcl_notes.ui.copy_note_dialog import parse_kill_time
from wcl_notes.ui.icons import IconProvider
from wcl_notes.ui.settings import AppSettings
from wcl_notes.ui.style import ERROR, TEXT_DIM, class_color

ENTRY_ROLE = Qt.ItemDataRole.UserRole
ICON_SIZE = 20
REGIONS = ("", "EU", "US", "KR", "TW", "CN")
SORT_LABELS = {RankingSort.RANK: "Rang", RankingSort.DURATION: "Durée", RankingSort.DATE: "Date"}
STATE_LABELS = {
    TrackState.LOADING: "chargement…",
    TrackState.LOADED: "✓",
    TrackState.ERROR: "erreur",
}
COLUMNS = ("#", "Joueur", "Montant", "Kill", "Date", "État")


def format_amount(amount: float) -> str:
    return f"{amount / 1000:.1f}k" if amount >= 1000 else f"{amount:.0f}"


class RankingsPanel(QWidget):
    def __init__(
        self,
        controller: AppController,
        settings: AppSettings,
        icons: IconProvider,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._settings = settings
        self._icons = icons
        self._entries: list[RankingEntry] = []
        self._query: RankingQuery | None = None
        self._has_more = False
        self._updating = False
        self._catalog_requested = False

        self.raid = QComboBox()
        self.boss = QComboBox()
        self.difficulty = QComboBox()
        for difficulty in (Difficulty.MYTHIC, Difficulty.HEROIC, Difficulty.NORMAL, Difficulty.LFR):
            self.difficulty.addItem(difficulty_label(difficulty), int(difficulty))
        self.region = QComboBox()
        for region in REGIONS:
            self.region.addItem(region or self.tr("Toutes"), region)
        self.game_class = QComboBox()
        self.spec = QComboBox()
        self.metric_box = QComboBox()
        for metric in METRICS:
            self.metric_box.addItem(metric.upper(), metric)
        self.search_button = QPushButton(self.tr("Rechercher"))
        self.search_button.clicked.connect(self.search)

        self.raid.currentIndexChanged.connect(self._fill_bosses)
        self.game_class.currentIndexChanged.connect(self._fill_specs)
        self.spec.currentIndexChanged.connect(self._on_spec_changed)

        filters = QFormLayout()
        filters.addRow(self.tr("Raid"), self.raid)
        filters.addRow(self.tr("Boss"), self.boss)
        row = QHBoxLayout()
        row.addWidget(self.difficulty, 1)
        row.addWidget(QLabel(self.tr("Région")))
        row.addWidget(self.region)
        filters.addRow(self.tr("Difficulté"), row)
        spec_row = QHBoxLayout()
        spec_row.addWidget(self.game_class, 1)
        spec_row.addWidget(self.spec, 1)
        filters.addRow(self.tr("Classe / spé"), spec_row)
        metric_row = QHBoxLayout()
        metric_row.addWidget(self.metric_box)
        metric_row.addStretch(1)
        metric_row.addWidget(self.search_button)
        filters.addRow(self.tr("Métrique"), metric_row)

        self.min_kill = QLineEdit()
        self.min_kill.setPlaceholderText("m:ss")
        self.max_kill = QLineEdit()
        self.max_kill.setPlaceholderText("m:ss")
        for edit in (self.min_kill, self.max_kill):
            edit.setMaximumWidth(70)
            edit.textChanged.connect(self.refresh)
        self.name_filter = QLineEdit()
        self.name_filter.setPlaceholderText(self.tr("Nom"))
        self.name_filter.setClearButtonEnabled(True)
        self.name_filter.textChanged.connect(self.refresh)
        self.sort = QComboBox()
        for key, label in SORT_LABELS.items():
            self.sort.addItem(self.tr(label), key.value)
        self.sort.currentIndexChanged.connect(self.refresh)
        local = QHBoxLayout()
        local.addWidget(QLabel(self.tr("Kill de")))
        local.addWidget(self.min_kill)
        local.addWidget(QLabel(self.tr("à")))
        local.addWidget(self.max_kill)
        local.addWidget(self.name_filter, 1)
        local.addWidget(QLabel(self.tr("Tri")))
        local.addWidget(self.sort)

        self.table = QTreeWidget()
        self.table.setHeaderLabels([self.tr(c) for c in COLUMNS])
        self.table.setRootIsDecorated(False)
        self.table.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.table.itemChanged.connect(self._on_item_changed)
        self.status = QLabel(self.tr("Choisissez un boss et une spé, puis Rechercher."))
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {TEXT_DIM};")
        self.more_button = QPushButton(self.tr("Page suivante"))
        self.more_button.clicked.connect(self.load_more)
        self.more_button.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(filters)
        layout.addLayout(local)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.more_button)
        self._set_search_enabled(False)

        controller.catalog_loaded.connect(self._on_catalog)
        controller.rankings_loaded.connect(self._on_rankings)
        controller.ranking_state_changed.connect(self._on_ranking_state)
        controller.workspace_changed.connect(self._refresh_states)
        icons.icon_ready.connect(lambda _: self._refresh_icons())

    # --- catalog ------------------------------------------------------------------

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.ensure_catalog()

    def ensure_catalog(self) -> None:
        """The catalog costs API points: load it the first time the tab is shown."""
        if self._catalog_requested:
            return
        self._catalog_requested = True
        self.status.setText(self.tr("Chargement des raids et des spés…"))
        self._controller.load_catalog()

    def _on_catalog(self, catalog: GameCatalog) -> None:
        self._updating = True
        self.raid.clear()
        for zone in catalog.raids:
            label = zone.name if not zone.frozen else f"{zone.name} ({self.tr('ancien')})"
            self.raid.addItem(label, zone.id)
        self.game_class.clear()
        for game_class in catalog.classes:
            self.game_class.addItem(game_class.name, game_class.slug)
        my_class, _, my_spec = self._settings.my_spec.partition("-")
        index = self.game_class.findData(my_class)
        self.game_class.setCurrentIndex(max(index, 0))
        self._updating = False
        self._fill_bosses()
        self._fill_specs()
        spec_index = self.spec.findData(my_spec)
        if spec_index >= 0:
            self.spec.setCurrentIndex(spec_index)
        self._set_search_enabled(bool(catalog.raids))
        self.status.setText(self.tr("Choisissez un boss et une spé, puis Rechercher."))

    def _fill_bosses(self) -> None:
        catalog = self._controller.catalog
        if catalog is None or self._updating:
            return
        zone = next((z for z in catalog.raids if z.id == self.raid.currentData()), None)
        self.boss.clear()
        for encounter in zone.encounters if zone else ():
            self.boss.addItem(encounter.name, encounter.id)

    def _fill_specs(self) -> None:
        catalog = self._controller.catalog
        if catalog is None or self._updating:
            return
        slug = self.game_class.currentData()
        game_class = next((c for c in catalog.classes if c.slug == slug), None)
        self.spec.clear()
        if game_class is None:
            return
        for spec in game_class.specs:
            icon = self._icons.spec_pixmap(f"{game_class.slug}-{spec.slug}", ICON_SIZE)
            self.spec.addItem(QIcon(icon), spec.name, spec.slug)

    def _on_spec_changed(self) -> None:
        spec = self.spec.currentData()
        if isinstance(spec, str):
            self.metric_box.setCurrentIndex(max(self.metric_box.findData(default_metric(spec)), 0))

    def _set_search_enabled(self, enabled: bool) -> None:
        for widget in (self.raid, self.boss, self.game_class, self.spec, self.search_button):
            widget.setEnabled(enabled)

    # --- rankings -----------------------------------------------------------------

    def current_query(self) -> RankingQuery | None:
        encounter, difficulty = self.boss.currentData(), self.difficulty.currentData()
        game_class, spec = self.game_class.currentData(), self.spec.currentData()
        if not all(isinstance(v, int) for v in (encounter, difficulty)):
            return None
        if not all(isinstance(v, str) for v in (game_class, spec)):
            return None
        return RankingQuery(
            encounter_id=encounter,
            difficulty=difficulty,
            class_name=game_class,
            spec=spec,
            metric=str(self.metric_box.currentData()),
            region=self.region.currentData() or None,
        )

    def search(self) -> None:
        query = self.current_query()
        if query is None:
            return
        self._query = query
        self._entries = []
        self._has_more = False
        self.table.clear()
        self._controller.load_rankings(query)

    def load_more(self) -> None:
        if self._query is not None and self._has_more:
            next_page = replace(self._query, page=self._query.page + 1)
            self._query = next_page
            self._controller.load_rankings(next_page)

    def _on_rankings(self, page: RankingsPage) -> None:
        # Ignore answers to an older search (e.g. the user changed the boss meanwhile).
        if self._query is None or page.query != self._query:
            return
        known = {ranking_key(e) for e in self._entries}
        self._entries.extend(e for e in page.entries if ranking_key(e) not in known)
        self._has_more = page.has_more
        self.more_button.setEnabled(page.has_more)
        self.refresh()

    def visible_entries(self) -> list[RankingEntry]:
        filtered = filter_rankings(
            self._entries,
            min_duration_ms=parse_kill_time(self.min_kill.text()),
            max_duration_ms=parse_kill_time(self.max_kill.text()),
            name=self.name_filter.text(),
        )
        return sort_rankings(filtered, RankingSort(self.sort.currentData()))

    def refresh(self) -> None:
        entries = self.visible_entries()
        self._updating = True
        self.table.clear()
        header = self.table.headerItem()
        if header is not None:
            header.setText(2, self._query.metric.upper() if self._query else self.tr("Montant"))
        for entry in entries:
            server = f"{entry.server}-{entry.region}" if entry.server else (entry.region or "")
            item = QTreeWidgetItem(
                [
                    str(entry.rank),
                    f"{entry.name}  ·  {server}",
                    format_amount(entry.amount),
                    format_duration(entry.duration_ms),
                    datetime.fromtimestamp(entry.start_time / 1000).strftime("%d/%m/%Y"),
                    "",
                ]
            )
            item.setData(0, ENTRY_ROLE, entry)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setIcon(1, QIcon(self._icons.spec_pixmap(entry.icon, ICON_SIZE)))
            item.setForeground(1, QBrush(class_color(entry.class_name)))
            item.setToolTip(1, entry.guild or "")
            for column in (0, 2, 3):
                item.setTextAlignment(column, Qt.AlignmentFlag.AlignRight)
            self._apply_state(item, entry)
            self.table.addTopLevelItem(item)
        for column in range(len(COLUMNS)):
            self.table.resizeColumnToContents(column)
        self._updating = False
        total = len(self._entries)
        self.status.setText(
            self.tr("{shown} classements affichés sur {total} chargés.").format(
                shown=len(entries), total=total
            )
            if total
            else self.tr("Aucun classement pour ces critères.")
        )

    def _apply_state(self, item: QTreeWidgetItem, entry: RankingEntry) -> None:
        state = self._controller.ranked_track_state(entry)
        checked = state in (TrackState.LOADING, TrackState.LOADED)
        item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        item.setText(5, STATE_LABELS.get(state or "", ""))
        item.setForeground(5, QBrush(QColor(ERROR if state == TrackState.ERROR else TEXT_DIM)))

    def _items(self) -> list[QTreeWidgetItem]:
        items = [self.table.topLevelItem(i) for i in range(self.table.topLevelItemCount())]
        return [item for item in items if item is not None]

    def _refresh_states(self) -> None:
        self._updating = True
        for item in self._items():
            entry = item.data(0, ENTRY_ROLE)
            if isinstance(entry, RankingEntry):
                self._apply_state(item, entry)
        self._updating = False

    def _on_ranking_state(self, _: RankingKey) -> None:
        self._refresh_states()

    def _refresh_icons(self) -> None:
        game_class = self.game_class.currentData()
        for index in range(self.spec.count()):
            icon = f"{game_class}-{self.spec.itemData(index)}"
            self.spec.setItemIcon(index, QIcon(self._icons.spec_pixmap(icon, ICON_SIZE)))
        for item in self._items():
            entry = item.data(0, ENTRY_ROLE)
            if isinstance(entry, RankingEntry):
                item.setIcon(1, QIcon(self._icons.spec_pixmap(entry.icon, ICON_SIZE)))

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating or column != 0 or self._query is None:
            return
        entry = item.data(0, ENTRY_ROLE)
        if not isinstance(entry, RankingEntry):
            return
        if item.checkState(0) != Qt.CheckState.Checked:
            self._controller.remove_ranked_track(entry)
            return
        encounter_id = self._query.encounter_id
        if not self._controller.workspace.accepts(encounter_id):
            answer = QMessageBox.question(
                self,
                self.tr("Autre boss"),
                self.tr("La timeline contient des pistes d'un autre boss. La vider ?"),
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._refresh_states()
                return
            self._controller.clear()
        self._controller.add_ranked_track(entry, encounter_id)
