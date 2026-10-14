from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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
