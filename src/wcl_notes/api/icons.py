"""Spell icons from the WCL CDN (file names come from ``masterData.abilities.icon``)."""

import re

import httpx

from wcl_notes.api.errors import WclNetworkError

ICON_CDN = "https://assets.rpglogs.com/img/warcraft/abilities/"
_SAFE_ICON = re.compile(r"^[A-Za-z0-9_.-]+$")


def is_safe_icon_name(name: str) -> bool:
    return bool(_SAFE_ICON.match(name)) and ".." not in name


def download_icon(name: str, *, timeout: float = 15.0) -> bytes:
    if not is_safe_icon_name(name):
        raise ValueError(f"Nom d'icône invalide : {name!r}")
    try:
        response = httpx.get(ICON_CDN + name, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise WclNetworkError(f"Icône {name} indisponible : {exc}") from exc
    if response.status_code != 200:
        raise WclNetworkError(f"Icône {name} indisponible (HTTP {response.status_code}).")
    return response.content
