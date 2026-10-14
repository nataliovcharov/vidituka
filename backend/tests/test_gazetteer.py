from __future__ import annotations

from pathlib import Path

import pytest

from vidituka.gazetteer.names import name_key, split_names
from vidituka.gazetteer.osm import Extract, extract

TINY = Path(__file__).parent / "fixtures" / "osm" / "tiny.osm"


@pytest.fixture(scope="module")
def data() -> Extract:
    return extract(TINY)


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Улица Никола Петров", "НИКОЛА ПЕТРОВ"),
        ("ул. Никола Петров", "НИКОЛА ПЕТРОВ"),
        ("Булевар Партизански Одреди", "ПАРТИЗАНСКИ ОДРЕДИ"),
        ("Општина Гази Баба", "ГАЗИ БАБА"),
        ("1.", "1"),
        ("Димо Димоски - Наредникот", "ДИМО ДИМОСКИ НАРЕДНИКОТ"),
        ("Градско", "ГРАДСКО"),
    ],
)
def test_name_key(name: str, key: str) -> None:
    assert name_key(name) == key


def test_split_names() -> None:
    assert split_names("А; Б ;") == ["А", "Б"]
    assert split_names(None) == []


def test_keeps_only_areas_inside_the_country(data: Extract) -> None:
    names = {(a.level, a.name) for a in data.areas}

    assert names == {(7, "Општина Исток"), (7, "Општина Запад"), (8, "Ново Село")}


def test_settlement_points_at_its_municipality(data: Extract) -> None:
    by_name = {a.name: a for a in data.areas}

    assert by_name["Ново Село"].municipality_osm_id == by_name["Општина Исток"].osm_id
    assert by_name["Ново Село"].alt_names == ["Старо Име"]


def test_places_inside_the_country_with_alt_names(data: Extract) -> None:
    places = {p.name: p for p in data.places}

    assert set(places) == {"Ново Село", "Нова Населба"}
    assert places["Нова Населба"].alt_names == ["Населба А", "Населба Б"]


def test_street_pieces_with_the_same_key_become_one_line(data: Extract) -> None:
    east = next(a.osm_id for a in data.areas if a.name == "Општина Исток")
    (street,) = [s for s in data.streets if s.name == "Јајце" and s.municipality_osm_id == east]

    assert len(street.way_ids) == 3
    assert len(street.geom.geoms) == 1  # merged into one continuous line
    assert street.alt_names == ["Улица Јајце"]
    assert street.settlement_osm_id is not None


def test_same_name_in_another_municipality_is_another_street(data: Extract) -> None:
    assert len([s for s in data.streets if s.name == "Јајце"]) == 2


def test_old_names_are_kept(data: Extract) -> None:
    (street,) = [s for s in data.streets if s.name == "Костурски Херои"]

    assert street.alt_names == ["29. Ноември"]


def test_footways_unnamed_and_foreign_streets_are_skipped(data: Extract) -> None:
    assert {s.name for s in data.streets} == {"Јајце", "Костурски Херои"}


def test_file_without_the_country_is_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "empty.osm"
    empty.write_text('<?xml version="1.0"?><osm version="0.6"></osm>', "utf-8")

    with pytest.raises(ValueError, match="ISO3166-1=MK"):
        extract(empty)
