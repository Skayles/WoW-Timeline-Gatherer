"""Spell legend: ticking a spell shows it on the timeline and puts it in the note."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wcl_notes.labels import CATEGORY_LABELS, OTHER_CATEGORY_LABEL
from wcl_notes.ui.controller import AppController
from wcl_notes.ui.icons import IconProvider
from wcl_notes.ui.style import TEXT_DIM

SPELL_ID_ROLE = Qt.ItemDataRole.UserRole
ICON_SIZE = 22


class LegendPanel(QWidget):
    def __init__(
        self, controller: AppController, icons: IconProvider, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._icons = icons
        self._updating = False

        title = QLabel(self.tr("Sorts"))
        font = QFont(title.font())
        font.setBold(True)
        title.setFont(font)
        self.show_all = QCheckBox(self.tr("Tous les casts"))
        self.show_all.setToolTip(
            self.tr("Lister aussi les sorts absents de la liste de la spé (sorts de rotation…)")
        )
        self.show_all.toggled.connect(controller.set_show_all)

        self.list = QListWidget()
        self.list.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.list.itemChanged.connect(self._on_item_changed)

        hint = QLabel(
            self.tr(
                "Décocher un sort le retire de la timeline et de la note. "
                "Cliquer sur un cast de la timeline le désactive seul."
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {TEXT_DIM};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(title)
        layout.addWidget(self.show_all)
        layout.addWidget(self.list, 1)
        layout.addWidget(hint)

        controller.workspace_changed.connect(self.refresh)
        controller.selection_changed.connect(self.refresh)
        icons.icon_ready.connect(lambda _: self.refresh())
        self.refresh()

    def refresh(self) -> None:
        self._updating = True
        scroll = self.list.verticalScrollBar().value()
        self.list.clear()
        self.show_all.setChecked(self._controller.workspace.selection.show_all)
        current_category: object = None
        for entry in self._controller.workspace.legend():
            if entry.category != current_category or self.list.count() == 0:
                current_category = entry.category
                label = CATEGORY_LABELS[entry.category] if entry.category else OTHER_CATEGORY_LABEL
                header = QListWidgetItem(label)
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                font = QFont(header.font())
                font.setBold(True)
                header.setFont(font)
                self.list.addItem(header)
            item = QListWidgetItem(
                QIcon(self._icons.pixmap(entry.spell.icon, ICON_SIZE)),
                f"{entry.spell.name}  ({entry.count})",
            )
            item.setData(SPELL_ID_ROLE, entry.spell.id)
            item.setToolTip(f"{entry.spell.name} — ID {entry.spell.id}")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if entry.included else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        self.list.verticalScrollBar().setValue(scroll)
        self._updating = False

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._updating:
            return
        spell_id = item.data(SPELL_ID_ROLE)
        if isinstance(spell_id, int):
            self._controller.set_spell_included(
                spell_id, item.checkState() == Qt.CheckState.Checked
            )
