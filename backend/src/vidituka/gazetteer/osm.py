"""Extract admin areas, places and streets for North Macedonia from an OSM extract (.osm.pbf).

Pure function of the input file, no database. See docs/adr/0004-gazetteer.md.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final

import osmium
import shapely
from shapely import wkb
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge
from shapely.prepared import PreparedGeometry, prep
from shapely.strtree import STRtree

from vidituka.gazetteer.names import name_key, split_names

COUNTRY_CODE: Final = "MK"
AREA_LEVELS: Final = frozenset({2, 6, 7, 8, 9})
PLACE_KINDS: Final = frozenset(
    {"city", "town", "village", "hamlet", "suburb", "neighbourhood", "quarter", "isolated_dwelling"}
)
# footways, tracks etc. are not addresses
STREET_TYPES: Final = frozenset(
    {
        "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
        "living_street", "pedestrian", "service", "road",
        "primary_link", "secondary_link", "tertiary_link",
    }
)  # fmt: skip
ALT_NAME_TAGS: Final = ("name:mk", "old_name", "alt_name", "official_name", "short_name")


@dataclass
class AreaRecord:
    osm_id: int
    level: int
    name: str
    alt_names: list[str]
    geom: MultiPolygon
    municipality_osm_id: int | None = None


@dataclass
class PlaceRecord:
    osm_id: int
    kind: str
    name: str
    alt_names: list[str]
    geom: Point
    municipality_osm_id: int | None = None


@dataclass
class StreetRecord:
    name: str
    alt_names: list[str]
    way_ids: list[int]
    geom: MultiLineString
    municipality_osm_id: int
    settlement_osm_id: int | None


@dataclass
class Extract:
    data_timestamp: datetime | None
    areas: list[AreaRecord] = field(default_factory=list)
    places: list[PlaceRecord] = field(default_factory=list)
    streets: list[StreetRecord] = field(default_factory=list)


@dataclass
class _RawWay:
    osm_id: int
    name: str
    alt_names: list[str]
    line: LineString


class _Collector(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.wkb = osmium.geom.WKBFactory()
        self.areas: list[AreaRecord] = []
        self.places: list[PlaceRecord] = []
        self.ways: list[_RawWay] = []
        self.country: MultiPolygon | None = None

    def area(self, a: osmium.osm.Area) -> None:
        tags = a.tags
        if tags.get("boundary") != "administrative" or "name" not in tags:
            return
        try:
            level = int(tags.get("admin_level") or "")
        except ValueError:
            return
        if level not in AREA_LEVELS:
            return
        try:
            geom = _as_multipolygon(wkb.loads(self.wkb.create_multipolygon(a), hex=True))
        except (RuntimeError, shapely.errors.GEOSException):
            return  # broken boundary in OSM; skip rather than fail the whole load
        osm_id = a.orig_id()
        if level == 2:
            if tags.get("ISO3166-1") == COUNTRY_CODE:
                self.country = geom
            return
        self.areas.append(AreaRecord(osm_id, level, tags["name"], _alt_names(tags), geom))

    def node(self, n: osmium.osm.Node) -> None:
        kind = n.tags.get("place")
        if kind in PLACE_KINDS and "name" in n.tags and n.location.valid():
            point = Point(n.location.lon, n.location.lat)
            self.places.append(PlaceRecord(n.id, kind, n.tags["name"], _alt_names(n.tags), point))

    def way(self, w: osmium.osm.Way) -> None:
        if w.tags.get("highway") not in STREET_TYPES or "name" not in w.tags:
            return
        try:
            line = wkb.loads(self.wkb.create_linestring(w), hex=True)
        except RuntimeError:
            return  # way with missing nodes at the edge of the extract
        if not isinstance(line, LineString):
            return
        self.ways.append(_RawWay(w.id, w.tags["name"], _alt_names(w.tags), line))


def extract(path: Path) -> Extract:
    collector = _Collector()
    collector.apply_file(str(path), locations=True)
    if collector.country is None:
        raise ValueError(f"no boundary with ISO3166-1={COUNTRY_CODE} in {path}")

    country = prep(collector.country)
    result = Extract(data_timestamp=_data_timestamp(path))
    result.areas = [a for a in collector.areas if country.contains(a.geom.representative_point())]
    result.places = [p for p in collector.places if country.contains(p.geom)]

    municipalities = _Index([a for a in result.areas if a.level == 7])
    settlements = _Index([a for a in result.areas if a.level == 8])
    for area in result.areas:
        if area.level in (8, 9):
            area.municipality_osm_id = municipalities.find(area.geom.representative_point())
    for place in result.places:
        place.municipality_osm_id = municipalities.find(place.geom)

    result.streets = _merge_streets(collector.ways, country, municipalities, settlements)
    return result


def _merge_streets(
    ways: list[_RawWay],
    country: PreparedGeometry[MultiPolygon],
    municipalities: _Index,
    settlements: _Index,
) -> list[StreetRecord]:
    # same name in the same settlement is one street, even when OSM splits it into many ways
    groups: dict[tuple[int, int | None, str], list[_RawWay]] = defaultdict(list)
    for way in ways:
        middle = way.line.interpolate(0.5, normalized=True)
        if not country.contains(middle):
            continue
        municipality = municipalities.find(middle)
        if municipality is None:
            continue
        groups[(municipality, settlements.find(middle), name_key(way.name))].append(way)

    streets = []
    for (municipality, settlement, _), group in groups.items():
        names = [w.name for w in group]
        name = max(set(names), key=names.count)
        alt = sorted({n for w in group for n in (*w.alt_names, w.name)} - {name})
        merged = linemerge([w.line for w in group])
        streets.append(
            StreetRecord(
                name=name,
                alt_names=alt,
                way_ids=sorted(w.osm_id for w in group),
                geom=_as_multilinestring(merged),
                municipality_osm_id=municipality,
                settlement_osm_id=settlement,
            )
        )
    return streets


class _Index:
    """Which area contains a point, with a spatial index so 17k lookups stay fast."""

    def __init__(self, areas: list[AreaRecord]) -> None:
        self._areas = areas
        self._tree = STRtree([a.geom for a in areas])

    def find(self, point: BaseGeometry) -> int | None:
        for i in self._tree.query(point, predicate="within"):
            return self._areas[int(i)].osm_id
        return None


def _alt_names(tags: osmium.osm.TagList) -> list[str]:
    main = tags.get("name")
    names = [n for key in ALT_NAME_TAGS for n in split_names(tags.get(key))]
    return sorted({n for n in names if n != main})


def _as_multipolygon(geom: BaseGeometry) -> MultiPolygon:
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    if isinstance(geom, MultiPolygon):
        return geom
    polygons = [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]
    return MultiPolygon(polygons)


def _as_multilinestring(geom: BaseGeometry) -> MultiLineString:
    if isinstance(geom, LineString):
        return MultiLineString([geom])
    if isinstance(geom, MultiLineString):
        return geom
    raise TypeError(f"unexpected street geometry {geom.geom_type}")


def _data_timestamp(path: Path) -> datetime | None:
    value = osmium.io.Reader(str(path)).header().get("osmosis_replication_timestamp")
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
