# WoW Timeline Gatherer

*[English version](README.md)*

Application Windows qui récupère sur [Warcraft Logs](https://www.warcraftlogs.com) les casts de
joueurs de World of Warcraft, les affiche sur une timeline façon [Lorrgs](https://lorrgs.io) et
génère une note prête à coller pour **Method Raid Tools (MRT)** ou
**Northern Sky Raid Tools (NSRT)**, avec le nom de votre personnage.

- **Top logs** : choisissez un boss, une difficulté et une spé, filtrez les meilleurs kills par
  durée pour trouver des kills proches de celui de votre raid, ajoutez les joueurs à suivre.
- **N'importe quel log** : collez une URL Warcraft Logs, choisissez un fight, cochez des joueurs
  (groupés par rôle).
- **Timeline** : une ligne par joueur, une icône par cast, intermissions WCL et changements de
  phase NSRT. Décochez un sort pour le retirer de la note, cliquez sur un cast pour le désactiver.
- **Notes** : MRT (`{time:01:23.4} - Nom {spell:ID}`) ou NSRT avec des temps relatifs à la phase,
  conversion des phases NSRT boss par boss, décalage, durée d'affichage, note de raid avec un nom
  par piste.
- **Listes de sorts pour les 40 spés**, construites à partir des casts d'environ 660 joueurs
  Mythiques de haut niveau ; potions, bijoux du tier et racials inclus. Vos choix sont retenus
  par boss et par spé.
- Interface en français et en anglais ; cache local : un log déjà chargé ne coûte aucun point
  d'API.

## Téléchargement

1. Téléchargez `WoW-Timeline-Gatherer-<version>-windows-x64.zip` depuis la
   [dernière release](https://github.com/Skayles/WoW-Timeline-Gatherer/releases/latest).
2. Décompressez-le où vous voulez et lancez `WoW Timeline Gatherer.exe` (gardez le dossier tel
   quel ; créez un raccourci vers l'exe si besoin). Windows SmartScreen peut afficher un
   avertissement d'éditeur inconnu (l'application n'est pas signée) : *Informations
   complémentaires → Exécuter quand même*.
3. Au premier lancement, renseignez un client API Warcraft Logs :
   - allez sur <https://www.warcraftlogs.com/api/clients/> (connecté) puis *Create Client* ;
   - nom au choix, redirect URL `http://localhost`, *Public Client* décoché ;
   - recopiez le **Client ID** et le **Client Secret** dans les réglages de l'application. Ils
     sont enregistrés dans le gestionnaire d'identifiants Windows et ne sont envoyés qu'à
     Warcraft Logs.

Renseignez aussi le nom de votre personnage et votre spé (ex. `Rogue-Assassination`) dans
*Réglages*, ainsi que la langue de l'interface si vous en voulez une autre que celle du système.

## Utilisation

1. Onglet **Classements** : raid, boss, difficulté, classe et spé → *Rechercher*. Réduisez la
   durée de kill (par ex. de `5:00` à `5:30`) et cochez un ou plusieurs joueurs. Ou onglet
   **Log** : collez l'URL d'un report, choisissez un fight, cochez des joueurs.
2. Dans la liste **Sorts** à droite, gardez les sorts voulus dans la note ; cliquez sur des casts
   de la timeline pour en désactiver certains.
3. **Copier la note** (Ctrl+Maj+C) : MRT ou NSRT, vérifiez le nom, copiez, collez en jeu.
   Adaptez toujours les timings à votre composition et à votre temps de kill.

NSRT numérote les phases à sa façon (parfois 1.5, 1.75…) : l'application convertit les phases
WCL boss par boss et prévient quand une correspondance est approximative
(voir `src/wcl_notes/data/encounters/`).

L'API Warcraft Logs autorise 720 points par heure et par client : charger un report ou un joueur
coûte environ un point ; les classements et les logs déjà chargés viennent du cache local
(`%LOCALAPPDATA%\wcl-notes\cache.sqlite`, taille et bouton *Vider* dans Réglages).

## Ligne de commande

```bash
uv run python -m wcl_notes.cli <code-ou-URL>                      # fights de boss du report
uv run python -m wcl_notes.cli <code> -f 7                        # joueurs du fight 7
uv run python -m wcl_notes.cli <code> -f 7 -p Joueur --summary    # sorts castés et leurs IDs
uv run python -m wcl_notes.cli <code> -f 7 -p Joueur -F nsrt -n MonNom   # note NSRT
```

Options utiles : `-s 360194,385627` (sorts à garder), `--all`, `--offset 2` (2 s plus tôt),
`--dur 5`, `--merge 0.5`, `--pets`, `-o note.txt`, `--no-cache`, `--lang fr|en`.

## Développement

Nécessite [uv](https://docs.astral.sh/uv/) et Python 3.12+.

```bash
uv sync                                   # dépendances
uv run python -m wcl_notes                # l'application
uv run pytest                             # tests (hors ligne, réponses WCL enregistrées)
uv run ruff check . && uv run ruff format . && uv run mypy src tests
uv run pyinstaller wcl_notes.spec --noconfirm   # dist/WoW Timeline Gatherer/
```

En développement, les identifiants API peuvent aussi aller dans un fichier `.env` à la racine
(`WCL_CLIENT_ID=…`, `WCL_CLIENT_SECRET=…` ; jamais commité).

- `src/wcl_notes/domain`, `services`, `exporters` : logique pure (ni Qt ni HTTP), testée.
- `src/wcl_notes/api` : client GraphQL Warcraft Logs ; chaque requête de `api/queries/*.graphql`
  est validée contre le schéma enregistré (`tests/fixtures/wcl_schema.graphql`).
- `src/wcl_notes/ui` : interface PySide6. Les textes passent par `wcl_notes.i18n.tr` (français
  source, anglais dans `src/wcl_notes/locales/en.yaml` ; un test vérifie qu'il ne manque rien).
- Listes de sorts : `uv run python scripts/spell_lists.py mine`, puis `review` et `build`
  (catégories dans `scripts/spell_categories.yaml`). Les IDs viennent toujours de vrais logs.
- Un build se vérifie avec `"WoW Timeline Gatherer.exe" --self-check rapport.json`.

Projet non affilié à Blizzard Entertainment, Warcraft Logs, Lorrgs, MRT ou NSRT.
