from pathlib import Path

import keyring
import pytest

from wcl_notes.api.credentials import has_credentials, load_credentials, read_env_file
from wcl_notes.api.errors import MissingCredentialsError


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WCL_CLIENT_ID", raising=False)
    monkeypatch.delenv("WCL_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(keyring, "get_password", lambda service, user: None)


def test_read_env_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        '# comment\nWCL_CLIENT_ID="abc"\nexport WCL_CLIENT_SECRET = xyz\n\nBROKEN\n',
        encoding="utf-8",
    )
    assert read_env_file(env) == {"WCL_CLIENT_ID": "abc", "WCL_CLIENT_SECRET": "xyz"}


def test_environment_wins_over_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("WCL_CLIENT_ID=file\nWCL_CLIENT_SECRET=file\n", encoding="utf-8")
    monkeypatch.setenv("WCL_CLIENT_ID", "env")
    monkeypatch.setenv("WCL_CLIENT_SECRET", "env")
    assert load_credentials(env).client_id == "env"


def test_env_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("WCL_CLIENT_ID=file-id\nWCL_CLIENT_SECRET=file-secret\n", encoding="utf-8")
    loaded = load_credentials(env)
    assert (loaded.client_id, loaded.client_secret) == ("file-id", "file-secret")


def test_keyring_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stored = {"client_id": "kr-id", "client_secret": "kr-secret"}
    monkeypatch.setattr(keyring, "get_password", lambda service, user: stored[user])
    assert load_credentials(tmp_path / "missing.env").client_id == "kr-id"


def test_missing_everywhere(tmp_path: Path) -> None:
    with pytest.raises(MissingCredentialsError):
        load_credentials(tmp_path / "missing.env")


def test_has_credentials(tmp_path: Path) -> None:
    assert not has_credentials(tmp_path / "missing.env")
    env = tmp_path / ".env"
    env.write_text("WCL_CLIENT_ID=a\nWCL_CLIENT_SECRET=b\n", encoding="utf-8")
    assert has_credentials(env)
