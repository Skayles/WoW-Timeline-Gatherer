# WoW Timeline Gatherer

Application desktop qui récupère sur Warcraft Logs les casts de joueurs sur un boss, les affiche
sur une timeline façon [Lorrgs](https://lorrgs.io) et génère une note prête à copier pour
**Method Raid Tools (MRT)** ou **Northern Sky Raid Tools (NSRT)**.

> Projet en cours de développement — voir la feuille de route dans [CLAUDE.md](CLAUDE.md).

## Installation (développement)

Prérequis : [uv](https://docs.astral.sh/uv/).

```bash
uv sync                          # installer les dépendances
uv run python -m wcl_notes       # lancer l'application
uv run python -m wcl_notes.cli   # CLI (sans interface)
```

Identifiants API : créer un client sur https://www.warcraftlogs.com/api/clients/ puis renseigner
`WCL_CLIENT_ID` et `WCL_CLIENT_SECRET` dans un fichier `.env` (jamais commité).

## CLI

Exploration pas à pas : sans `--fight`, la commande liste les fights de boss ; sans `--player`,
les joueurs du fight.

```bash
uv run python -m wcl_notes.cli <code-ou-URL>                     # fights de boss
uv run python -m wcl_notes.cli <code> -f 7                       # joueurs du fight 7
uv run python -m wcl_notes.cli <code> -f 7 -p Joueur --summary   # sorts castés + IDs
uv run python -m wcl_notes.cli <code> -f 7 -p Joueur -s 360194,385627,1856   # note MRT
```

Une URL avec `#fight=7&source=126` pré-remplit le fight et le joueur. Options utiles :
`-n` (nom écrit dans la note, « Kràùck » par défaut), `--offset 2` (prévenir 2 s avant),
`--pets`, `-o note.txt` (fichier UTF-8, recommandé sous PowerShell).

## Qualité

```bash
uv run pytest
uv run ruff check . && uv run ruff format .
uv run mypy src
```
