"""« Réglages » dialog: my name, my spec, the WCL API credentials (OS keyring), the cache."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wcl_notes.api.credentials import Credentials, store_credentials
from wcl_notes.cache.response_cache import ResponseCache
from wcl_notes.i18n import LANGUAGES, tr
from wcl_notes.ui.settings import AppSettings
from wcl_notes.ui.style import TEXT_DIM


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: AppSettings,
        parent: QWidget | None = None,
        *,
        cache: ResponseCache | None = None,
    ) -> None:
        super().__init__(parent)
        self._cache = cache
        self.setWindowTitle(tr("Réglages"))
        self.setMinimumWidth(460)
        self._settings = settings
        self.credentials_changed = False

        self.player_name = QLineEdit(settings.player_name)
        self.player_name.setPlaceholderText(tr("Nom de votre personnage"))
        self.my_spec = QLineEdit(settings.my_spec)
        self.my_spec.setPlaceholderText("Rogue-Assassination")
        self.my_spec.setToolTip(
            tr("Classe-Spé telle qu'écrite par Warcraft Logs, ex. Rogue-Assassination")
        )
        self.language = QComboBox()
        self.language.addItem(tr("Langue du système"), "")
        for code, name in LANGUAGES.items():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(self.language.findData(settings.language), 0))
        player = QFormLayout()
        player.addRow(tr("Nom du joueur"), self.player_name)
        player.addRow(tr("Ma spé"), self.my_spec)
        player.addRow(tr("Langue / Language"), self.language)

        self.client_id = QLineEdit()
        self.client_id.setPlaceholderText(tr("inchangé"))
        self.client_secret = QLineEdit()
        self.client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.client_secret.setPlaceholderText(tr("inchangé"))
        api_box = QGroupBox(tr("API Warcraft Logs"))
        api = QFormLayout(api_box)
        api.addRow(tr("Client ID"), self.client_id)
        api.addRow(tr("Client Secret"), self.client_secret)
        note = QLabel(
            tr(
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

        cache_box = QGroupBox(tr("Cache local"))
        cache_layout = QVBoxLayout(cache_box)
        self.cache_label = QLabel()
        self.cache_label.setWordWrap(True)
        self.clear_cache_button = QPushButton(tr("Vider le cache"))
        self.clear_cache_button.clicked.connect(self._clear_cache)
        cache_row = QHBoxLayout()
        cache_row.addWidget(self.cache_label, 1)
        cache_row.addWidget(self.clear_cache_button)
        cache_layout.addLayout(cache_row)
        cache_note = QLabel(
            tr(
                "Les logs terminés sont gardés sans limite de durée (ils ne changent plus) : "
                "les recharger ne coûte aucun point d'API. Les classements expirent après 1 h."
            )
        )
        cache_note.setWordWrap(True)
        cache_note.setStyleSheet(f"color: {TEXT_DIM};")
        cache_layout.addWidget(cache_note)
        self._refresh_cache_label()

        layout = QVBoxLayout(self)
        layout.addLayout(player)
        layout.addWidget(api_box)
        layout.addWidget(cache_box)
        layout.addWidget(buttons)

    def _refresh_cache_label(self) -> None:
        if self._cache is None:
            self.cache_label.setText(tr("Cache indisponible."))
            self.clear_cache_button.setEnabled(False)
            return
        stats = self._cache.stats()
        self.cache_label.setText(
            tr("{n} réponse(s), {size:.1f} Mo — {path}").format(
                n=stats.entries, size=stats.size_bytes / 1_000_000, path=self._cache.path
            )
        )
        self.clear_cache_button.setEnabled(stats.entries > 0)

    def _clear_cache(self) -> None:
        if self._cache is None:
            return
        answer = QMessageBox.question(
            self,
            tr("Vider le cache"),
            tr("Supprimer toutes les réponses gardées ? Les logs seront re-téléchargés."),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._cache.clear()
            self._refresh_cache_label()

    def accept(self) -> None:
        client_id = self.client_id.text().strip()
        client_secret = self.client_secret.text().strip()
        if bool(client_id) != bool(client_secret):
            QMessageBox.warning(
                self,
                tr("Identifiants incomplets"),
                tr("Renseignez à la fois le Client ID et le Client Secret."),
            )
            return
        if client_id:
            try:
                store_credentials(Credentials(client_id, client_secret))
            except Exception as exc:  # keyring backends raise various errors
                QMessageBox.warning(
                    self,
                    tr("Trousseau indisponible"),
                    tr("Impossible d'enregistrer les identifiants : {error}").format(error=exc),
                )
                return
            self.credentials_changed = True
        self._settings.player_name = self.player_name.text()
        self._settings.my_spec = self.my_spec.text()
        language = str(self.language.currentData() or "")
        if language != self._settings.language:
            self._settings.language = language
            QMessageBox.information(
                self,
                tr("Langue / Language"),
                tr("Redémarrez l'application pour changer de langue."),
            )
        super().accept()
