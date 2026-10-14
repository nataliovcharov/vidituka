"""Works out where each outage is: parse its text, match the names, store the geometry."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from geoalchemy2 import WKBElement
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from vidituka.gazetteer.store import latest_load
from vidituka.geocoding.context import PlaceContext, resolve_place
from vidituka.geocoding.index import SETTLEMENT_PLACES, Entry, Index, load_index
from vidituka.geocoding.matching import match_location
from vidituka.geocoding.names import query_key
from vidituka.ingest import utc_now
from vidituka.models import AdminArea, Outage, OutageLocation, Place, Street
from vidituka.parsing.locations import parse_locations
from vidituka.parsing.models import HouseNumber, Location

log = logging.getLogger(__name__)

# raise when the parser or matcher changes, so `vidituka locate` redoes stored outages
LOCATOR_VERSION = 1

_MODELS: dict[str, type[AdminArea] | type[Place] | type[Street]] = {
    "admin_areas": AdminArea,
    "places": Place,
    "streets": Street,
}


@dataclass
class LocateStats:
    outages: int = 0
    locations: int = 0
    matched: int = 0
    approximate: int = 0
    unplaced: int = 0


def locate_pending(
    session_factory: sessionmaker[Session],
    now: Callable[[], datetime] = utc_now,
    redo_all: bool = False,
) -> LocateStats:
    """Locate outages that were never located, were located by older rules, or before the
    current gazetteer was loaded."""
    with session_factory.begin() as session:
        load = latest_load(session)
        if load is None:
            log.warning("no gazetteer loaded, run `vidituka load-osm` first; skipping")
            return LocateStats()
        index = load_index(session)

        query = select(Outage).order_by(Outage.id)
        if not redo_all:
            query = query.where(
                or_(
                    Outage.locator_version.is_distinct_from(LOCATOR_VERSION),
                    Outage.located_at < load.loaded_at,
                )
            )
        stats = LocateStats()
        for outage in session.scalars(query):
            locate_outage(session, index, outage, now(), stats)
        return stats


def locate_outage(
    session: Session,
    index: Index,
    outage: Outage,
    now: datetime,
    stats: LocateStats | None = None,
) -> list[OutageLocation]:
    stats = stats if stats is not None else LocateStats()
    session.execute(delete(OutageLocation).where(OutageLocation.outage_id == outage.id))

    context = resolve_place(index, outage.place)
    rows = []
    for position, location in enumerate(parse_locations(outage.location_text, outage.place)):
        row = _locate_one(index, context, location, session)
        row.outage_id = outage.id
        row.position = position
        rows.append(row)

        stats.locations += 1
        if row.matched_name is not None:
            stats.matched += 1
        elif row.geom is not None:
            stats.approximate += 1
        else:
            stats.unplaced += 1

    session.add_all(rows)
    outage.located_at = now
    outage.locator_version = LOCATOR_VERSION
    stats.outages += 1
    return rows


def _locate_one(
    index: Index, context: PlaceContext, location: Location, session: Session
) -> OutageLocation:
    row = OutageLocation(
        kind=location.kind,
        name=location.name,
        partial=location.partial,
        numbers=[_number_json(n) for n in location.numbers],
        within=location.in_,
    )
    match = match_location(index, context, location)
    if match is not None:
        row.matched_name = match.name
        row.match_method = match.method
        row.match_widened = match.widened
        row.approximate = False
        row.geom = _geometry(session, match.entries)
        return row

    # not in OSM: show the village or municipality around it, marked as approximate
    area = _fallback_area(index, context, location)
    row.match_widened = False
    row.approximate = True
    row.geom = _geometry(session, (area,)) if area is not None else None
    return row


def _fallback_area(index: Index, context: PlaceContext, location: Location) -> Entry | None:
    if location.kind in ("street", "neighborhood"):
        if location.in_ and context.municipality is not None:
            key = query_key(location.in_)
            for entry in index.by_municipality[context.municipality.id]:
                if key in entry.keys and (
                    entry.kind == "settlement" or entry.kind in SETTLEMENT_PLACES
                ):
                    return entry
        if context.settlement is not None:
            return context.settlement
    return context.municipality


def _geometry(session: Session, entries: tuple[Entry, ...]) -> WKBElement | None:
    # one feature can be several rows (a street through two villages): draw them all,
    # but don't mix a village's boundary with its point
    first = entries[0]
    model = _MODELS[first.table]
    ids = [e.id for e in entries if e.table == first.table]
    geom: WKBElement | None = session.scalar(
        select(func.ST_Union(model.geom)).where(model.id.in_(ids))
    )
    return geom


def _number_json(number: HouseNumber) -> Any:
    if isinstance(number, str):
        return number
    return {"from": number.start, "to": number.end}
