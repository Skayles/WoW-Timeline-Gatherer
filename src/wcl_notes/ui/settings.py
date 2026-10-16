"""User preferences stored with QSettings (registry on Windows). No secrets here."""

import json

from PySide6.QtCore import QSettings

from wcl_notes.domain.spells import SpellPreset
from wcl_notes.i18n import LANGUAGES
from wcl_notes.services.presets import PresetKey

# Empty until the user fills them in Settings (the app is shared with other raiders).
DEFAULT_PLAYER_NAME = ""
DEFAULT_SPEC = ""
MAX_RECENT_REPORTS = 10


class AppSettings:
    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings if settings is not None else QSettings()

    def _str(self, key: str, default: str) -> str:
        value = self._settings.value(key, default)
        return str(value) if value is not None else default

    @property
    def language(self) -> str:
        """Interface language ("fr" or "en"); empty = the system language."""
        value = self._str("language", "")
        return value if value in LANGUAGES else ""

    @language.setter
    def language(self, value: str) -> None:
        self._settings.setValue("language", value if value in LANGUAGES else "")

    @property
    def player_name(self) -> str:
        return self._str("player_name", DEFAULT_PLAYER_NAME)

    @player_name.setter
    def player_name(self, value: str) -> None:
        self._settings.setValue("player_name", value.strip())

    @property
    def my_spec(self) -> str:
        """WCL icon of my spec, "Class-Spec" (e.g. "Rogue-Assassination")."""
        return self._str("my_spec", DEFAULT_SPEC)

    @my_spec.setter
    def my_spec(self, value: str) -> None:
        self._settings.setValue("my_spec", value.strip())

    @property
    def note_format(self) -> str:
        value = self._str("note_format", "mrt")
        return value if value in ("mrt", "nsrt") else "mrt"

    @note_format.setter
    def note_format(self, value: str) -> None:
        self._settings.setValue("note_format", value)

    @property
    def offset_s(self) -> float:
        try:
            return float(self._str("offset_s", "0"))
        except ValueError:
            return 0.0

    @offset_s.setter
    def offset_s(self, value: float) -> None:
        self._settings.setValue("offset_s", str(value))

    @property
    def nsrt_dur(self) -> int:
        """Display duration written in NSRT notes; 0 = let NSRT use its own setting."""
        try:
            return max(int(self._str("nsrt_dur", "0")), 0)
        except ValueError:
            return 0

    @nsrt_dur.setter
    def nsrt_dur(self, value: int) -> None:
        self._settings.setValue("nsrt_dur", str(value))

    @property
    def merge_s(self) -> float:
        """Same spell cast again within this many seconds: one line in the note."""
        try:
            return max(float(self._str("merge_s", "0.5")), 0.0)
        except ValueError:
            return 0.5

    @merge_s.setter
    def merge_s(self, value: float) -> None:
        self._settings.setValue("merge_s", str(value))

    @property
    def recent_reports(self) -> list[tuple[str, str]]:
        """Most recent first: (report code, title)."""
        try:
            raw = json.loads(self._str("recent_reports", "[]"))
        except json.JSONDecodeError:
            return []
        return [
            (str(item[0]), str(item[1]))
            for item in raw
            if isinstance(item, list) and len(item) == 2
        ]

    # --- spell presets (PresetStore) ------------------------------------------------

    @staticmethod
    def _preset_name(key: PresetKey) -> str:
        return f"presets/{key[0]}/{key[1]}"

    def get_preset(self, key: PresetKey) -> SpellPreset | None:
        raw = self._settings.value(self._preset_name(key))
        if raw is None:
            return None
        try:
            data = json.loads(str(raw))
            return SpellPreset(
                include=frozenset(int(x) for x in data.get("include", [])),
                exclude=frozenset(int(x) for x in data.get("exclude", [])),
            )
        except (ValueError, TypeError, AttributeError):
            return None

    def set_preset(self, key: PresetKey, preset: SpellPreset) -> None:
        value = {"include": sorted(preset.include), "exclude": sorted(preset.exclude)}
        self._settings.setValue(self._preset_name(key), json.dumps(value))

    def delete_preset(self, key: PresetKey) -> None:
        self._settings.remove(self._preset_name(key))

    def add_recent_report(self, code: str, title: str) -> None:
        recent = [(c, t) for c, t in self.recent_reports if c != code]
        recent.insert(0, (code, title))
        self._settings.setValue(
            "recent_reports", json.dumps(recent[:MAX_RECENT_REPORTS], ensure_ascii=False)
        )
