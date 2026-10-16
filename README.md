# WoW Timeline Gatherer

*[Version française](README.fr.md)*

A Windows desktop app that pulls the casts of World of Warcraft players from
[Warcraft Logs](https://www.warcraftlogs.com), shows them on a [Lorrgs](https://lorrgs.io)-like
timeline, and builds a ready-to-paste note for **Method Raid Tools (MRT)** or
**Northern Sky Raid Tools (NSRT)** with your own character name.

- **Top logs**: pick a boss, a difficulty and a spec, filter the best kills by kill time to find
  fights close to your raid's, and add the players you want to follow.
- **Any log**: paste a Warcraft Logs URL, pick a fight, tick players (grouped by role).
- **Timeline**: one row per player, one icon per cast, WCL intermissions and NSRT phase changes.
  Untick a spell to drop it from the note, click a cast to disable just that one.
- **Notes**: MRT (`{time:01:23.4} - Name {spell:ID}`) or NSRT with phase-relative times, per-boss
  NSRT phase mapping, offset, display duration, raid notes with one name per track.
- **Spell lists for all 40 specs**, built from the casts of ~660 top Mythic players; potions,
  tier trinkets and racials included. Your choices are remembered per boss and spec.
- English and French interface; local cache, so a log already loaded costs no API point.

## Download

1. Download `WoW-Timeline-Gatherer-<version>-windows-x64.zip` from the
   [latest release](https://github.com/Skayles/WoW-Timeline-Gatherer/releases/latest).
2. Unzip it anywhere and run `WoW Timeline Gatherer.exe` (keep the folder as it is; create a
   shortcut to the exe if you like). Windows SmartScreen may warn about an unknown publisher
   (the app is not code-signed): *More info → Run anyway*.
3. On first launch, enter a Warcraft Logs API client:
   - go to <https://www.warcraftlogs.com/api/clients/> (logged in) and click *Create Client*;
   - any name, redirect URL `http://localhost`, leave *Public Client* unticked;
   - copy the **Client ID** and **Client Secret** into the app's settings. They are stored in
     the Windows Credential Manager, never sent anywhere but Warcraft Logs.

Also set your character name and spec (e.g. `Rogue-Assassination`) in *Settings*, and the
interface language if you want another one than your system's.

## Using it

1. **Rankings** tab: raid, boss, difficulty, class and spec → *Search*. Narrow the kill time
   (e.g. from `5:00` to `5:30`) and tick one or more players. Or **Log** tab: paste a report URL,
   pick a fight, tick players.
2. In the **Spells** list on the right, keep the spells you want in the note; click casts on the
   timeline to disable single ones.
3. **Copy note** (Ctrl+Shift+C): choose MRT or NSRT, check the name, copy, and paste it in game.
   Always adapt the timings to your raid composition and kill time.

NSRT counts boss phases its own way (sometimes 1.5, 1.75…): the app converts WCL phases per
boss and warns when a mapping is approximate (see `src/wcl_notes/data/encounters/`).

The Warcraft Logs API allows 720 points per hour per client: loading a report or a player costs
about one point each, rankings and already loaded logs come from the local cache
(`%LOCALAPPDATA%\wcl-notes\cache.sqlite`, size and *Clear* button in Settings).

## Command line

```bash
uv run python -m wcl_notes.cli <code-or-URL>                      # boss fights of the report
uv run python -m wcl_notes.cli <code> -f 7                        # players of fight 7
uv run python -m wcl_notes.cli <code> -f 7 -p Player --summary    # cast spells and their IDs
uv run python -m wcl_notes.cli <code> -f 7 -p Player -F nsrt -n MyName   # NSRT note
```

Useful options: `-s 360194,385627` (spells to keep), `--all`, `--offset 2` (2 s earlier),
`--dur 5`, `--merge 0.5`, `--pets`, `-o note.txt`, `--no-cache`, `--lang en|fr`.

## Development

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync                                   # dependencies
uv run python -m wcl_notes                # the app
uv run pytest                             # tests (offline, recorded WCL responses)
uv run ruff check . && uv run ruff format . && uv run mypy src tests
uv run pyinstaller wcl_notes.spec --noconfirm   # dist/WoW Timeline Gatherer/
```

For development, API credentials can also go in a `.env` file at the project root
(`WCL_CLIENT_ID=…`, `WCL_CLIENT_SECRET=…`; never committed).

- `src/wcl_notes/domain`, `services`, `exporters`: pure logic (no Qt, no HTTP), fully tested.
- `src/wcl_notes/api`: Warcraft Logs GraphQL client; every query in `api/queries/*.graphql` is
  validated against the recorded schema (`tests/fixtures/wcl_schema.graphql`).
- `src/wcl_notes/ui`: PySide6 interface. Texts go through `wcl_notes.i18n.tr` (French source,
  English in `src/wcl_notes/locales/en.yaml`; a test checks nothing is missing).
- Spell lists: `uv run python scripts/spell_lists.py mine`, then `review` and `build`
  (categories in `scripts/spell_categories.yaml`). Spell IDs always come from real logs.
- A packaged build checks itself with `"WoW Timeline Gatherer.exe" --self-check report.json`.

Not affiliated with Blizzard Entertainment, Warcraft Logs, Lorrgs, MRT or NSRT.
