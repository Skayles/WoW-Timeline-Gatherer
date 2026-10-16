import argparse
from pathlib import Path

import pytest

from conftest import REPORT_CODE, FakeWcl, load_json, read_golden
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
    code = run(
        fake_wcl, f"{URL}#fight=7&source=126", "--spells", "360194,385627,1856", "-n", "Kràùck"
    )
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


def test_nsrt_note(fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str]) -> None:
    args = ("-F", "nsrt", "-s", "360194,385627,1856", "-n", "Kràùck")
    assert run(fake_wcl, f"{URL}#fight=7&source=126", *args) == 0
    captured = capsys.readouterr()
    assert captured.out == read_golden("nsrt_rogue_nekzali.txt")
    assert "Phases NSRT : 1 à 00:00.0, 1.5 à 02:19.4, 2 à 03:50.8" in captured.err
    assert "approximatives" in captured.err


def test_nsrt_dur(fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(fake_wcl, REPORT_CODE, "-f", "7", "-p", "126", "-F", "nsrt", "--dur", "5") == 0
    lines = capsys.readouterr().out.splitlines()
    assert all(line.endswith(";dur:5") for line in lines[1:])


def test_default_filter_uses_spec_spells(
    fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(fake_wcl, REPORT_CODE, "-f", "7", "-p", "126") == 0
    captured = capsys.readouterr()
    spells = {line.rsplit("{spell:", 1)[1].rstrip("}") for line in captured.out.splitlines()}
    assert spells == {"360194", "385627", "1856", "1297761"}  # + Voracious Heart trinket
    assert "sorts importants Rogue Assassination" in captured.err


def test_all_keeps_every_cast(fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(fake_wcl, REPORT_CODE, "-f", "7", "-p", "126", "--all", "--merge", "0") == 0
    assert len(capsys.readouterr().out.splitlines()) == 338


def test_spec_without_spell_file_keeps_everything(
    fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("wcl_notes.cli.load_spec_spells", lambda class_name, spec: None)
    pages = load_json("casts_cmw7_f7_s118_pages.json")
    cast_events = [
        e
        for page in pages
        for e in page["data"]["reportData"]["report"]["events"]["data"]
        if e["type"] == "cast"
    ]
    assert run(fake_wcl, REPORT_CODE, "-f", "7", "-p", "118") == 0
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == len(cast_events)
    assert "mage_frost.yaml" in captured.err


def test_summary_marks_default_spells(
    fake_wcl: FakeWcl, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(fake_wcl, REPORT_CODE, "-f", "7", "-p", "126", "--summary") == 0
    deathmark = next(line for line in capsys.readouterr().out.splitlines() if "Deathmark" in line)
    assert "★" in deathmark
