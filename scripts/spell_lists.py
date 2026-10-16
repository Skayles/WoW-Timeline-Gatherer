"""Build the spell lists of src/wcl_notes/data/spells/ from real logs (developer tool).

    uv run python scripts/spell_lists.py mine  --out build/spell_stats.json
    uv run python scripts/spell_lists.py review --stats build/spell_stats.json
    uv run python scripts/spell_lists.py build --stats build/spell_stats.json

``mine`` takes the top Mythic kills of a few bosses (fightRankings, one kill per guild),
downloads every friendly cast of those fights (one paginated query per fight, cached forever
in the app cache, so re-running costs nothing), and counts the spells of each spec.
Specs still missing afterwards are looked up through their own character rankings.

``review`` prints, per spec, the rarely cast spells (cooldown candidates) to curate.

``build`` keeps, for each spec, the spells listed in scripts/spell_categories.yaml and
writes one YAML per spec. Spell IDs and names always come from WCL, never from memory.
"""

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from wcl_notes.api.client import FOREVER, CacheRule, WclClient
from wcl_notes.api.credentials import load_credentials
from wcl_notes.api.rankings import fetch_catalog, fetch_rankings
from wcl_notes.api.reports import fetch_report, parse_cast_events
from wcl_notes.cache.response_cache import ResponseCache, default_cache_path
from wcl_notes.domain.models import CastKind, Report
from wcl_notes.domain.rankings import RankingQuery
from wcl_notes.services.data_files import spec_file_name
from wcl_notes.services.rankings import default_metric
from wcl_notes.services.report_navigation import resolve_fight

ROOT = Path(__file__).resolve().parent.parent
SPELLS_DIR = ROOT / "src" / "wcl_notes" / "data" / "spells"
CATEGORIES_FILE = ROOT / "scripts" / "spell_categories.yaml"
VENOMOUS_ABYSS = [3470, 3445, 3455, 3497, 3513, 3492, 3420, 3421, 3429, 3379]
CATEGORY_ORDER = ("offensive", "raid_cd", "defensive", "utility", "movement")


@dataclass
class SpellStat:
    name: str
    icon: str | None
    players: int = 0
    casts: int = 0


@dataclass
class SpecStat:
    samples: int = 0
    minutes: float = 0.0
    spells: dict[int, SpellStat] = field(default_factory=dict)


def rate(client: WclClient) -> float:
    data = client.execute("rate_limit", {})
    return float(data["rateLimitData"]["pointsSpentThisHour"])


def fight_casts(client: WclClient, code: str, fight_id: int, start: int, end: int) -> list[Any]:
    events: list[Any] = []
    cursor: float = start
    while True:
        data = client.execute(
            "fight_casts",
            {"code": code, "fightID": fight_id, "startTime": cursor, "endTime": end},
            cache=FOREVER,
        )
        page = data["reportData"]["report"]["events"]
        events.extend(page["data"] or [])
        if page["nextPageTimestamp"] is None:
            return events
        cursor = page["nextPageTimestamp"]


def player_specs(client: WclClient, code: str, fight_id: int) -> dict[int, str]:
    data = client.execute("player_details", {"code": code, "fightID": fight_id}, cache=FOREVER)
    details = data["reportData"]["report"]["playerDetails"]["data"]["playerDetails"]
    specs = {}
    for players in details.values():
        for player in players:
            icon = player.get("icon") or ""
            if "-" in icon:
                specs[int(player["id"])] = icon
    return specs


def add_fight(stats: dict[str, SpecStat], client: WclClient, report: Report, fight_id: int) -> int:
    fight = resolve_fight(report, fight_id)
    specs = player_specs(client, report.code, fight_id)
    raw = fight_casts(client, report.code, fight_id, fight.start_ms, fight.end_ms)
    per_player: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for event in parse_cast_events(raw):
        if event.kind is CastKind.CAST and not event.fake and event.source_id in specs:
            per_player[event.source_id][event.spell_id] += 1
    minutes = fight.duration_ms / 60_000
    for player_id, spells in per_player.items():
        stat = stats.setdefault(specs[player_id], SpecStat())
        stat.samples += 1
        stat.minutes += minutes
        for spell_id, count in spells.items():
            spell = report.spells.get(spell_id)
            entry = stat.spells.setdefault(
                spell_id,
                SpellStat(spell.name if spell else str(spell_id), spell.icon if spell else None),
            )
            entry.players += 1
            entry.casts += count
    return len(per_player)


def mine(args: argparse.Namespace) -> None:
    cache = ResponseCache(default_cache_path())
    client = WclClient(load_credentials(ROOT / ".env"), cache=cache)
    spent_before = rate(client)
    catalog = fetch_catalog(client)
    all_specs = {f"{c.slug}-{s.slug}" for c in catalog.classes for s in c.specs}
    stats: dict[str, SpecStat] = {}
    done: set[tuple[str, int]] = set()
    guilds: set[object] = set()

    def take(code: str, fight_id: int) -> None:
        if (code, fight_id) in done:
            return
        done.add((code, fight_id))
        report = fetch_report(client, code)
        players = add_fight(stats, client, report, fight_id)
        print(f"  {code}#{fight_id}: {players} joueurs, {len(stats)} spés couvertes", flush=True)

    # 1. Top kills of several bosses, one per guild, round-robin over the bosses.
    rankings = {}
    for encounter in args.encounters:
        data = client.execute(
            "fight_rankings",
            {"encounterID": encounter, "difficulty": args.difficulty, "page": 1},
            cache=CacheRule(ttl_s=24 * 3600),
        )
        rankings[encounter] = data["worldData"]["encounter"]["fightRankings"]["rankings"]
    for index in range(50):
        for encounter in args.encounters:
            ranks = rankings[encounter]
            if len(done) >= args.max_fights or index >= len(ranks):
                continue
            ranked = ranks[index]
            guild = (ranked.get("guild") or {}).get("id") or ranked["report"]["code"]
            if guild in guilds:
                continue
            guilds.add(guild)
            take(ranked["report"]["code"], ranked["report"]["fightID"])

    # 2. Specs with too few samples: their own top logs.
    for spec_icon in sorted(all_specs):
        missing = args.samples - (stats[spec_icon].samples if spec_icon in stats else 0)
        if missing <= 0:
            continue
        class_slug, spec_slug = spec_icon.split("-", 1)
        print(f"{spec_icon}: {missing} échantillon(s) manquant(s)", flush=True)
        query = RankingQuery(
            args.encounters[0], args.difficulty, class_slug, spec_slug, default_metric(spec_slug)
        )
        for entry in fetch_rankings(client, query).entries[:missing]:
            take(entry.report_code, entry.fight_id)

    out = {
        icon: {
            "samples": stat.samples,
            "minutes": round(stat.minutes, 2),
            "spells": {
                str(spell_id): {
                    "name": s.name,
                    "icon": s.icon,
                    "players": s.players,
                    "per_min": round(s.casts / stat.minutes, 3),
                }
                for spell_id, s in sorted(stat.spells.items())
            },
        }
        for icon, stat in sorted(stats.items())
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    spent = rate(client) - spent_before
    print(f"{len(done)} fights, {len(out)} spés, points dépensés : {spent:.1f}")


def review(args: argparse.Namespace) -> None:
    """Rare spells first: cooldowns are cast a few times per fight, fillers dozens of times."""
    stats = json.loads(args.stats.read_text(encoding="utf-8"))
    for spec_icon, stat in sorted(stats.items()):
        print(f"\n== {spec_icon} ({stat['samples']} joueurs)")
        spells = [
            (int(i), s)
            for i, s in stat["spells"].items()
            if s["players"] * 3 >= stat["samples"] and s["per_min"] <= args.max_per_min
        ]
        for spell_id, s in sorted(spells, key=lambda item: item[1]["per_min"]):
            share = s["players"] / stat["samples"]
            print(f"  {spell_id:>8}  {s['per_min']:5.2f}/min  {share:4.0%}  {s['name']}")


def build(args: argparse.Namespace) -> None:
    stats = json.loads(args.stats.read_text(encoding="utf-8"))
    curated = yaml.safe_load(CATEGORIES_FILE.read_text(encoding="utf-8"))
    for spec_icon, spec_conf in sorted(curated["specs"].items()):
        class_slug, spec_slug = spec_icon.split("-", 1)
        seen = stats.get(spec_icon, {}).get("spells", {})
        names = {int(i): s["name"] for i, s in seen.items()}
        spells = []
        for category in CATEGORY_ORDER:
            for item in spec_conf.get(category) or []:
                spell_id, default = _parse_item(item)
                if spell_id not in names:
                    # Only spells actually seen for this spec are published.
                    print(f"  {spec_icon}: {spell_id} jamais vu dans les logs, ignoré")
                    continue
                spell: dict[str, object] = {
                    "id": spell_id,
                    "name": names[spell_id],
                    "category": category,
                }
                if default:
                    spell["selected_by_default"] = True
                spells.append(spell)
        samples = stats.get(spec_icon, {}).get("samples", 0)
        header = (
            f"# {spec_icon}: spells worth a raid note. Generated by scripts/spell_lists.py from\n"
            f"# {samples} top Mythic players (IDs and names from WCL). Edit\n"
            "# scripts/spell_categories.yaml, then run the build again.\n"
        )
        body = {"class_name": class_slug, "spec": spec_slug, "spells": spells}
        path = SPELLS_DIR / spec_file_name(class_slug, spec_slug)
        path.write_text(
            header + yaml.safe_dump(body, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
            newline="\n",
        )
    print(f"{len(curated['specs'])} fichiers écrits dans {SPELLS_DIR}")


def _parse_item(item: object) -> tuple[int, bool]:
    """``360194`` or ``360194*`` (the star = selected by default)."""
    text = str(item).strip()
    return int(text.rstrip("*")), text.endswith("*")


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    mine_parser = sub.add_parser("mine", help="compter les sorts des top logs")
    mine_parser.add_argument("--out", type=Path, default=ROOT / "build" / "spell_stats.json")
    mine_parser.add_argument("--difficulty", type=int, default=5)
    mine_parser.add_argument(
        "--encounters",
        type=lambda s: [int(x) for x in s.split(",")],
        default=VENOMOUS_ABYSS[:5],
    )
    mine_parser.add_argument("--max-fights", type=int, default=12)
    mine_parser.add_argument("--samples", type=int, default=3)
    review_parser = sub.add_parser("review", help="lister les sorts rares de chaque spé")
    review_parser.add_argument("--stats", type=Path, default=ROOT / "build" / "spell_stats.json")
    review_parser.add_argument("--max-per-min", type=float, default=1.2)
    build_parser = sub.add_parser("build", help="écrire les YAML des spés")
    build_parser.add_argument("--stats", type=Path, default=ROOT / "build" / "spell_stats.json")
    args = parser.parse_args()
    {"mine": mine, "review": review, "build": build}[args.command](args)


if __name__ == "__main__":
    main()
