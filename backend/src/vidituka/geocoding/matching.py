"""Finds the gazetteer feature a parsed location refers to.

Each location is searched in its outage's municipality first, then in the municipalities
next to it. In each, three methods are tried in order and the first that finds anything
decides:

1. exact: the same key, after the variants in `names.py` (old names included)
2. abbreviation: "МАК КОСОВСКА" -> "Македонско-косовска бригада", "ВС БАТО" ->
   "Видое Смилевски Бато"
3. fuzzy: a small spelling difference, "ГВАДАЛАХАРА" -> "Гвадалахара", "БЕДИЊЕ" -> "Бедиње"

A name that matches two different features equally well is left unmatched rather than
guessed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz

from vidituka.geocoding.context import PlaceContext
from vidituka.geocoding.index import NEIGHBORHOOD_PLACES, SETTLEMENT_PLACES, Entry, Index
from vidituka.geocoding.names import query_key
from vidituka.parsing.models import Location

Method = Literal["exact", "abbreviation", "fuzzy"]
Finder = Callable[[str, Sequence[Entry]], list[tuple[Entry, float]]]

FUZZY_MIN_SCORE = 88.0
# the best fuzzy candidate must beat the next one by this much
FUZZY_MARGIN = 5.0


@dataclass(frozen=True)
class Match:
    # one feature can be several rows, e.g. a street that crosses two villages
    entries: tuple[Entry, ...]
    method: Method
    score: float
    # found outside the outage's own municipality
    widened: bool = False

    @property
    def name(self) -> str:
        return self.entries[0].name


def match_location(index: Index, context: PlaceContext, location: Location) -> Match | None:
    key = query_key(location.name)
    if not key:
        return None
    if location.kind == "municipality":
        return _search(key, [Tier(index.municipalities)], context)

    muni = context.municipality
    if muni is None:
        return None
    local = index.by_municipality[muni.id]
    nearby = [e for other in index.neighbors.get(muni.id, ()) for e in index.by_municipality[other]]

    if location.kind == "street":
        streets = [e for e in local if e.kind == "street"]
        tiers = [Tier(streets), Tier([e for e in nearby if e.kind == "street"], widened=True)]
        if location.in_:
            village = _find_settlement(index, muni, location.in_)
            if village is not None:
                tiers.insert(0, Tier([e for e in streets if e.settlement_id == village.id]))
        return _search(key, tiers, context)

    if location.kind == "settlement":
        return _search(
            key,
            [
                Tier([e for e in local if _is_settlement(e)]),
                Tier([e for e in local if _is_neighborhood(e)]),
                # a different village with the same name is likelier than a typo here
                Tier([e for e in nearby if _is_settlement(e)], widened=True, fuzzy=False),
            ],
            context,
        )

    # neighborhood
    return _search(
        key,
        [
            Tier([e for e in local if _is_neighborhood(e)]),
            Tier([e for e in local if _is_settlement(e)]),
            # some are known by the street they grew around
            Tier([e for e in local if e.kind == "street"], fuzzy=False),
            Tier([e for e in nearby if _is_neighborhood(e)], widened=True, fuzzy=False),
        ],
        context,
    )


@dataclass(frozen=True)
class Tier:
    entries: Sequence[Entry]
    widened: bool = False
    fuzzy: bool = True


def _is_settlement(e: Entry) -> bool:
    return e.kind == "settlement" or e.kind in SETTLEMENT_PLACES


def _is_neighborhood(e: Entry) -> bool:
    return e.kind == "urban_area" or e.kind in NEIGHBORHOOD_PLACES


def _find_settlement(index: Index, muni: Entry, name: str) -> Entry | None:
    key = query_key(name)
    found = [e for e in index.by_municipality[muni.id] if _is_settlement(e) and key in e.keys]
    return found[0] if found else None


def _search(key: str, tiers: Sequence[Tier], context: PlaceContext) -> Match | None:
    for tier in tiers:
        methods: list[tuple[Method, Finder]] = [("exact", _exact), ("abbreviation", _abbreviation)]
        if tier.fuzzy:
            methods.append(("fuzzy", _fuzzy))
        for method, find in methods:
            found = find(key, tier.entries)
            if not found:
                continue
            chosen = _one_feature(found, context)
            if chosen is None:
                # two different places fit equally well: don't guess
                return None
            entries, score = chosen
            return Match(entries, method, score, tier.widened)
    return None


def _exact(key: str, pool: Sequence[Entry]) -> list[tuple[Entry, float]]:
    return [(e, 100.0) for e in pool if key in e.keys]


def _abbreviation(key: str, pool: Sequence[Entry]) -> list[tuple[Entry, float]]:
    words = key.split()
    # either side can be the short one: the feed's "МАК КОСОВСКА" or OSM's "Ј. Османо"
    return [
        (e, 95.0)
        for e in pool
        if any(_abbreviates(words, k.split()) or _abbreviates(k.split(), words) for k in e.keys)
    ]


def _abbreviates(short: list[str], full: list[str]) -> bool:
    """True if each short word is a full word, its start ("МАК"), or the initials of the
    next few words ("ВС"), in order. Full words left over at the end are allowed
    ("МАК КОСОВСКА" -> "МАКЕДОНСКО КОСОВСКА БРИГАДА"), as long as one word is whole and
    something was actually shortened."""
    if short == full or not any(len(w) <= 3 and not w.isdigit() for w in short):
        return False
    i = 0
    whole = 0
    for word in short:
        if i >= len(full):
            return False
        if word == full[i]:
            whole += 1
            i += 1
        elif full[i].startswith(word) and len(full[i]) > len(word):
            i += 1
        elif (
            2 <= len(word) <= 3
            and i + len(word) <= len(full)
            and all(full[i + n].startswith(letter) for n, letter in enumerate(word))
        ):
            i += len(word)
        else:
            return False
    return whole >= 1


def _fuzzy(key: str, pool: Sequence[Entry]) -> list[tuple[Entry, float]]:
    # spelling slips only: same number of words and the same numbers, so
    # "МАКЕДОНСКА БРИГАДА" never becomes "2 МАКЕДОНСКА БРИГАДА"
    shape = _shape(key)
    scored = sorted(
        (
            (e, max(fuzz.ratio(key, k) for k in comparable))
            for e in pool
            if (comparable := [k for k in e.keys if _shape(k) == shape])
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )
    if not scored or scored[0][1] < FUZZY_MIN_SCORE:
        return []
    best = scored[0][1]
    close = [(e, s) for e, s in scored if s > best - FUZZY_MARGIN]
    return close


def _shape(key: str) -> tuple[int, tuple[str, ...]]:
    words = key.split()
    return len(words), tuple(w for w in words if w.isdigit())


def _one_feature(
    found: Iterable[tuple[Entry, float]], context: PlaceContext
) -> tuple[tuple[Entry, ...], float] | None:
    best = max(s for _, s in found)
    top = [e for e, s in found if s == best]
    others = [e for e, s in found if s != best]
    groups: dict[str, list[Entry]] = {}
    for entry in top:
        groups.setdefault(query_key(entry.name), []).append(entry)

    if len(groups) > 1:
        return None
    # close runners-up with a different name make the fuzzy answer unsafe
    if any(query_key(e.name) not in groups for e in others):
        return None

    entries = next(iter(groups.values()))
    if context.settlement is not None:
        # prefer the copy in the outage's own settlement when a name repeats
        preferred = [e for e in entries if e.settlement_id == context.settlement.id]
        entries = preferred or entries
    # boundaries before points
    entries.sort(key=lambda e: (e.table != "admin_areas", e.table != "streets", e.id))
    return tuple(entries), best
