"""Dark theme (Lorrgs-like) and WoW class colors."""

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# Official class colors, keyed by WCL actor subType.
CLASS_COLORS = {
    "DeathKnight": "#C41E3A",
    "DemonHunter": "#A330C9",
    "Druid": "#FF7C0A",
    "Evoker": "#33937F",
    "Hunter": "#AAD372",
    "Mage": "#3FC7EB",
    "Monk": "#00FF98",
    "Paladin": "#F48CBA",
    "Priest": "#FFFFFF",
    "Rogue": "#FFF468",
    "Shaman": "#0070DD",
    "Warlock": "#8788EE",
    "Warrior": "#C69B6D",
}

BACKGROUND = "#1b1d23"
SURFACE = "#24272f"
SURFACE_ALT = "#2b2f38"
BORDER = "#3a3f4b"
TEXT = "#e6e6e6"
TEXT_DIM = "#9aa0aa"
ACCENT = "#4FC3F7"
WARNING = "#FFB74D"
ERROR = "#E57373"


def class_color(sub_type: str) -> QColor:
    return QColor(CLASS_COLORS.get(sub_type, TEXT_DIM))


def monospace_font(point_size: int = 10) -> QFont:
    font = QFont("Consolas")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(point_size)
    return font


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: BACKGROUND,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: SURFACE,
        QPalette.ColorRole.AlternateBase: SURFACE_ALT,
        QPalette.ColorRole.ToolTipBase: SURFACE_ALT,
        QPalette.ColorRole.ToolTipText: TEXT,
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: SURFACE_ALT,
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.BrightText: ERROR,
        QPalette.ColorRole.Highlight: "#2f6f8f",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.Link: ACCENT,
        QPalette.ColorRole.PlaceholderText: TEXT_DIM,
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(TEXT_DIM))
    app.setPalette(palette)
    app.setStyleSheet(
        f"QToolTip {{ color: {TEXT}; background: {SURFACE_ALT}; border: 1px solid {BORDER}; }}"
        f"QSplitter::handle {{ background: {BORDER}; }}"
    )
