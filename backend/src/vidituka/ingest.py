from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from vidituka.models import FetchRun, Outage
from vidituka.sources import elektrodistribucija as ed

log = logging.getLogger(__name__)

POWER_SOURCE = "elektrodistribucija"


@dataclass(frozen=True)
class IngestStats:
    total: int
    rejected: int
    new: int
    withdrawn: int


def utc_now() -> datetime:
    return datetime.now(UTC)


def ingest_power(
    session_factory: sessionmaker[Session],
    client: httpx.Client,
    now: Callable[[], datetime] = utc_now,
) -> IngestStats:
    # the run row is committed first so a failed fetch still leaves a trace
    with session_factory.begin() as session:
        run = FetchRun(source=POWER_SOURCE, started_at=now(), status="running")
        session.add(run)
        session.flush()
        run_id = run.id

    try:
        result = ed.fetch_feed(client)
        for rejected in result.rejected:
            log.warning("rejected record: %s", rejected.error)

        with session_factory.begin() as session:
            stats = store_power_outages(session, result, run_id, now())
            session.execute(
                update(FetchRun)
                .where(FetchRun.id == run_id)
                .values(
                    status="ok",
                    finished_at=now(),
                    records_total=stats.total,
                    records_rejected=stats.rejected,
                    records_new=stats.new,
                    records_withdrawn=stats.withdrawn,
                )
            )
        return stats
    except Exception as exc:
        with session_factory.begin() as session:
            session.execute(
                update(FetchRun)
                .where(FetchRun.id == run_id)
                .values(status="failed", finished_at=now(), error=f"{type(exc).__name__}: {exc}")
            )
        raise


def store_power_outages(
    session: Session, result: ed.FeedResult, run_id: int, now: datetime
) -> IngestStats:
    # the feed could repeat a record, and postgres won't upsert the same row twice
    rows: dict[str, dict[str, Any]] = {}
    for o in result.outages:
        rows[o.content_hash] = {
            "source": POWER_SOURCE,
            "utility": "power",
            "content_hash": o.content_hash,
            "region_id": o.kec_id,
            "place": o.place.strip(),
            "location_text": o.location_text.strip(),
            "outage_type": o.outage_type,
            "voltage_level": o.voltage_level,
            "starts_at": o.starts_at,
            "ends_at": o.ends_at,
            "first_seen_at": now,
            "last_seen_at": now,
            "first_seen_run_id": run_id,
            "last_seen_run_id": run_id,
        }

    new = 0
    if rows:
        insert_stmt = insert(Outage).values(list(rows.values()))
        upsert = insert_stmt.on_conflict_do_update(
            constraint="uq_outages_source_content_hash",
            set_={
                "last_seen_at": insert_stmt.excluded.last_seen_at,
                "last_seen_run_id": insert_stmt.excluded.last_seen_run_id,
                "withdrawn_at": None,
            },
        ).returning(Outage.first_seen_run_id)
        new = sum(1 for first_run in session.scalars(upsert) if first_run == run_id)

    withdrawn = 0
    # an empty feed is more likely a problem on their side than zero planned outages
    if rows:
        missing_upcoming = (
            update(Outage)
            .where(
                Outage.source == POWER_SOURCE,
                Outage.withdrawn_at.is_(None),
                Outage.starts_at > now,
                Outage.content_hash.not_in(rows.keys()),
            )
            .values(withdrawn_at=now)
            .returning(Outage.id)
        )
        withdrawn = len(session.scalars(missing_upcoming).all())

    return IngestStats(
        total=len(result.outages), rejected=len(result.rejected), new=new, withdrawn=withdrawn
    )
