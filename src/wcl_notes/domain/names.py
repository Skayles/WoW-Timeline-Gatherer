"""Character name helpers. Accents are never stripped or normalised."""


def character_name(name: str) -> str:
    """Drop the realm from "Name-Realm"; WoW character names cannot contain "-"."""
    return name.strip().split("-", 1)[0]
