from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from vidituka.ingest import ingest_power
from vidituka.models import FetchRun, Outage

FIXTURE = Path(__file__).parents[1] / "fixtures" / "elektrodistribucija" / "2026-09-29_sample.json"
SKOPJE = ZoneInfo("Europe/Skopje")

# noon on the 29th: some outages are over, some running, some upcoming
NOON = datetime(2026, 9, 29, 12, 0, tzinfo=SKOPJE)
LATER = datetime(2026, 9, 29, 12, 30, tzinfo=SKOPJE)

Payload = list[dict[str, Any]]


@pytest.fixture
def payload() -> Payload:
    data: Payload = json.loads(FIXTURE.read_text("utf-8"))
    return data


def client_for(payload: Payload | None = None, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload if payload is not None else [])

    return httpx.Client(transport=httpx.MockTransport(handler))


def clock(at: datetime) -> Callable[[], datetime]:
    return lambda: at


def outages(session_factory: sessionmaker[Session]) -> list[Outage]:
    with session_factory() as session:
        return list(session.scalars(select(Outage).order_by(Outage.starts_at, Outage.id)))


def test_first_run_stores_everything(
    session_factory: sessionmaker[Session], payload: Payload
) -> None:
    stats = ingest_power(session_factory, client_for(payload), clock(NOON))

    assert (stats.total, stats.new, stats.withdrawn, stats.rejected) == (16, 16, 0, 0)
    assert len(outages(session_factory)) == 16
    with session_factory() as session:
        run = session.scalars(select(FetchRun)).one()
    assert run.status == "ok"
    assert (run.records_total, run.records_new) == (16, 16)
    assert run.finished_at is not None


def test_times_are_stored_as_the_right_instant(
    session_factory: sessionmaker[Session], payload: Payload
) -> None:
    ingest_power(session_factory, client_for(payload[:1]), clock(NOON))

    stored = outages(session_factory)[0]

    # 07:55 in Skopje (CEST) is 05:55 UTC
    assert stored.starts_at.astimezone(UTC) == datetime(2026, 9, 29, 5, 55, 36, tzinfo=UTC)


def test_second_run_updates_last_seen_only(
    session_factory: sessionmaker[Session], payload: Payload
) -> None:
    ingest_power(session_factory, client_for(payload), clock(NOON))
    first = {o.content_hash: o for o in outages(session_factory)}

    # new random ids on every request, like the real feed
    refetched = [{**r, "prekinID": f"id-{i}"} for i, r in enumerate(payload)]
    stats = ingest_power(session_factory, client_for(refetched), clock(LATER))

    assert stats.new == 0
    after = outages(session_factory)
    assert len(after) == 16
    for o in after:
        assert o.first_seen_at == first[o.content_hash].first_seen_at
        assert o.last_seen_at == LATER
        assert o.last_seen_run_id != o.first_seen_run_id


def test_upcoming_outage_that_disappears_is_withdrawn(
    session_factory: sessionmaker[Session], payload: Payload
) -> None:
    ingest_power(session_factory, client_for(payload), clock(NOON))
    ended, upcoming = payload[0], payload[4]  # 29.09 07:55 and 30.09 07:55
    remaining = [r for r in payload if r not in (ended, upcoming)]

    stats = ingest_power(session_factory, client_for(remaining), clock(LATER))

    assert stats.withdrawn == 1
    withdrawn = [o for o in outages(session_factory) if o.withdrawn_at is not None]
    assert [o.location_text for o in withdrawn] == [upcoming["adresa"].strip()]
    assert withdrawn[0].withdrawn_at == LATER


def test_withdrawn_outage_that_comes_back_is_restored(
    session_factory: sessionmaker[Session], payload: Payload
) -> None:
    ingest_power(session_factory, client_for(payload), clock(NOON))
    ingest_power(session_factory, client_for(payload[:4] + payload[5:]), clock(LATER))

    ingest_power(session_factory, client_for(payload), clock(LATER))

    assert all(o.withdrawn_at is None for o in outages(session_factory))


def test_empty_feed_withdraws_nothing(
    session_factory: sessionmaker[Session], payload: Payload
) -> None:
    ingest_power(session_factory, client_for(payload), clock(NOON))

    stats = ingest_power(session_factory, client_for([]), clock(LATER))

    assert stats.withdrawn == 0
    assert all(o.withdrawn_at is None for o in outages(session_factory))


def test_duplicate_records_in_one_response_are_stored_once(
    session_factory: sessionmaker[Session], payload: Payload
) -> None:
    stats = ingest_power(session_factory, client_for([payload[0], payload[0]]), clock(NOON))

    assert stats.new == 1
    assert len(outages(session_factory)) == 1


def test_rejected_records_are_counted_and_skipped(
    session_factory: sessionmaker[Session], payload: Payload
) -> None:
    broken = {k: v for k, v in payload[0].items() if k != "kraj"}

    stats = ingest_power(session_factory, client_for([broken, *payload[1:]]), clock(NOON))

    assert (stats.total, stats.rejected) == (15, 1)
    assert len(outages(session_factory)) == 15


def test_failed_fetch_is_recorded(session_factory: sessionmaker[Session]) -> None:
    with pytest.raises(httpx.HTTPStatusError):
        ingest_power(session_factory, client_for(status=503), clock(NOON))

    with session_factory() as session:
        run = session.scalars(select(FetchRun)).one()
        count = session.scalar(select(func.count()).select_from(Outage))
    assert run.status == "failed"
    assert run.error is not None and "503" in run.error
    assert count == 0
