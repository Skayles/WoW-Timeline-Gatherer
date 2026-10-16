"""« Copier la note » dialog, modelled on Lorrgs' Copy Note window."""

import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wcl_notes.domain.models import TrackRef
from wcl_notes.domain.names import character_name
from wcl_notes.i18n import tr
from wcl_notes.labels import spec_label
from wcl_notes.services.notes import NoteFormat, NoteOptions, NoteResult, build_note
from wcl_notes.services.workspace import TrackEntry
from wcl_notes.ui.controller import AppController
from wcl_notes.ui.settings import AppSettings
from wcl_notes.ui.style import TEXT_DIM, WARNING, monospace_font

KILL_TIME_RE = re.compile(r"^\s*(\d{1,2}):([0-5]\d)\s*$")


def parse_kill_time(text: str) -> int | None:
    """Parse a kill time such as "5:26" into milliseconds; None when invalid."""
    match = KILL_TIME_RE.match(text)
    if not match:
        return None
    return (int(match.group(1)) * 60 + int(match.group(2))) * 1000


class CopyNoteDialog(QDialog):
    def __init__(
        self,
        controller: AppController,
        settings: AppSettings,
        preferred: TrackRef | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Copier la note"))
        self.resize(720, 640)
        self._controller = controller
        self._settings = settings
        self._entries: list[TrackEntry] = list(controller.workspace.visible_entries()) or list(
            controller.workspace.entries
        )

        self.mrt = QRadioButton("MRT")
        self.nsrt = QRadioButton("NSRT")
        formats = QButtonGroup(self)
        formats.addButton(self.mrt)
        formats.addButton(self.nsrt)
        (self.nsrt if settings.note_format == NoteFormat.NSRT else self.mrt).setChecked(True)
        format_row = QHBoxLayout()
        format_row.addWidget(self.mrt)
        format_row.addWidget(self.nsrt)
        format_row.addStretch(1)

        self.raid_mode = QCheckBox(tr("Note de raid (plusieurs pistes, un nom par piste)"))
        self.raid_mode.setEnabled(len(self._entries) > 1)

        self.source = QComboBox()
        for entry in self._entries:
            self.source.addItem(_entry_label(entry), entry.ref)
        if preferred is not None:
            index = self.source.findData(preferred)
            if index >= 0:
                self.source.setCurrentIndex(index)
        self.player_name = QLineEdit(settings.player_name)
        self.player_name.setPlaceholderText(tr("Nom à écrire dans la note"))

        self.raid_table = QTableWidget(len(self._entries), 3)
        self.raid_table.setHorizontalHeaderLabels(["", tr("Piste source"), tr("Nom dans la note")])
        self.raid_table.verticalHeader().setVisible(False)
        self.raid_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.raid_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for row, entry in enumerate(self._entries):
            include = QTableWidgetItem()
            include.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            include.setCheckState(Qt.CheckState.Checked)
            source = QTableWidgetItem(_entry_label(entry))
            source.setFlags(Qt.ItemFlag.ItemIsEnabled)
            name = QTableWidgetItem(character_name(entry.track.player.name))
            self.raid_table.setItem(row, 0, include)
            self.raid_table.setItem(row, 1, source)
            self.raid_table.setItem(row, 2, name)

        self.offset = QDoubleSpinBox()
        self.offset.setRange(0, 30)
        self.offset.setSingleStep(0.5)
        self.offset.setDecimals(1)
        self.offset.setSuffix(" s")
        self.offset.setValue(settings.offset_s)
        self.offset.setToolTip(tr("Avancer chaque cast pour être prévenu avant"))
        self.dur = QSpinBox()
        self.dur.setRange(0, 30)
        self.dur.setSpecialValueText(tr("réglage NSRT"))
        self.dur.setSuffix(" s")
        self.dur.setValue(settings.nsrt_dur)
        self.dur.setToolTip(tr("Durée d'affichage du reminder NSRT (dur)"))
        self.merge = QDoubleSpinBox()
        self.merge.setRange(0, 10)
        self.merge.setSingleStep(0.5)
        self.merge.setDecimals(1)
        self.merge.setSuffix(" s")
        self.merge.setSpecialValueText(tr("jamais"))
        self.merge.setValue(settings.merge_s)
        self.merge.setToolTip(tr("Un même sort relancé dans cet intervalle ne donne qu'une ligne"))
        self.kill_time = QLineEdit()
        self.kill_time.setPlaceholderText(tr("m:ss, optionnel"))
        self.kill_time.setToolTip(
            tr("Temps de kill de votre raid, pour être averti si le log source est très différent")
        )

        form = QFormLayout()
        form.addRow(tr("Format"), format_row)
        form.addRow("", self.raid_mode)
        form.addRow(tr("Piste source"), self.source)
        form.addRow(tr("Player Name"), self.player_name)
        form.addRow(tr("Décalage"), self.offset)
        form.addRow(tr("Durée NSRT"), self.dur)
        form.addRow(tr("Regrouper"), self.merge)
        form.addRow(tr("Mon temps de kill"), self.kill_time)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(monospace_font())
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.warnings = QLabel()
        self.warnings.setWordWrap(True)
        self.warnings.setStyleSheet(f"color: {WARNING};")
        self.infos = QLabel()
        self.infos.setWordWrap(True)
        self.infos.setStyleSheet(f"color: {TEXT_DIM};")
        caution = QLabel(
            tr(
                "⚠ Adaptez la note à votre composition et à votre temps de kill "
                "avant de l'utiliser."
            )
        )
        caution.setWordWrap(True)
        caution.setStyleSheet(f"color: {WARNING};")

        self.copy_button = QPushButton(tr("Copier"))
        self.copy_button.setDefault(True)
        self.copy_button.clicked.connect(self.copy)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.addButton(self.copy_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.raid_table)
        layout.addWidget(QLabel(tr("Aperçu")))
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.infos)
        layout.addWidget(self.warnings)
        layout.addWidget(caution)
        layout.addWidget(buttons)

        for signal in (
            self.mrt.toggled,
            self.raid_mode.toggled,
        ):
            signal.connect(self.refresh)
        self.source.currentIndexChanged.connect(self.refresh)
        self.player_name.textChanged.connect(self.refresh)
        self.offset.valueChanged.connect(self.refresh)
        self.dur.valueChanged.connect(self.refresh)
        self.merge.valueChanged.connect(self.refresh)
        self.kill_time.textChanged.connect(self.refresh)
        self.raid_table.itemChanged.connect(self.refresh)
        controller.selection_changed.connect(self.refresh)
        self.refresh()

    def note_format(self) -> NoteFormat:
        return NoteFormat.NSRT if self.nsrt.isChecked() else NoteFormat.MRT

    def targets(self) -> list[tuple[TrackRef, str]]:
        if self.raid_mode.isChecked():
            targets = []
            for row, entry in enumerate(self._entries):
                include = self.raid_table.item(row, 0)
                name = self.raid_table.item(row, 2)
                if include is None or include.checkState() != Qt.CheckState.Checked:
                    continue
                text = name.text().strip() if name is not None else ""
                targets.append((entry.ref, text or character_name(entry.track.player.name)))
            return targets
        ref = self.source.currentData()
        source = next((e for e in self._entries if e.ref == ref), None)
        if source is None:
            return []
        # Without a name, the note keeps the source player's name.
        target_name = self.player_name.text().strip() or self._settings.player_name
        return [(source.ref, target_name or character_name(source.track.player.name))]

    def options(self) -> NoteOptions:
        return NoteOptions(
            format=self.note_format(),
            offset_ms=round(self.offset.value() * 1000),
            dur=self.dur.value() or None,
            my_kill_ms=parse_kill_time(self.kill_time.text()),
            merge_window_ms=round(self.merge.value() * 1000),
        )

    def note_result(self) -> NoteResult:
        assignments = self._controller.workspace.note_assignments(self.targets())
        return build_note(assignments, self.options())

    def refresh(self) -> None:
        raid = self.raid_mode.isChecked()
        self.raid_table.setVisible(raid)
        self.source.setEnabled(not raid)
        self.player_name.setEnabled(not raid)
        self.dur.setEnabled(self.nsrt.isChecked())
        result = self.note_result()
        self.preview.setPlainText(result.text)
        self.infos.setText("\n".join(result.infos))
        self.infos.setVisible(bool(result.infos))
        self.warnings.setText("\n".join(f"⚠ {w}" for w in result.warnings))
        self.warnings.setVisible(bool(result.warnings))
        self.copy_button.setEnabled(bool(result.text.strip()))

    def copy(self) -> None:
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self.preview.toPlainText())
        self._remember()
        self.copy_button.setText(tr("Copié ✓"))
        QTimer.singleShot(1500, lambda: self.copy_button.setText(tr("Copier")))

    def _remember(self) -> None:
        if not self.raid_mode.isChecked() and self.player_name.text().strip():
            self._settings.player_name = self.player_name.text()
        self._settings.note_format = self.note_format().value
        self._settings.offset_s = self.offset.value()
        self._settings.nsrt_dur = self.dur.value()
        self._settings.merge_s = self.merge.value()

    def done(self, result: int) -> None:
        self._remember()
        super().done(result)


def _entry_label(entry: TrackEntry) -> str:
    track = entry.track
    return f"{track.player.name} ({spec_label(track.player)}) — {entry.origin}"
