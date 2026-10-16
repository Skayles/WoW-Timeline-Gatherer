"""Turn raw WCL cast events into pull-relative casts on a track."""

from collections import Counter
from collections.abc import Iterable

from wcl_notes.domain.models import Cast, CastEvent, CastKind, Fight


def build_casts(
    events: Iterable[CastEvent],
    fight: Fight,
    *,
    include_begincast: bool = False,
    include_fake: bool = False,
) -> tuple[Cast, ...]:
    casts = [
        Cast(
            time_ms=event.timestamp - fight.start_ms,
            spell_id=event.spell_id,
            source_id=event.source_id,
            kind=event.kind,
        )
        for event in events
        if (include_begincast or event.kind is CastKind.CAST) and (include_fake or not event.fake)
    ]
    casts.sort(key=lambda c: (c.time_ms, c.source_id, c.spell_id))
    return tuple(casts)


def merge_close_casts(casts: Iterable[Cast], window_ms: int) -> list[Cast]:
    """Keep one cast when the same spell is cast again within ``window_ms``.

    WCL sometimes logs a spell twice at once (one cast on two targets, charges used back
    to back): one reminder is enough. ``window_ms <= 0`` keeps everything.
    """
    ordered = sorted(casts, key=lambda c: c.time_ms)
    if window_ms <= 0:
        return ordered
    last_kept: dict[tuple[int, int], int] = {}
    kept = []
    for cast in ordered:
        key = (cast.source_id, cast.spell_id)
        previous = last_kept.get(key)
        if previous is not None and cast.time_ms - previous < window_ms:
            continue
        last_kept[key] = cast.time_ms
        kept.append(cast)
    return kept


def spell_counts(casts: Iterable[Cast]) -> Counter[int]:
    return Counter(cast.spell_id for cast in casts)
