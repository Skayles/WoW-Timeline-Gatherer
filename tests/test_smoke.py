import pytest

from wcl_notes import __version__
from wcl_notes.cli import main


def test_version_is_set() -> None:
    assert __version__


def test_cli_requires_a_report() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
