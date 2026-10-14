from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from geoalchemy2.shape import from_shape
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from vidituka.gazetteer.names import name_key
from vidituka.gazetteer.osm import Extract
from vidituka.models import AdminArea, GazetteerLoad, Place, Street

SRID = 4326


@dataclass(frozen=True)
class LoadStats:
    areas: int
    places: int
    streets: int


def replace_gazetteer(session: Session, data: Extract, source: str) -> LoadStats:
    """Swap all reference data for `data`. Call inside one transaction so a failed load
    leaves the previous data in place."""
    session.execute(delete(Street))
    session.execute(delete(Place))
    session.execute(delete(AdminArea).where(AdminArea.municipality_id.is_not(None)))
    session.execute(delete(AdminArea))

    # municipalities first, so settlements can point at them
    ordered = sorted(data.areas, key=lambda a: a.municipality_osm_id is not None)
    ids: dict[int, int] = {}
    for area in ordered:
        ids[area.osm_id] = session.execute(
            insert(AdminArea)
            .values(
                osm_id=area.osm_id,
                level=area.level,
                name=area.name,
                name_key=name_key(area.name),
                alt_names=area.alt_names,
                municipality_id=ids.get(area.municipality_osm_id)
                if area.municipality_osm_id
                else None,
                geom=from_shape(area.geom, srid=SRID),
            )
            .returning(AdminArea.id)
        ).scalar_one()

    if data.places:
        session.execute(
            insert(Place),
            [
                {
                    "osm_id": p.osm_id,
                    "kind": p.kind,
                    "name": p.name,
                    "name_key": name_key(p.name),
                    "alt_names": p.alt_names,
                    "municipality_id": ids.get(p.municipality_osm_id)
                    if p.municipality_osm_id
                    else None,
                    "geom": from_shape(p.geom, srid=SRID),
                }
                for p in data.places
            ],
        )
    if data.streets:
        session.execute(
            insert(Street),
            [
                {
                    "name": s.name,
                    "name_key": name_key(s.name),
                    "alt_names": s.alt_names,
                    "municipality_id": ids[s.municipality_osm_id],
                    "settlement_id": ids.get(s.settlement_osm_id) if s.settlement_osm_id else None,
                    "osm_way_ids": s.way_ids,
                    "geom": from_shape(s.geom, srid=SRID),
                }
                for s in data.streets
            ],
        )

    stats = LoadStats(len(data.areas), len(data.places), len(data.streets))
    session.add(
        GazetteerLoad(
            source=source,
            data_timestamp=data.data_timestamp,
            loaded_at=datetime.now(UTC),
            areas=stats.areas,
            places=stats.places,
            streets=stats.streets,
        )
    )
    return stats


def latest_load(session: Session) -> GazetteerLoad | None:
    return session.scalars(select(GazetteerLoad).order_by(GazetteerLoad.id.desc()).limit(1)).first()
