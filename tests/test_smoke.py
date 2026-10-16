from wcl_notes import __version__
from wcl_notes.cli import main


def test_version_is_set() -> None:
    assert __version__


def test_cli_runs_without_arguments() -> None:
    assert main([]) == 0
