"""User-facing texts in French (source language) or English (locales/en.yaml).

Every text shown to the user goes through ``tr()``. Placeholders use ``str.format`` names,
translated before formatting: ``tr("Fight #{fight} introuvable.").format(fight=7)``.
No Qt here: the CLI, the services and the UI share the same catalog.
"""

import ctypes
import os
import sys
from functools import cache
from importlib import resources

import yaml

LANGUAGES = {"fr": "Français", "en": "English"}
SOURCE_LANGUAGE = "fr"
_FRENCH_LANGID = 0x0C  # primary language of a Windows LANGID

_current = SOURCE_LANGUAGE


def system_language() -> str:
    """French on a French system, English everywhere else."""
    if sys.platform == "win32":
        try:
            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        except (AttributeError, OSError):
            langid = 0
        if langid:
            return "fr" if langid & 0x3FF == _FRENCH_LANGID else "en"
    env = (os.environ.get("LC_ALL") or os.environ.get("LANG") or "").lower()
    return "fr" if env.startswith("fr") else "en"


def set_language(language: str) -> None:
    global _current
    _current = language if language in LANGUAGES else SOURCE_LANGUAGE


def get_language() -> str:
    return _current


@cache
def catalog(language: str) -> dict[str, str]:
    if language == SOURCE_LANGUAGE:
        return {}
    text = resources.files("wcl_notes").joinpath("locales", f"{language}.yaml").read_text("utf-8")
    data = yaml.safe_load(text) or {}
    return {str(k): str(v) for k, v in data.items()}


def tr(text: str) -> str:
    """Translate a French source text; unknown texts are returned unchanged."""
    if _current == SOURCE_LANGUAGE:
        return text
    return catalog(_current).get(text, text)
