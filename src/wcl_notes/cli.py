"""Command-line MVP: report code + fight + player -> MRT note in the terminal.

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
from wcl_notes.domain.models import Actor, Cast, Fight, Report
from wcl_notes.domain.names import character_name
from wcl_notes.exporters.mrt import export_mrt, format_mrt_time
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
DIFFICULTY_LABELS = {1: "LFR", 3: "Normal", 4: "Héroïque", 5: "Mythique", 10: "Mythique+"}

ClientFactory = Callable[[argparse.Namespace], WclClient]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wcl_notes.cli",
        description="Génère une note MRT à partir d'un log Warcraft Logs.",
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
        "-s",
        "--spells",
        type=_spell_ids_arg,
        help="IDs des sorts à garder, séparés par des virgules",
    )
    parser.add_argument(
        "--summary", action="store_true", help="lister les sorts castés au lieu de générer la note"
    )
    parser.add_argument(
        "--offset", type=float, default=0.0, help="avancer chaque cast de N secondes"
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
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None, *, client_factory: ClientFactory | None = None) -> int:
    _ensure_utf8_output()
    args = build_parser().parse_args(argv)
    factory = client_factory or _default_client
    try:
        with factory(args) as client:
            return _run(args, client)
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
    if args.spells:
        casts = tuple(c for c in casts if c.spell_id in args.spells)

    if args.summary:
        _print_summary(report, player, casts)
        return 0

    note = export_mrt(casts, args.name, offset_ms=round(args.offset * 1000))
    print(
        f"# Source : {player.name} ({_spec_label(player)}) — {_fight_label(fight)} — "
        f"{len(casts)} casts. Adaptez à votre compo et à votre temps de kill.",
        file=sys.stderr,
    )
    if args.output:
        args.output.write_text(note + "\n", encoding="utf-8")
        print(f"# Note écrite dans {args.output}", file=sys.stderr)
    else:
        print(note)
    return 0


def _default_client(args: argparse.Namespace) -> WclClient:
    return WclClient(load_credentials(args.env_file))


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
            f"  {fight.id:>4}  {fight.name:<{width}}  {_difficulty(fight):<9} "
            f"{outcome}  {_duration(fight.duration_ms):>6}"
        )
        if not fight.kill and fight.boss_percentage is not None:
            line += f"  (boss à {fight.boss_percentage:.1f} %)"
        print(line)
    print("→ Relancez avec --fight <id> (ou --fight last).")


def _print_players(report: Report, fight: Fight, players: list[Actor]) -> None:
    print(f"Joueurs du fight #{fight.id} — {_fight_label(fight)} :")
    width = max((len(p.name) for p in players), default=0)
    for player in players:
        print(f"  {player.id:>4}  {player.name:<{width}}  {_spec_label(player)}")
    print("→ Relancez avec --player <nom ou id>.")


def _print_summary(report: Report, player: Actor, casts: Sequence[Cast]) -> None:
    counts = spell_counts(casts)
    first_cast: dict[int, int] = {}
    for cast in casts:
        first_cast.setdefault(cast.spell_id, cast.time_ms)
    names = {sid: spell.name for sid, spell in report.spells.items()}
    width = max((len(names.get(sid, "?")) for sid in counts), default=0)
    print(f"Sorts castés par {character_name(player.name)} ({len(casts)} casts) :")
    print(f"  {'ID':>8}  {'Sort':<{width}}  {'Casts':>5}  Premier")
    for spell_id, count in counts.most_common():
        name = names.get(spell_id, "?")
        print(
            f"  {spell_id:>8}  {name:<{width}}  {count:>5}  {format_mrt_time(first_cast[spell_id])}"
        )
    print("→ Gardez les sorts voulus avec --spells <id>,<id>,…")


def _fight_label(fight: Fight) -> str:
    outcome = "kill" if fight.kill else "wipe"
    return f"{fight.name} ({_difficulty(fight)}, {outcome}, {_duration(fight.duration_ms)})"


def _spec_label(actor: Actor) -> str:
    return f"{actor.sub_type} {actor.spec}" if actor.spec else actor.sub_type


def _difficulty(fight: Fight) -> str:
    if fight.difficulty is None:
        return "?"
    return DIFFICULTY_LABELS.get(fight.difficulty, str(fight.difficulty))


def _duration(ms: int) -> str:
    minutes, seconds = divmod(round(ms / 1000), 60)
    return f"{minutes}:{seconds:02d}"


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
