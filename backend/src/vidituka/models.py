from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
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
