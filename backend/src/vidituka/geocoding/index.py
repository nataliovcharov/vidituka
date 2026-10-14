"""In-memory copy of the gazetteer names, for matching without a query per location."""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from vidituka.geocoding.names import match_keys
from vidituka.models import AdminArea, Place, Street

Table = Literal["admin_areas", "places", "streets"]

# names from the OSM extract the labels were checked against, for tests and eval-matcher
DEFAULT_SNAPSHOT = (
    Path(__file__).resolve().parents[3] / "tests/fixtures/osm/gazetteer_snapshot.json.gz"
)

MUNICIPALITY_LEVEL = 7
SETTLEMENT_LEVEL = 8
URBAN_AREA_LEVEL = 9
SETTLEMENT_PLACES = frozenset({"city", "town", "village", "hamlet", "isolated_dwelling"})
NEIGHBORHOOD_PLACES = frozenset({"suburb", "neighbourhood", "quarter"})


@dataclass(frozen=True)
class Entry:
    table: Table
    id: int
    name: str
    kind: str  # "municipality", "settlement", "urban_area", a place kind, or "street"
    municipality_id: int | None
    settlement_id: int | None = None
    keys: frozenset[str] = frozenset()


@dataclass
class Index:
    entries: dict[tuple[Table, int], Entry] = field(default_factory=dict)
    # municipality id -> entries inside it
    by_municipality: dict[int | None, list[Entry]] = field(
        default_factory=lambda: defaultdict(list)
    )
    municipalities: list[Entry] = field(default_factory=list)
    # municipalities that share a border. The feed's municipality is the power company's
    # area, and a village or street it lists is sometimes just across the line.
    neighbors: dict[int, frozenset[int]] = field(default_factory=dict)

    def add(self, entry: Entry) -> None:
        self.entries[(entry.table, entry.id)] = entry
        if entry.kind == "municipality":
            self.municipalities.append(entry)
        else:
            self.by_municipality[entry.municipality_id].append(entry)

    def municipality_name(self, entry: Entry) -> str | None:
        if entry.kind == "municipality":
            return entry.name
        muni = self.entries.get(("admin_areas", entry.municipality_id or -1))
        return muni.name if muni else None


AreaRow = tuple[int, int, str, list[str], int | None]  # id, level, name, alt names, municipality
PlaceRow = tuple[int, str, str, list[str], int | None]  # id, kind, name, alt names, municipality
StreetRow = tuple[
    int, str, list[str], int, int | None
]  # id, name, alt names, municipality, settlement


@dataclass(frozen=True)
class Snapshot:
    """The gazetteer's names without geometry. Small enough to keep as a test fixture."""

    areas: list[AreaRow]
    places: list[PlaceRow]
    streets: list[StreetRow]
    borders: list[tuple[int, int]]  # municipality ids that share a border

    def save(self, path: Path) -> None:
        data = {
            "areas": self.areas,
            "places": self.places,
            "streets": self.streets,
            "borders": self.borders,
        }
        # mtime=0 keeps the file identical when the data is
        with gzip.GzipFile(path, "wb", mtime=0) as f:
            f.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode())

    @classmethod
    def load(cls, path: Path) -> Snapshot:
        with gzip.open(path, "rb") as f:
            data = json.loads(f.read())
        return cls(
            [tuple(r) for r in data["areas"]],
            [tuple(r) for r in data["places"]],
            [tuple(r) for r in data["streets"]],
            [(a, b) for a, b in data["borders"]],
        )


def build_index(snapshot: Snapshot) -> Index:
    neighbors: dict[int, set[int]] = defaultdict(set)
    for a, b in snapshot.borders:
        neighbors[a].add(b)
        neighbors[b].add(a)
    index = Index(neighbors={k: frozenset(v) for k, v in neighbors.items()})
    for id_, level, name, alt, muni in snapshot.areas:
        kind = {
            MUNICIPALITY_LEVEL: "municipality",
            SETTLEMENT_LEVEL: "settlement",
            URBAN_AREA_LEVEL: "urban_area",
        }.get(level)
        if kind is None:
            continue
        index.add(Entry("admin_areas", id_, name, kind, muni, keys=match_keys(name, *alt)))
    for id_, place_kind, name, alt, muni in snapshot.places:
        index.add(Entry("places", id_, name, place_kind, muni, keys=match_keys(name, *alt)))
    for id_, name, alt, muni, settlement in snapshot.streets:
        index.add(Entry("streets", id_, name, "street", muni, settlement, match_keys(name, *alt)))
    return index


def read_snapshot(session: Session) -> Snapshot:
    a = aliased(AdminArea)
    b = aliased(AdminArea)
    return Snapshot(
        areas=[
            (r.id, r.level, r.name, list(r.alt_names), r.municipality_id)
            for r in session.execute(
                select(
                    AdminArea.id,
                    AdminArea.level,
                    AdminArea.name,
                    AdminArea.alt_names,
                    AdminArea.municipality_id,
                ).order_by(AdminArea.id)
            )
        ],
        places=[
            (r.id, r.kind, r.name, list(r.alt_names), r.municipality_id)
            for r in session.execute(
                select(
                    Place.id, Place.kind, Place.name, Place.alt_names, Place.municipality_id
                ).order_by(Place.id)
            )
        ],
        streets=[
            (r.id, r.name, list(r.alt_names), r.municipality_id, r.settlement_id)
            for r in session.execute(
                select(
                    Street.id,
                    Street.name,
                    Street.alt_names,
                    Street.municipality_id,
                    Street.settlement_id,
                ).order_by(Street.id)
            )
        ],
        borders=[
            (x, y)
            for x, y in session.execute(
                select(a.id, b.id)
                .where(
                    a.level == MUNICIPALITY_LEVEL,
                    b.level == MUNICIPALITY_LEVEL,
                    a.id < b.id,
                    a.geom.ST_Intersects(b.geom),
                )
                .order_by(a.id, b.id)
            )
        ],
    )


def load_index(session: Session) -> Index:
    return build_index(read_snapshot(session))
