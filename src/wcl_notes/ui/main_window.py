"""Main window: side panel (Classements / Log / Pistes), timeline, spell legend."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QTabWidget,
    QToolBar,
    QWidget,
)

from wcl_notes import __version__
from wcl_notes.ui.controller import AppController
from wcl_notes.ui.copy_note_dialog import CopyNoteDialog
from wcl_notes.ui.icons import IconProvider
from wcl_notes.ui.legend_panel import LegendPanel
from wcl_notes.ui.log_panel import LogPanel
from wcl_notes.ui.settings import AppSettings
from wcl_notes.ui.settings_dialog import SettingsDialog
from wcl_notes.ui.style import TEXT_DIM
from wcl_notes.ui.timeline_view import TimelineView
from wcl_notes.ui.tracks_panel import TracksPanel
from wcl_notes.ui.workers import TaskRunner

LOG_TAB = 1


class MainWindow(QMainWindow):
    def __init__(
        self,
        controller: AppController,
        settings: AppSettings,
        icons: IconProvider,
        runner: TaskRunner,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("WoW Timeline Gatherer {version}").format(version=__version__))
        self.resize(1500, 860)
        self._controller = controller
        self._settings = settings

        rankings = QLabel(
            self.tr("Classements des meilleurs logs : bientôt (étape 4 de la feuille de route).")
        )
        rankings.setWordWrap(True)
        rankings.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rankings.setStyleSheet(f"color: {TEXT_DIM}; padding: 20px;")
        self.log_panel = LogPanel(controller, settings)
        self.tracks_panel = TracksPanel(controller)
        self.tabs = QTabWidget()
        self.tabs.addTab(rankings, self.tr("Classements"))
        self.tabs.addTab(self.log_panel, self.tr("Log"))
        self.tabs.addTab(self.tracks_panel, self.tr("Pistes"))
        self.tabs.setCurrentIndex(LOG_TAB)

        self.timeline = TimelineView(controller, icons)
        self.legend = LegendPanel(controller, icons)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.tabs)
        splitter.addWidget(self.timeline)
        splitter.addWidget(self.legend)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([400, 850, 250])
        self.setCentralWidget(splitter)

        self.copy_action = QAction(self.tr("Copier la note…"), self)
        self.copy_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self.copy_action.triggered.connect(self.open_copy_note)
        settings_action = QAction(self.tr("Réglages…"), self)
        settings_action.triggered.connect(self.open_settings)
        zoom_in = QAction(self.tr("Zoom +"), self)
        zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zoom_in.triggered.connect(self.timeline.zoom_in)
        zoom_out = QAction(self.tr("Zoom -"), self)
        zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zoom_out.triggered.connect(self.timeline.zoom_out)
        toolbar = QToolBar(self.tr("Actions"))
        toolbar.setMovable(False)
        toolbar.addAction(self.copy_action)
        toolbar.addSeparator()
        toolbar.addAction(zoom_in)
        toolbar.addAction(zoom_out)
        toolbar.addSeparator()
        toolbar.addAction(settings_action)
        self.addToolBar(toolbar)

        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setMaximumWidth(120)
        self.busy.setVisible(False)
        self.statusBar().addPermanentWidget(self.busy)
        self.statusBar().showMessage(
            self.tr("Collez une URL Warcraft Logs dans l'onglet Log pour commencer.")
        )

        runner.busy_changed.connect(self.busy.setVisible)
        controller.error.connect(self.show_error)
        controller.message.connect(lambda text: self.statusBar().showMessage(text, 8000))
        controller.workspace_changed.connect(self._update_actions)
        self._update_actions()

    def _update_actions(self) -> None:
        self.copy_action.setEnabled(bool(self._controller.workspace.entries))

    def show_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 10000)
        QMessageBox.warning(self, self.tr("Warcraft Logs"), message)

    def open_copy_note(self) -> None:
        if not self._controller.workspace.entries:
            return
        CopyNoteDialog(self._controller, self._settings, parent=self).exec()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() and dialog.credentials_changed:
            self._controller.reset_client()
            self.statusBar().showMessage(self.tr("Identifiants enregistrés."), 5000)
