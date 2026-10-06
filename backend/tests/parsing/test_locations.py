from __future__ import annotations

import pytest

from vidituka.parsing.evaluate import evaluate, load_labels
from vidituka.parsing.locations import parse_locations
from vidituka.parsing.models import Location

SKOPJE = "КАРПОШ-СКОПЈЕ-КАРПОШ"


def names(locations: list[Location]) -> list[tuple[str, str, bool]]:
    return [(loc.kind, loc.name, loc.partial) for loc in locations]


def test_street_list_continues_without_markers() -> None:
    result = parse_locations("УЛ.АВРОРА, КРЕСНА, МИТРЕ ВЛАОТ", SKOPJE)

    assert names(result) == [
        ("street", "АВРОРА", False),
        ("street", "КРЕСНА", False),
        ("street", "МИТРЕ ВЛАОТ", False),
    ]


def test_part_of_a_plural_applies_to_the_whole_list() -> None:
    result = parse_locations("ЌЕ ОСТАНАТ БЕЗ ЕЕ НА ДЕЛ ОД УЛИЦИТЕ АЛПИ, ЈАЈЦЕ И КРЕСНА", SKOPJE)

    assert all(loc.partial for loc in result)
    assert len(result) == 3


def test_part_of_a_single_item_stops_at_a_comma_but_not_at_and() -> None:
    joined = parse_locations("ДЕЛ ОД С.ЛАРЦЕ И С.ДОБАРЦЕ", "ЖЕЛИНО")
    listed = parse_locations("ДЕЛ ОД С.ЛАРЦЕ, С.ДОБАРЦЕ", "ЖЕЛИНО")

    assert [loc.partial for loc in joined] == [True, True]
    assert [loc.partial for loc in listed] == [True, False]


def test_reason_for_the_work_is_ignored() -> None:
    text = "ПОРАДИ РАБОТА ВО ТС ВОДНО 2 (38 1111) БЕЗ ЕЕ ЌЕ ОСТАНАТ ПОТРОШУВАЧИТЕ НА УЛ.ЈАЈЦЕ"

    assert names(parse_locations(text, SKOPJE)) == [("street", "ЈАЈЦЕ", False)]


def test_list_stops_at_trailing_maintenance_text() -> None:
    text = "УЛИЦИТЕ АЛПИ И ЈАЈЦЕ ПОРАДИ РАБОТА ВО ТС ГАЗИ БАБА 4, ЧИСТЕЊЕ И ПРОВЕРКА"

    assert [loc.name for loc in parse_locations(text, SKOPJE)] == ["АЛПИ", "ЈАЈЦЕ"]


def test_markers_are_not_matched_inside_words() -> None:
    text = "С.РОСОМАН, ГРАДСКО, УЛАНЦИ"

    assert [loc.name for loc in parse_locations(text, "ГРАДСКО")] == [
        "РОСОМАН",
        "ГРАДСКО",
        "УЛАНЦИ",
    ]


def test_companies_end_a_list() -> None:
    text = "С.ЖЕЛИНО, ОБЈЕКТИ КАЈ ШКОЛОТО И ГИПСАРАТА, МЛИН"

    assert [loc.name for loc in parse_locations(text, "ЖЕЛИНО")] == ["ЖЕЛИНО"]


def test_reference_points_are_not_locations() -> None:
    text = "ДЕЛ ОД УЛ.МЛАДИНСКА ОД ФОН ДО РАСКРСНИЦА СО УЛ.ЈАЈЦЕ, ФАБРИКА НА ПАТ ЗА С.РАМНА"

    assert names(parse_locations(text, "СТРУМИЦА")) == [("street", "МЛАДИНСКА", True)]


@pytest.mark.parametrize(
    ("text", "name", "numbers"),
    [
        ("УЛ. ГОЦЕ ДЕЛЧЕВ БР.17", "ГОЦЕ ДЕЛЧЕВ", ["17"]),
        ("ДЕЛ ОД УЛ. ХРИСТО ТАТАРЧЕВ 5", "ХРИСТО ТАТАРЧЕВ", ["5"]),
        ("УЛ.ЈАЈЦЕ УЛ.БР 8", "ЈАЈЦЕ", ["8"]),
    ],
)
def test_house_numbers(text: str, name: str, numbers: list[str]) -> None:
    (loc,) = parse_locations(text, SKOPJE)

    assert (loc.name, loc.numbers) == (name, numbers)


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("УЛ.21-ВА", "21"),
        ("УЛ. 4", "4"),
        ("УЛ.12 - ТА УДАРНА БРИГАДА", "12-ТА УДАРНА БРИГАДА"),
        ("УЛ 8 ТИ МАРТ", "8-ТИ МАРТ"),
    ],
)
def test_numbered_and_ordinal_streets(text: str, name: str) -> None:
    (loc,) = parse_locations(text, SKOPJE)

    assert (loc.name, loc.numbers) == (name, [])


def test_and_inside_a_known_name_is_kept() -> None:
    result = parse_locations("УЛ.СВ. КИРИЛ И МЕТОДИЈ, УЛ.ЈАЈЦЕ", SKOPJE)

    assert [loc.name for loc in result] == ["СВЕТИ КИРИЛ И МЕТОДИЈ", "ЈАЈЦЕ"]


def test_street_in_a_named_village() -> None:
    by_word = parse_locations("УЛ. 3 И УЛ.7 ВО ДРАЧЕВО", "КИСЕЛА ВОДА-ДРАЧЕВО")
    by_place = parse_locations("УЛ. 5 ДРАЧЕВО", "КИСЕЛА ВОДА-ДРАЧЕВО")

    assert [(loc.name, loc.in_) for loc in by_word] == [("3", "ДРАЧЕВО"), ("7", "ДРАЧЕВО")]
    assert [(loc.name, loc.in_) for loc in by_place] == [("5", "ДРАЧЕВО")]


def test_upper_and_lower_village_abbreviations() -> None:
    result = parse_locations("С.Д.ЛЕШНИЦА, С.Г.СРПЦИ", "ЖЕЛИНО")

    assert [loc.name for loc in result] == ["ДОЛНА ЛЕШНИЦА", "ГОРНО СРПЦИ"]


def test_qualifier_in_brackets_marks_part() -> None:
    (loc,) = parse_locations("С.ЛАРЦЕ ( ДЕЛОТ ОКОЛУ ЦРКВАТА), МЛЕКАРА", "ЖЕЛИНО")

    assert (loc.name, loc.partial) == ("ЛАРЦЕ", True)


def test_same_place_twice_counts_once_and_whole_wins() -> None:
    text = "ОБЈЕКТИ ПРЕД ВЛЕЗОТ НА С.РАМНА КАКО И СИТЕ КОРИСНИЦИ ВО С.РАМНА"

    assert names(parse_locations(text, "БИТОЛА")) == [("settlement", "РАМНА", False)]


def test_only_companies_gives_nothing() -> None:
    assert parse_locations("АКТИВА,ВИВЕНДИ,БЕНЗ.ПУМПА ВАГО", "ШТИП") == []


def test_score_does_not_drop_below_baseline() -> None:
    # raise these when the parser improves; never lower them to make a change pass
    report = evaluate(parse_locations, load_labels())

    assert report.overall.f1 >= 0.95
    assert report.overall.precision >= 0.97
    assert report.partial.value >= 0.99
