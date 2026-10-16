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

## Interface

`uv run python -m wcl_notes` ouvre la fenêtre principale :

- **Log** : collez une URL ou un code de report, choisissez un fight (kills par défaut, wipes
  accessibles), puis cochez les joueurs, groupés par rôle. « Cocher ma spé » et « Me cocher »
  utilisent les réglages. Une URL avec `#fight=…&source=…` pré-sélectionne le fight et le joueur.
- **Pistes** : visibilité, couleur, lien vers WCL et retrait de chaque piste. Une timeline = un boss.
- **Timeline** : molette = défiler, Ctrl+molette = zoomer, clic sur un cast = le désactiver.
  Les bandes orange sont les intermissions WCL, les pointillés bleus les changements de phase NSRT.
- **Sorts** (à droite) : décocher un sort le retire de la timeline et de la note ;
  « Tous les casts » liste aussi les sorts de rotation.
- **Copier la note** (Ctrl+Maj+C) : MRT ou NSRT, Player Name, décalage, durée NSRT,
  note de raid (un nom par piste), aperçu en direct et bouton Copier.
- **Réglages** : nom du joueur, spé, identifiants API (enregistrés dans le gestionnaire
  d'identifiants Windows).

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
`-n` (nom écrit dans la note, « Kràùck » par défaut), `-F nsrt` (note Northern Sky Raid Tools,
temps relatifs à la phase), `--dur 5` (NSRT), `--offset 2` (prévenir 2 s avant), `--pets`,
`-o note.txt` (fichier UTF-8, recommandé sous PowerShell).

Sans `--spells`, la note garde les sorts importants de la spé définis dans
`src/wcl_notes/data/spells/` (plus potions et bijoux de `_common.yaml`) ; `--all` garde tout.
Les phases NSRT de chaque boss sont décrites dans `src/wcl_notes/data/encounters/`.

## Qualité

```bash
uv run pytest
uv run ruff check . && uv run ruff format .
uv run mypy src
```
