"""Icons from the WCL CDN.

Spell icons: file names from ``masterData.abilities.icon`` ("ability_rogue_deathmark.jpg").
Spec icons: actor icon + ".jpg" ("Rogue-Assassination.jpg").
"""

import re
from enum import StrEnum

import httpx

from wcl_notes.api.errors import WclNetworkError


class IconKind(StrEnum):
    ABILITY = "abilities"
    SPEC = "icons"


ICON_CDN = "https://assets.rpglogs.com/img/warcraft/"
_SAFE_ICON = re.compile(r"^[A-Za-z0-9_.-]+$")


def is_safe_icon_name(name: str) -> bool:
    return bool(_SAFE_ICON.match(name)) and ".." not in name


def icon_url(name: str, kind: IconKind = IconKind.ABILITY) -> str:
    return f"{ICON_CDN}{kind.value}/{name}"


def download_icon(name: str, kind: IconKind = IconKind.ABILITY, *, timeout: float = 15.0) -> bytes:
    if not is_safe_icon_name(name):
        raise ValueError(f"Invalid icon name: {name!r}")
    try:
        response = httpx.get(icon_url(name, kind), timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise WclNetworkError(f"Icon {name} unavailable: {exc}") from exc
    if response.status_code != 200:
        raise WclNetworkError(f"Icon {name} unavailable (HTTP {response.status_code}).")
    return response.content
