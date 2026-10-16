"""WCL client credentials: environment, then ``.env`` (dev only), then the OS keyring."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import keyring
from keyring.errors import KeyringError

from wcl_notes.api.errors import MissingCredentialsError

ENV_CLIENT_ID = "WCL_CLIENT_ID"
ENV_CLIENT_SECRET = "WCL_CLIENT_SECRET"
KEYRING_SERVICE = "wcl-notes"
_KEYRING_ID_USER = "client_id"
_KEYRING_SECRET_USER = "client_secret"


@dataclass(frozen=True, slots=True)
class Credentials:
    client_id: str
    client_secret: str = field(repr=False)


def read_env_file(path: Path) -> dict[str, str]:
    """Minimal ``KEY=value`` parser; quotes around values are dropped."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.removeprefix("export ").strip()] = value.strip().strip("\"'")
    return values


def load_credentials(env_file: Path | None = Path(".env")) -> Credentials:
    sources: list[dict[str, str]] = [dict(os.environ)]
    if env_file is not None and env_file.is_file():
        sources.append(read_env_file(env_file))
    for values in sources:
        client_id = values.get(ENV_CLIENT_ID, "").strip()
        client_secret = values.get(ENV_CLIENT_SECRET, "").strip()
        if client_id and client_secret:
            return Credentials(client_id, client_secret)

    stored_id: str | None = None
    stored_secret: str | None = None
    try:
        stored_id = keyring.get_password(KEYRING_SERVICE, _KEYRING_ID_USER)
        stored_secret = keyring.get_password(KEYRING_SERVICE, _KEYRING_SECRET_USER)
    except KeyringError:
        pass
    if stored_id and stored_secret:
        return Credentials(stored_id, stored_secret)

    raise MissingCredentialsError(
        "Identifiants Warcraft Logs introuvables : renseignez-les dans Réglages "
        "(ou WCL_CLIENT_ID et WCL_CLIENT_SECRET dans un fichier .env)."
    )


def has_credentials(env_file: Path | None = Path(".env")) -> bool:
    try:
        load_credentials(env_file)
    except MissingCredentialsError:
        return False
    return True


def store_credentials(credentials: Credentials) -> None:
    keyring.set_password(KEYRING_SERVICE, _KEYRING_ID_USER, credentials.client_id)
    keyring.set_password(KEYRING_SERVICE, _KEYRING_SECRET_USER, credentials.client_secret)
