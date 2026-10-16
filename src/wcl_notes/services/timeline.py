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


def spell_counts(casts: Iterable[Cast]) -> Counter[int]:
    return Counter(cast.spell_id for cast in casts)
