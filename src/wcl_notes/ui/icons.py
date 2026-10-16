"""Spell icons: memory cache, then disk cache, then download from the WCL CDN."""

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, QStandardPaths, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap

from wcl_notes.api.icons import download_icon, is_safe_icon_name
from wcl_notes.ui.style import BORDER, SURFACE_ALT, TEXT_DIM
from wcl_notes.ui.workers import TaskRunner

log = logging.getLogger(__name__)


def default_cache_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
    return Path(base) / "icons"


class IconProvider(QObject):
    icon_ready = Signal(str)

    def __init__(
        self,
        runner: TaskRunner,
        cache_dir: Path | None = None,
        *,
        download: bool = True,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._runner = runner
        self._cache_dir = cache_dir if cache_dir is not None else default_cache_dir()
        self._download = download
        self._pixmaps: dict[str, QPixmap] = {}
        self._requested: set[str] = set()
        self._placeholders: dict[int, QPixmap] = {}

    def pixmap(self, icon_name: str | None, size: int) -> QPixmap:
        """The icon at ``size``, or a placeholder while it downloads (then ``icon_ready``)."""
        if not icon_name or not is_safe_icon_name(icon_name):
            return self._placeholder(size)
        source = self._pixmaps.get(icon_name) or self._load_from_disk(icon_name)
        if source is None:
            self._request(icon_name)
            return self._placeholder(size)
        return source.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _load_from_disk(self, icon_name: str) -> QPixmap | None:
        path = self._cache_dir / icon_name
        if not path.is_file():
            return None
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return None
        self._pixmaps[icon_name] = pixmap
        return pixmap

    def _request(self, icon_name: str) -> None:
        if not self._download or icon_name in self._requested:
            return
        self._requested.add(icon_name)

        def stored(data: object) -> None:
            if not isinstance(data, bytes):
                return
            pixmap = QPixmap()
            if not pixmap.loadFromData(data):
                return
            try:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                (self._cache_dir / icon_name).write_bytes(data)
            except OSError:
                log.warning("Could not cache icon %s", icon_name)
            self._pixmaps[icon_name] = pixmap
            self.icon_ready.emit(icon_name)

        # A missing icon is cosmetic: keep the placeholder, log, never pop up an error.
        self._runner.run(lambda: download_icon(icon_name), stored, log.warning)

    def _placeholder(self, size: int) -> QPixmap:
        if size not in self._placeholders:
            pixmap = QPixmap(size, size)
            pixmap.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(SURFACE_ALT))
            painter.setPen(QColor(BORDER))
            painter.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), 3, 3)
            painter.setPen(QColor(TEXT_DIM))
            font = QFont()
            font.setPixelSize(max(size // 2, 8))
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "?")
            painter.end()
            self._placeholders[size] = pixmap
        return self._placeholders[size]
