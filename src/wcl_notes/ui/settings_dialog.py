"""« Réglages » dialog: my name, my spec, and the WCL API credentials (OS keyring)."""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from wcl_notes.api.credentials import Credentials, store_credentials
from wcl_notes.ui.settings import AppSettings
from wcl_notes.ui.style import TEXT_DIM


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Réglages"))
        self.setMinimumWidth(460)
        self._settings = settings
        self.credentials_changed = False

        self.player_name = QLineEdit(settings.player_name)
        self.my_spec = QLineEdit(settings.my_spec)
        self.my_spec.setPlaceholderText("Rogue-Assassination")
        self.my_spec.setToolTip(
            self.tr("Classe-Spé telle qu'écrite par Warcraft Logs, ex. Rogue-Assassination")
        )
        player = QFormLayout()
        player.addRow(self.tr("Nom du joueur"), self.player_name)
        player.addRow(self.tr("Ma spé"), self.my_spec)

        self.client_id = QLineEdit()
        self.client_id.setPlaceholderText(self.tr("inchangé"))
        self.client_secret = QLineEdit()
        self.client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.client_secret.setPlaceholderText(self.tr("inchangé"))
        api_box = QGroupBox(self.tr("API Warcraft Logs"))
        api = QFormLayout(api_box)
        api.addRow(self.tr("Client ID"), self.client_id)
        api.addRow(self.tr("Client Secret"), self.client_secret)
        note = QLabel(
            self.tr(
                "Créez un client sur warcraftlogs.com/api/clients. Les identifiants sont "
                "enregistrés dans le gestionnaire d'identifiants Windows ; un fichier .env ou "
                "des variables d'environnement restent prioritaires."
            )
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {TEXT_DIM};")
        api.addRow(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(player)
        layout.addWidget(api_box)
        layout.addWidget(buttons)

    def accept(self) -> None:
        client_id = self.client_id.text().strip()
        client_secret = self.client_secret.text().strip()
        if bool(client_id) != bool(client_secret):
            QMessageBox.warning(
                self,
                self.tr("Identifiants incomplets"),
                self.tr("Renseignez à la fois le Client ID et le Client Secret."),
            )
            return
        if client_id:
            try:
                store_credentials(Credentials(client_id, client_secret))
            except Exception as exc:  # keyring backends raise various errors
                QMessageBox.warning(
                    self,
                    self.tr("Trousseau indisponible"),
                    self.tr("Impossible d'enregistrer les identifiants : {error}").format(
                        error=exc
                    ),
                )
                return
            self.credentials_changed = True
        self._settings.player_name = self.player_name.text()
        self._settings.my_spec = self.my_spec.text()
        super().accept()
