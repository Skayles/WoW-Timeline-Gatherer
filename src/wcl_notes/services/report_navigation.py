"""Find fights and players inside a loaded report."""

from wcl_notes.domain.models import Actor, Difficulty, Fight, Report
from wcl_notes.i18n import tr
from wcl_notes.services.report_reference import FightSelector

_RAID_DIFFICULTIES = frozenset(d.value for d in Difficulty)


class NavigationError(LookupError):
    """A fight or player could not be found. Message is user-facing."""


def boss_fights(report: Report, *, kills_only: bool = False) -> list[Fight]:
    """Raid boss pulls; trash and Mythic+ runs logged in the same report are left out."""
    return [
        f
        for f in report.fights
        if f.is_boss and f.difficulty in _RAID_DIFFICULTIES and (f.kill or not kills_only)
    ]


def resolve_fight(report: Report, selector: FightSelector) -> Fight:
    if not report.fights:
        raise NavigationError(
            tr("Le report {code} ne contient aucun fight.").format(code=report.code)
        )
    if selector == "last":
        return max(report.fights, key=lambda f: f.id)
    for fight in report.fights:
        if fight.id == selector:
            return fight
    raise NavigationError(
        tr("Fight #{fight} introuvable dans le report {code}.").format(
            fight=selector, code=report.code
        )
    )


def players_in_fight(report: Report, fight: Fight) -> list[Actor]:
    """Players actually present in the fight, not every player of the report."""
    players = [
        actor
        for actor_id in fight.player_ids
        if (actor := report.actors.get(actor_id)) is not None and actor.is_player
    ]
    return sorted(players, key=lambda a: a.name.casefold())


def find_player(players: list[Actor], query: str | int) -> Actor:
    """Match by actor ID, then by exact name (accents kept), then case-insensitively."""
    if isinstance(query, int) or query.strip().isdigit():
        actor_id = int(query)
        for actor in players:
            if actor.id == actor_id:
                return actor
        raise NavigationError(tr("Aucun joueur avec l'ID {id} dans ce fight.").format(id=actor_id))

    name = query.strip()
    for actor in players:
        if actor.name == name:
            return actor
    matches = [a for a in players if a.name.casefold() == name.casefold()]
    if len(matches) == 1:
        return matches[0]
    raise NavigationError(tr("Joueur « {name} » introuvable dans ce fight.").format(name=name))


def pet_ids(fight: Fight, owner_id: int) -> list[int]:
    return [pet.id for pet in fight.pets if pet.owner_id == owner_id]
