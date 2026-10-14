from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from vidituka.gazetteer.osm import extract
from vidituka.gazetteer.store import latest_load, replace_gazetteer
from vidituka.models import AdminArea, Place, Street

TINY = Path(__file__).parents[1] / "fixtures" / "osm" / "tiny.osm"


def counts(session: Session) -> tuple[int | None, ...]:
    return tuple(
        session.scalar(select(func.count()).select_from(model))
        for model in (AdminArea, Place, Street)
    )


def test_load_stores_everything_with_links(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as session:
        stats = replace_gazetteer(session, extract(TINY), source="tiny.osm")

    with session_factory() as session:
        assert counts(session) == (3, 2, 3) == (stats.areas, stats.places, stats.streets)
        settlement = session.scalars(select(AdminArea).where(AdminArea.level == 8)).one()
        municipality = session.get(AdminArea, settlement.municipality_id)
        assert municipality is not None and municipality.name == "Општина Исток"
        load = latest_load(session)
        assert load is not None and load.source == "tiny.osm"


def test_loading_again_replaces_instead_of_adding(session_factory: sessionmaker[Session]) -> None:
    data = extract(TINY)
    for _ in range(2):
        with session_factory.begin() as session:
            replace_gazetteer(session, data, source="tiny.osm")

    with session_factory() as session:
        assert counts(session) == (3, 2, 3)


def test_failed_load_keeps_the_previous_data(session_factory: sessionmaker[Session]) -> None:
    data = extract(TINY)
    with session_factory.begin() as session:
        replace_gazetteer(session, data, source="good")

    data.streets[0].municipality_osm_id = 999  # unknown municipality: the load must fail
    with pytest.raises(KeyError), session_factory.begin() as session:
        replace_gazetteer(session, data, source="bad")

    with session_factory() as session:
        assert counts(session) == (3, 2, 3)
        load = latest_load(session)
        assert load is not None and load.source == "good"


def test_spatial_queries_work(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as session:
        replace_gazetteer(session, extract(TINY), source="tiny.osm")

    with session_factory() as session:
        in_village = session.execute(
            text(
                "SELECT s.name FROM streets s JOIN admin_areas a ON a.name = 'Ново Село'"
                " WHERE ST_Within(s.geom, a.geom) ORDER BY s.name"
            )
        ).scalars()
        assert list(in_village) == ["Јајце", "Костурски Херои"]
        metres = session.scalar(
            text(
                "SELECT round(ST_Length(geom::geography)) FROM streets"
                " WHERE name = 'Костурски Херои'"
            )
        )
        assert metres is not None and 8000 < metres < 8500  # 0.1 degree of longitude at 41.8N
