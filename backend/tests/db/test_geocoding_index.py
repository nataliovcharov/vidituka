from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from vidituka.gazetteer.osm import extract
from vidituka.gazetteer.store import replace_gazetteer
from vidituka.geocoding.context import resolve_place
from vidituka.geocoding.index import Snapshot, build_index, load_index, read_snapshot
from vidituka.geocoding.matching import match_location
from vidituka.parsing.models import Location

TINY = Path(__file__).parents[1] / "fixtures" / "osm" / "tiny.osm"


def test_index_from_the_database(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as session:
        replace_gazetteer(session, extract(TINY), source="tiny.osm")

    with session_factory() as session:
        index = load_index(session)

    istok = next(m for m in index.municipalities if m.name == "Општина Исток")
    zapad = next(m for m in index.municipalities if m.name == "Општина Запад")
    assert index.neighbors[istok.id] == {zapad.id}

    context = resolve_place(index, "ИСТОК-СТАРО ИМЕ")
    match = match_location(index, context, Location("street", "ЈАЈЦЕ"))
    assert context.settlement is not None and context.settlement.name == "Ново Село"
    assert match is not None and match.entries[0].municipality_id == istok.id


def test_snapshot_round_trip(session_factory: sessionmaker[Session], tmp_path: Path) -> None:
    with session_factory.begin() as session:
        replace_gazetteer(session, extract(TINY), source="tiny.osm")
    with session_factory() as session:
        snapshot = read_snapshot(session)

    snapshot.save(tmp_path / "s.json.gz")
    loaded = Snapshot.load(tmp_path / "s.json.gz")

    assert loaded == snapshot
    assert build_index(loaded).entries == build_index(snapshot).entries
