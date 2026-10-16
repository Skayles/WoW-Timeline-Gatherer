"""Method Raid Tools note: one line per cast, Lorrgs style.

{time:00:01.3} - Kràùck {spell:1236994}
"""

from collections.abc import Iterable

from wcl_notes.domain.models import Cast
from wcl_notes.domain.names import character_name


def format_mrt_time(time_ms: int) -> str:
    """MM:SS.d from the pull, rounded half-up to the tenth. Pre-pull clamps to 00:00.0."""
    tenths = (max(time_ms, 0) + 50) // 100
    minutes, rest = divmod(tenths, 600)
    seconds, tenth = divmod(rest, 10)
    return f"{minutes:02d}:{seconds:02d}.{tenth}"


def export_mrt(casts: Iterable[Cast], player_name: str, *, offset_ms: int = 0) -> str:
    """Build the note; ``offset_ms`` moves every cast earlier to get warned ahead."""
    return export_mrt_entries(((player_name, cast) for cast in casts), offset_ms=offset_ms)


def export_mrt_entries(entries: Iterable[tuple[str, Cast]], *, offset_ms: int = 0) -> str:
    """Several players in one note (raid note), merged in time order."""
    return "\n".join(
        f"{{time:{format_mrt_time(cast.time_ms - offset_ms)}}} - "
        f"{character_name(name)} {{spell:{cast.spell_id}}}"
        for name, cast in sorted(entries, key=lambda entry: entry[1].time_ms)
    )
