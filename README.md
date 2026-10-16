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

## Qualité

```bash
uv run pytest
uv run ruff check . && uv run ruff format .
uv run mypy src
```
