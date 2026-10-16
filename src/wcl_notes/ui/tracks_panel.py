"""« Pistes » tab: what is on the timeline, with visibility, color and removal."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from wcl_notes.domain.models import TrackRef
from wcl_notes.i18n import tr
from wcl_notes.labels import difficulty_label, format_duration, spec_label
from wcl_notes.services.workspace import COMFORTABLE_TRACK_COUNT, TrackEntry
from wcl_notes.ui.controller import AppController
from wcl_notes.ui.style import WARNING, class_color

VISIBLE, COLOR, PLAYER, FIGHT, ACTIONS = range(5)


class TracksPanel(QWidget):
    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "", tr("Joueur"), tr("Fight"), ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(PLAYER, QHeaderView.ResizeMode.Stretch)

        self.empty_label = QLabel(
            tr("Aucune piste. Cochez des joueurs dans l'onglet Log pour les ajouter.")
        )
        self.empty_label.setWordWrap(True)
        self.warning_label = QLabel(
            tr(
                "Plus de {n} pistes : la timeline devient difficile à lire "
                "et chaque piste consomme du quota API."
            ).format(n=COMFORTABLE_TRACK_COUNT)
        )
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet(f"color: {WARNING};")
        self.clear_button = QPushButton(tr("Vider la timeline"))
        self.clear_button.clicked.connect(controller.clear)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.clear_button)

        controller.workspace_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        entries = self._controller.workspace.entries
        # Drop the previous rows (and their cell widgets) before rebuilding.
        self.table.setRowCount(0)
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            self._fill_row(row, entry)
        self.table.resizeRowsToContents()
        self.empty_label.setVisible(not entries)
        self.clear_button.setEnabled(bool(entries))
        self.warning_label.setVisible(len(entries) > COMFORTABLE_TRACK_COUNT)

    def _fill_row(self, row: int, entry: TrackEntry) -> None:
        ref = entry.ref
        track = entry.track
        tooltip = f"{spec_label(track.player)} — {entry.origin}\n{entry.report_title}"

        visible = QCheckBox()
        visible.setChecked(entry.visible)
        visible.setToolTip(tr("Afficher sur la timeline"))
        visible.toggled.connect(lambda checked, r=ref: self._controller.set_visible(r, checked))
        self.table.setCellWidget(row, VISIBLE, _centered(visible))

        color = QToolButton()
        color.setToolTip(tr("Couleur de la piste"))
        color.setFixedSize(18, 18)
        color.setStyleSheet(f"background: {entry.color}; border: 1px solid #000;")
        color.clicked.connect(lambda _=False, r=ref, c=entry.color: self._pick_color(r, c))
        self.table.setCellWidget(row, COLOR, _centered(color))

        player = QTableWidgetItem(f"{track.player.name}  ·  {spec_label(track.player)}")
        player.setForeground(QBrush(class_color(track.player.sub_type)))
        player.setToolTip(tooltip)
        self.table.setItem(row, PLAYER, player)
        fight = QTableWidgetItem(
            f"{difficulty_label(track.fight.difficulty)} · "
            f"{format_duration(track.fight.duration_ms)}"
        )
        fight.setToolTip(tooltip)
        self.table.setItem(row, FIGHT, fight)

        open_log = QToolButton()
        open_log.setText("WCL")
        open_log.setToolTip(tr("Ouvrir le log sur Warcraft Logs"))
        open_log.clicked.connect(
            lambda _=False, url=entry.wcl_url: QDesktopServices.openUrl(QUrl(url))
        )
        remove = QToolButton()
        remove.setText("✕")
        remove.setToolTip(tr("Retirer la piste"))
        remove.clicked.connect(lambda _=False, r=ref: self._controller.remove_track(r))
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(2, 0, 2, 0)
        actions_layout.addWidget(open_log)
        actions_layout.addWidget(remove)
        self.table.setCellWidget(row, ACTIONS, actions)

    def _pick_color(self, ref: TrackRef, current: str) -> None:
        color = QColorDialog.getColor(QColor(current), self, tr("Couleur de la piste"))
        if color.isValid():
            self._controller.set_color(ref, color.name())


def _centered(widget: QWidget) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(widget)
    return holder
