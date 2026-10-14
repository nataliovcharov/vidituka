"""Turns the feed's place field into a municipality and settlement.

The power feed writes it as MUNICIPALITY, MUNICIPALITY-SETTLEMENT or
MUNICIPALITY-SETTLEMENT-PART, e.g. "КАРПОШ-СКОПЈЕ-КАРПОШ", "ИЛИНДЕН-КАДИНО" or
"ВРАПЧИШТЕ-СЕНОКОС (ВРАПЧИШТЕ)". Some municipality names contain a dash themselves
("ЧЕШИНОВО - ОБЛЕШЕВО"), so the split is decided by which names exist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vidituka.geocoding.index import SETTLEMENT_PLACES, Entry, Index
from vidituka.geocoding.names import query_key

# the feed's spelling -> the gazetteer's, where they differ by more than punctuation
MUNICIPALITY_ALIASES = {
    "МАВРОВО РОСТУШЕ": "МАВРОВО И РОСТУША",
    "ДЕМИР ХИСАР": "ДЕМИР ХИСАР МУРГАШЕВО",
}
_BRACKETS = re.compile(r"\(.*?\)")


@dataclass(frozen=True)
class PlaceContext:
    municipality: Entry | None
    settlement: Entry | None


def resolve_place(index: Index, place: str) -> PlaceContext:
    parts = [p for p in (_BRACKETS.sub(" ", s).strip() for s in re.split(r"-", place)) if p]
    municipalities = {key: m for m in index.municipalities for key in m.keys}

    # longest run of leading parts that names a municipality
    for size in range(len(parts), 0, -1):
        key = query_key(" ".join(parts[:size]))
        muni = municipalities.get(MUNICIPALITY_ALIASES.get(key, key))
        if muni is None:
            continue
        rest = parts[size:]
        # a municipality alone usually means its seat, e.g. "БИТОЛА"
        settlement_name = rest[0] if rest else " ".join(parts[:size])
        return PlaceContext(muni, _settlement(index, muni, settlement_name))
    return PlaceContext(None, None)


def _settlement(index: Index, muni: Entry, name: str) -> Entry | None:
    key = query_key(name)
    candidates = [e for e in index.by_municipality[muni.id] if key in e.keys]
    # a boundary is more useful than a point, so prefer it when OSM has both
    for wanted in (
        [e for e in candidates if e.kind == "settlement"],
        [e for e in candidates if e.kind in SETTLEMENT_PLACES],
    ):
        if len(wanted) == 1:
            return wanted[0]
    return None
