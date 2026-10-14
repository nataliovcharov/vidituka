from __future__ import annotations

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# stable constraint names so migrations stay predictable
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class FetchRun(Base):
    __tablename__ = "fetch_runs"
    __table_args__ = (CheckConstraint("status IN ('running', 'ok', 'failed')", name="status"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10))
    records_total: Mapped[int | None] = mapped_column(Integer)
    records_rejected: Mapped[int | None] = mapped_column(Integer)
    records_new: Mapped[int | None] = mapped_column(Integer)
    records_withdrawn: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)


class Outage(Base):
    __tablename__ = "outages"
    __table_args__ = (
        UniqueConstraint("source", "content_hash"),
        CheckConstraint("utility IN ('power', 'water')", name="utility"),
        CheckConstraint("ends_at >= starts_at", name="ends_after_start"),
        Index(None, "starts_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    utility: Mapped[str] = mapped_column(String(10))
    content_hash: Mapped[str] = mapped_column(String(64))

    region_id: Mapped[int | None] = mapped_column(Integer)
    place: Mapped[str] = mapped_column(Text)
    location_text: Mapped[str] = mapped_column(Text)
    outage_type: Mapped[str | None] = mapped_column(Text)
    voltage_level: Mapped[str | None] = mapped_column(String(20))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_seen_run_id: Mapped[int] = mapped_column(ForeignKey("fetch_runs.id"))
    last_seen_run_id: Mapped[int] = mapped_column(ForeignKey("fetch_runs.id"))
    # set when an upcoming outage drops out of the feed (cancelled or rescheduled)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # when its locations were last worked out, and by which version of the rules
    located_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locator_version: Mapped[int | None] = mapped_column(Integer)

    locations: Mapped[list[OutageLocation]] = relationship(
        back_populates="outage", order_by="OutageLocation.position", passive_deletes=True
    )


class OutageLocation(Base):
    """One street, village or neighbourhood an outage names, and where it is.

    The geometry is a copy, not a link to the gazetteer: reloading OSM replaces those rows,
    and an old outage should still be drawable.
    """

    __tablename__ = "outage_locations"
    __table_args__ = (
        UniqueConstraint("outage_id", "position"),
        CheckConstraint(
            "kind IN ('street', 'settlement', 'neighborhood', 'municipality')", name="kind"
        ),
        CheckConstraint("match_method IN ('exact', 'abbreviation', 'fuzzy')", name="match_method"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    outage_id: Mapped[int] = mapped_column(ForeignKey("outages.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)  # order in the text
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(Text)  # as the parser read it
    partial: Mapped[bool] = mapped_column(Boolean)
    # house numbers: "42" or {"from": "10", "to": "30"}
    numbers: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    within: Mapped[str | None] = mapped_column(Text)  # a village named in the text

    # what it matched in the gazetteer, if anything
    matched_name: Mapped[str | None] = mapped_column(Text)
    match_method: Mapped[str | None] = mapped_column(String(20))
    # found in a neighbouring municipality rather than the outage's own
    match_widened: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # true when geom is only the village or municipality around it
    approximate: Mapped[bool] = mapped_column(Boolean)
    geom: Mapped[WKBElement | None] = mapped_column(Geometry("GEOMETRY", srid=4326))

    outage: Mapped[Outage] = relationship(back_populates="locations")


# reference data loaded from OpenStreetMap (see docs/adr/0004-gazetteer.md)


class GazetteerLoad(Base):
    __tablename__ = "gazetteer_loads"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source: Mapped[str] = mapped_column(Text)
    data_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    areas: Mapped[int] = mapped_column(Integer)
    places: Mapped[int] = mapped_column(Integer)
    streets: Mapped[int] = mapped_column(Integer)


class AdminArea(Base):
    __tablename__ = "admin_areas"
    __table_args__ = (
        CheckConstraint("level IN (2, 6, 7, 8, 9)", name="level"),
        Index(None, "level", "name_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    osm_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    # 2 country, 6 city of Skopje, 7 municipality, 8 settlement, 9 urban area
    level: Mapped[int] = mapped_column(SmallInteger)
    name: Mapped[str] = mapped_column(Text)
    name_key: Mapped[str] = mapped_column(Text)
    alt_names: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("admin_areas.id"))
    geom: Mapped[WKBElement] = mapped_column(Geometry("MULTIPOLYGON", srid=4326))


class Place(Base):
    __tablename__ = "places"
    __table_args__ = (Index(None, "name_key"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    osm_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    kind: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    name_key: Mapped[str] = mapped_column(Text)
    alt_names: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("admin_areas.id"))
    geom: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=4326))


class Street(Base):
    __tablename__ = "streets"
    __table_args__ = (
        # one row per street name per settlement, also when the settlement is unknown
        UniqueConstraint(
            "municipality_id", "settlement_id", "name_key", postgresql_nulls_not_distinct=True
        ),
        Index(None, "name_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    name_key: Mapped[str] = mapped_column(Text)
    alt_names: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    municipality_id: Mapped[int] = mapped_column(ForeignKey("admin_areas.id"))
    settlement_id: Mapped[int | None] = mapped_column(ForeignKey("admin_areas.id"))
    osm_way_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger))
    geom: Mapped[WKBElement] = mapped_column(Geometry("MULTILINESTRING", srid=4326))
