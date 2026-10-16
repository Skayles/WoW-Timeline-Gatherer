import argparse
from pathlib import Path

import pytest

from conftest import REPORT_CODE, FakeWcl, read_golden
from wcl_notes.api.client import WclClient
from wcl_notes.cli import main

URL = f"https://www.warcraftlogs.com/reports/{REPORT_CODE}"


def run(fake_wcl: FakeWcl, *argv: str) -> int:
    def factory(_: argparse.Namespace) -> WclClient:
        return fake_wcl.client()

    return main(list(argv), client_factory=factory)


def test_lists_boss_fights_without_fight(
    fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(fake_wcl, REPORT_CODE) == 0
    out = capsys.readouterr().out
    assert "Nek'zali the Soulcoiler" in out
    assert "Mythique" in out
    assert "--fight" in out


def test_lists_players_of_the_fight(fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(fake_wcl, f"{URL}#fight=7") == 0
    out = capsys.readouterr().out
    assert "Vénéfique" in out
    assert "Rogue Assassination" in out
    assert "Absentéïste" not in out


def test_note_for_selected_spells(fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str]) -> None:
    code = run(fake_wcl, f"{URL}#fight=7&source=126", "--spells", "360194,385627,1856")
    assert code == 0
    captured = capsys.readouterr()
    assert captured.out == read_golden("mrt_rogue_cooldowns.txt")
    assert "Vénéfique" in captured.err


def test_custom_name_and_output_file(fake_wcl: FakeWcl, tmp_path: Path) -> None:
    out = tmp_path / "note.txt"
    code = run(
        fake_wcl, REPORT_CODE, "-f", "7", "-p", "Vénéfique", "-s", "1856", "-n", "Zoë-Hyjal",
        "-o", str(out),
    )  # fmt: skip
    assert code == 0
    assert out.read_text(encoding="utf-8").splitlines()[0] == "{time:00:18.9} - Zoë {spell:1856}"


def test_summary(fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(fake_wcl, REPORT_CODE, "-f", "7", "-p", "126", "--summary") == 0
    out = capsys.readouterr().out
    assert "Deathmark" in out
    assert "338 casts" in out  # 466 minus the 128 fake off-hand Mutilate


def test_pets_option(fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(fake_wcl, REPORT_CODE, "-f", "7", "-p", "117", "--pets", "-s", "117588") == 0
    assert "{spell:117588}" in capsys.readouterr().out  # Meteor, cast by the fire elemental


def test_unknown_player_is_a_clear_error(
    fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(fake_wcl, REPORT_CODE, "-f", "7", "-p", "Personne") == 1
    assert "Erreur : Joueur « Personne » introuvable" in capsys.readouterr().err


def test_invalid_reference(fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(fake_wcl, "https://lorrgs.io/") == 1
    assert "Erreur" in capsys.readouterr().err
