from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from vidituka import locate
from vidituka.gazetteer.osm import extract
from vidituka.gazetteer.store import replace_gazetteer
from vidituka.ingest import ingest_power
from vidituka.locate import LOCATOR_VERSION, locate_pending
from vidituka.models import AdminArea, FetchRun, Outage, OutageLocation, Street

FIXTURES = Path(__file__).parents[1] / "fixtures"
TINY = FIXTURES / "osm" / "tiny.osm"
WHEN = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def load_tiny(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as session:
        replace_gazetteer(session, extract(TINY), source="tiny.osm")


def add_outage(session_factory: sessionmaker[Session], place: str, text: str) -> int:
    with session_factory.begin() as session:
        run = FetchRun(source="test", started_at=WHEN, status="ok")
        session.add(run)
        session.flush()
        outage = Outage(
            source="test",
            utility="power",
            content_hash=f"{place}|{text}",
            place=place,
            location_text=text,
            starts_at=WHEN,
            ends_at=WHEN,
            first_seen_at=WHEN,
            last_seen_at=WHEN,
            first_seen_run_id=run.id,
            last_seen_run_id=run.id,
        )
        session.add(outage)
        session.flush()
        return outage.id


def locations(session: Session, outage_id: int) -> list[OutageLocation]:
    return list(
        session.scalars(
            select(OutageLocation)
            .where(OutageLocation.outage_id == outage_id)
            .order_by(OutageLocation.position)
        )
    )


def test_matched_street_gets_its_line_and_unknown_one_its_village(
    session_factory: sessionmaker[Session],
) -> None:
    load_tiny(session_factory)
    outage_id = add_outage(
        session_factory, "ИСТОК-НОВО СЕЛО", "ПОТРОШУВАЧИТЕ НА УЛ.ЈАЈЦЕ БР.5 И УЛ.НЕПОСТОЈНА"
    )

    stats = locate_pending(session_factory)

    assert (stats.outages, stats.locations, stats.matched, stats.approximate) == (1, 2, 1, 1)
    with session_factory() as session:
        jajce, unknown = locations(session, outage_id)
        street = session.scalars(
            select(Street).where(Street.name == "Јајце", Street.settlement_id.is_not(None))
        ).one()
        village = session.scalars(select(AdminArea).where(AdminArea.name == "Ново Село")).one()

        assert (jajce.matched_name, jajce.match_method, jajce.approximate) == (
            "Јајце",
            "exact",
            False,
        )
        assert jajce.numbers == ["5"]
        assert session.scalar(func.ST_Equals(jajce.geom, street.geom))

        assert (unknown.matched_name, unknown.approximate) == (None, True)
        assert session.scalar(func.ST_Equals(unknown.geom, village.geom))

        outage = session.get(Outage, outage_id)
        assert outage is not None and outage.locator_version == LOCATOR_VERSION


def test_nothing_is_located_without_a_gazetteer(session_factory: sessionmaker[Session]) -> None:
    outage_id = add_outage(session_factory, "ИСТОК", "УЛ.ЈАЈЦЕ")

    stats = locate_pending(session_factory)

    assert stats.outages == 0
    with session_factory() as session:
        outage = session.get(Outage, outage_id)
        assert outage is not None and outage.located_at is None


def test_located_outages_are_not_redone(session_factory: sessionmaker[Session]) -> None:
    load_tiny(session_factory)
    add_outage(session_factory, "ИСТОК", "УЛ.ЈАЈЦЕ")

    first = locate_pending(session_factory)
    second = locate_pending(session_factory)

    assert (first.outages, second.outages) == (1, 0)


def test_new_rules_or_a_new_gazetteer_redo_them_without_duplicates(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    load_tiny(session_factory)
    outage_id = add_outage(session_factory, "ИСТОК", "УЛ.ЈАЈЦЕ")
    locate_pending(session_factory)

    monkeypatch.setattr(locate, "LOCATOR_VERSION", LOCATOR_VERSION + 1)
    after_new_rules = locate_pending(session_factory)
    load_tiny(session_factory)
    after_new_gazetteer = locate_pending(session_factory)

    assert (after_new_rules.outages, after_new_gazetteer.outages) == (1, 1)
    with session_factory() as session:
        assert len(locations(session, outage_id)) == 1


def test_deleting_an_outage_deletes_its_locations(session_factory: sessionmaker[Session]) -> None:
    load_tiny(session_factory)
    outage_id = add_outage(session_factory, "ИСТОК", "УЛ.ЈАЈЦЕ")
    locate_pending(session_factory)

    with session_factory.begin() as session:
        outage = session.get(Outage, outage_id)
        session.delete(outage)

    with session_factory() as session:
        assert locations(session, outage_id) == []


def test_unknown_municipality_is_stored_without_a_place(
    session_factory: sessionmaker[Session],
) -> None:
    load_tiny(session_factory)
    outage_id = add_outage(session_factory, "НЕПОЗНАТО", "УЛ.ЈАЈЦЕ")

    stats = locate_pending(session_factory)

    assert stats.unplaced == 1
    with session_factory() as session:
        (row,) = locations(session, outage_id)
        assert (row.name, row.geom) == ("ЈАЈЦЕ", None)


def test_feed_to_locations(session_factory: sessionmaker[Session]) -> None:
    # the whole path on a real feed sample: nothing crashes and every location is stored
    load_tiny(session_factory)
    payload = json.loads(
        (FIXTURES / "elektrodistribucija" / "2026-09-29_sample.json").read_text("utf-8")
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    ingest_power(session_factory, client, lambda: WHEN)

    stats = locate_pending(session_factory)

    assert stats.outages == 16
    with session_factory() as session:
        stored = session.scalar(select(func.count()).select_from(OutageLocation))
        located = session.scalar(
            select(func.count()).select_from(Outage).where(Outage.located_at.is_not(None))
        )
    assert stored == stats.locations > 0
    assert located == 16


def test_a_street_through_two_villages_is_drawn_whole(
    session_factory: sessionmaker[Session],
) -> None:
    load_tiny(session_factory)
    with session_factory.begin() as session:
        part = session.scalars(select(Street).where(Street.name == "Јајце")).first()
        assert part is not None
        # the same street continuing outside Ново Село
        session.add(
            Street(
                name="Јајце",
                name_key="ЈАЈЦЕ",
                municipality_id=part.municipality_id,
                settlement_id=None,
                osm_way_ids=[999],
                geom=func.ST_GeomFromText("MULTILINESTRING((21.6 41.7, 21.7 41.7))", 4326),
            )
        )
    outage_id = add_outage(session_factory, "ИСТОК", "УЛ.ЈАЈЦЕ")

    locate_pending(session_factory)

    with session_factory() as session:
        (row,) = locations(session, outage_id)
        assert session.scalar(func.ST_NumGeometries(func.ST_Multi(row.geom))) == 2


def test_village_is_drawn_as_its_boundary_not_its_point(
    session_factory: sessionmaker[Session],
) -> None:
    load_tiny(session_factory)
    outage_id = add_outage(session_factory, "ИСТОК", "С.НОВО СЕЛО")

    locate_pending(session_factory)

    with session_factory() as session:
        (row,) = locations(session, outage_id)
        assert session.scalar(func.GeometryType(row.geom)) in ("POLYGON", "MULTIPOLYGON")
