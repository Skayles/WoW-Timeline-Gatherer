"""Command-line MVP: report code + fight + player -> MRT or NSRT note in the terminal.

Without --fight it lists the boss fights, without --player the players of the fight,
so the report can be explored step by step.
"""

import argparse
import io
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from wcl_notes import __version__
from wcl_notes.api.client import WclClient
from wcl_notes.api.credentials import load_credentials
from wcl_notes.api.errors import WclError
from wcl_notes.api.reports import fetch_pet_casts, fetch_player_casts, fetch_report
from wcl_notes.cache.response_cache import ResponseCache, default_cache_path
from wcl_notes.domain.models import Actor, Cast, Fight, Report, Track, TrackRef
from wcl_notes.domain.names import character_name
from wcl_notes.domain.spells import SpecSpells
from wcl_notes.exporters.mrt import format_mrt_time
from wcl_notes.labels import difficulty_label, fight_label, format_duration, spec_label
from wcl_notes.services.data_files import load_spec_spells, spec_file_name
from wcl_notes.services.notes import (
    DEFAULT_MERGE_WINDOW_MS,
    NoteAssignment,
    NoteFormat,
    NoteOptions,
    build_note,
)
from wcl_notes.services.report_navigation import (
    NavigationError,
    boss_fights,
    find_player,
    pet_ids,
    players_in_fight,
    resolve_fight,
)
from wcl_notes.services.report_reference import (
    FightSelector,
    InvalidReportReferenceError,
    parse_report_reference,
)
from wcl_notes.services.timeline import build_casts, spell_counts

DEFAULT_PLAYER_NAME = "Kràùck"

ClientFactory = Callable[[argparse.Namespace], WclClient]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wcl_notes.cli",
        description="Génère une note MRT ou NSRT à partir d'un log Warcraft Logs.",
    )
    parser.add_argument("report", help="code du report ou URL Warcraft Logs")
    parser.add_argument("-f", "--fight", type=_fight_arg, help="ID du fight, ou « last »")
    parser.add_argument("-p", "--player", help="nom ou ID du joueur source")
    parser.add_argument(
        "-n",
        "--name",
        default=DEFAULT_PLAYER_NAME,
        help=f"nom à écrire dans la note (défaut : {DEFAULT_PLAYER_NAME})",
    )
    parser.add_argument(
        "-F",
        "--format",
        choices=("mrt", "nsrt"),
        default="mrt",
        help="format de la note (défaut : mrt)",
    )
    parser.add_argument(
        "-s",
        "--spells",
        type=_spell_ids_arg,
        help="IDs des sorts à garder, séparés par des virgules",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="garder tous les casts au lieu des sorts importants de la spé",
    )
    parser.add_argument(
        "--summary", action="store_true", help="lister les sorts castés au lieu de générer la note"
    )
    parser.add_argument(
        "--offset", type=float, default=0.0, help="avancer chaque cast de N secondes"
    )
    parser.add_argument(
        "--dur", type=int, help="NSRT : durée d'affichage en secondes (défaut : réglage NSRT)"
    )
    parser.add_argument(
        "--merge",
        type=float,
        default=DEFAULT_MERGE_WINDOW_MS / 1000,
        help="regrouper un même sort relancé à moins de N secondes (0 = jamais, défaut : 0,5)",
    )
    parser.add_argument("--pets", action="store_true", help="inclure les casts des familiers")
    parser.add_argument("--begincast", action="store_true", help="inclure les débuts d'incantation")
    parser.add_argument(
        "--fake", action="store_true", help="inclure les casts synthétisés par WCL (doublons)"
    )
    parser.add_argument("-o", "--output", type=Path, help="écrire la note dans un fichier UTF-8")
    parser.add_argument(
        "--env-file", type=Path, default=Path(".env"), help="fichier .env (défaut : .env)"
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="ignorer le cache local des réponses WCL"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None, *, client_factory: ClientFactory | None = None) -> int:
    _ensure_utf8_output()
    args = build_parser().parse_args(argv)
    factory = client_factory or _default_client
    try:
        with factory(args) as client:
            code = _run(args, client)
            if client.cache_hits:
                print(
                    f"# {client.cache_hits} réponse(s) lue(s) dans le cache local "
                    "(aucun point API consommé).",
                    file=sys.stderr,
                )
            return code
    except (WclError, InvalidReportReferenceError, NavigationError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1


def _run(args: argparse.Namespace, client: WclClient) -> int:
    ref = parse_report_reference(args.report)
    report = fetch_report(client, ref.code)

    selector: FightSelector | None = args.fight if args.fight is not None else ref.fight
    if selector is None:
        _print_fights(report)
        return 0
    fight = resolve_fight(report, selector)

    players = players_in_fight(report, fight)
    player_query: str | int | None = args.player if args.player is not None else ref.source_id
    if player_query is None:
        _print_players(report, fight, players)
        return 0
    player = find_player(players, player_query)

    events = fetch_player_casts(client, report.code, fight, player.id)
    if args.pets:
        for pet_id in pet_ids(fight, player.id):
            events.extend(fetch_pet_casts(client, report.code, fight, pet_id))
    casts = build_casts(events, fight, include_begincast=args.begincast, include_fake=args.fake)
    spec_spells = load_spec_spells(player.sub_type, player.spec) if player.spec else None

    if args.summary:
        if args.spells:
            casts = tuple(c for c in casts if c.spell_id in args.spells)
        _print_summary(report, player, casts, spec_spells)
        return 0

    casts = _select_casts(casts, args, player, spec_spells)
    print(
        f"# Source : {player.name} ({spec_label(player)}) — {fight_label(fight)} — "
        f"{len(casts)} casts. Adaptez à votre compo et à votre temps de kill.",
        file=sys.stderr,
    )
    track = Track(TrackRef(report.code, fight.id, player.id), player, fight, casts)
    options = NoteOptions(
        format=NoteFormat(args.format),
        offset_ms=round(args.offset * 1000),
        dur=args.dur,
        merge_window_ms=round(args.merge * 1000),
    )
    result = build_note([NoteAssignment(track, casts, args.name)], options)
    for info in result.infos:
        print(f"# {info}", file=sys.stderr)
    for warning in result.warnings:
        print(f"# Attention, {warning}", file=sys.stderr)
    note = result.text

    if args.output:
        args.output.write_text(note + "\n", encoding="utf-8")
        print(f"# Note écrite dans {args.output}", file=sys.stderr)
    else:
        print(note)
    return 0


def _select_casts(
    casts: tuple[Cast, ...],
    args: argparse.Namespace,
    player: Actor,
    spec_spells: SpecSpells | None,
) -> tuple[Cast, ...]:
    if args.spells:
        return tuple(c for c in casts if c.spell_id in args.spells)
    if args.all:
        return casts
    if spec_spells is None:
        wanted = spec_file_name(player.sub_type, player.spec or "?")
        print(
            f"# Pas de liste de sorts pour {spec_label(player)} (data/spells/{wanted}) : "
            "tous les casts sont gardés, filtrez avec --spells.",
            file=sys.stderr,
        )
        return casts
    print(
        f"# Filtre : sorts importants {spec_label(player)} (--all pour tout garder).",
        file=sys.stderr,
    )
    selected = spec_spells.default_ids()
    return tuple(c for c in casts if c.spell_id in selected)


def _default_client(args: argparse.Namespace) -> WclClient:
    cache = None if args.no_cache else ResponseCache(default_cache_path())
    return WclClient(load_credentials(args.env_file), cache=cache)


def _print_fights(report: Report) -> None:
    fights = boss_fights(report)
    print(f"Report {report.code} — {report.title}")
    if not fights:
        print("Aucun fight de boss dans ce report.")
        return
    width = max(len(f.name) for f in fights)
    for fight in fights:
        outcome = "kill" if fight.kill else "wipe"
        line = (
            f"  {fight.id:>4}  {fight.name:<{width}}  {difficulty_label(fight.difficulty):<9} "
            f"{outcome}  {format_duration(fight.duration_ms):>6}"
        )
        if not fight.kill and fight.boss_percentage is not None:
            line += f"  (boss à {fight.boss_percentage:.1f} %)"
        print(line)
    print("→ Relancez avec --fight <id> (ou --fight last).")


def _print_players(report: Report, fight: Fight, players: list[Actor]) -> None:
    print(f"Joueurs du fight #{fight.id} — {fight_label(fight)} :")
    width = max((len(p.name) for p in players), default=0)
    for player in players:
        print(f"  {player.id:>4}  {player.name:<{width}}  {spec_label(player)}")
    print("→ Relancez avec --player <nom ou id>.")


def _print_summary(
    report: Report, player: Actor, casts: Sequence[Cast], spec_spells: SpecSpells | None
) -> None:
    counts = spell_counts(casts)
    first_cast: dict[int, int] = {}
    for cast in casts:
        first_cast.setdefault(cast.spell_id, cast.time_ms)
    selected = spec_spells.default_ids() if spec_spells else frozenset()
    names = {sid: spell.name for sid, spell in report.spells.items()}
    width = max((len(names.get(sid, "?")) for sid in counts), default=0)
    print(f"Sorts castés par {character_name(player.name)} ({len(casts)} casts) :")
    print(f"     {'ID':>8}  {'Sort':<{width}}  {'Casts':>5}  Premier")
    for spell_id, count in counts.most_common():
        name = names.get(spell_id, "?")
        mark = "★" if spell_id in selected else " "
        print(
            f"  {mark}  {spell_id:>8}  {name:<{width}}  {count:>5}  "
            f"{format_mrt_time(first_cast[spell_id])}"
        )
    if selected:
        print("★ = gardé par défaut dans la note.")
    print("→ Choisissez les sorts avec --spells <id>,<id>,… (ou --all pour tout garder)")


def _fight_arg(value: str) -> FightSelector:
    if value.lower() == "last":
        return "last"
    if not value.isdigit():
        raise argparse.ArgumentTypeError(f"fight invalide : {value} (un nombre ou « last »)")
    return int(value)


def _spell_ids_arg(value: str) -> frozenset[int]:
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts or not all(p.isdigit() for p in parts):
        raise argparse.ArgumentTypeError(f"liste de sorts invalide : {value}")
    return frozenset(int(p) for p in parts)


def _ensure_utf8_output() -> None:
    # Character names carry accents and non-Latin scripts; never crash on a cp1252 pipe.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
