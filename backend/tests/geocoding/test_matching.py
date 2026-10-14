from __future__ import annotations

import pytest

from vidituka.geocoding.context import resolve_place
from vidituka.geocoding.index import Index, Snapshot, build_index
from vidituka.geocoding.matching import Match, match_location
from vidituka.parsing.models import Kind, Location

# municipalities: Исток and Запад share a border, Далеку doesn't touch either
ISTOK, ZAPAD, DALEKU, CHESHINOVO, DEMIR_HISAR = 1, 2, 3, 4, 5
NOVO_SELO, KADINO, ISTOK_SEAT = 10, 11, 12


def make_index(
    places: list[tuple[int, str, str, int]] | None = None,
    streets: list[tuple[int, str, int, int | None]] | None = None,
) -> Index:
    return build_index(
        Snapshot(
            areas=[
                (ISTOK, 7, "Општина Исток", [], None),
                (ZAPAD, 7, "Општина Запад", [], None),
                (DALEKU, 7, "Општина Далеку", [], None),
                (CHESHINOVO, 7, "Општина Чешиново-Облешево", [], None),
                (DEMIR_HISAR, 7, "Општина Демир Хисар/Мургашево", [], None),
                (NOVO_SELO, 8, "Ново Село", ["Старо Име"], ISTOK),
                (KADINO, 8, "Кадино", [], ISTOK),
                (ISTOK_SEAT, 8, "Исток", [], ISTOK),
            ],
            places=[(i, kind, name, [], muni) for i, kind, name, muni in places or []],
            streets=[
                (i, name, [], muni, settlement) for i, name, muni, settlement in streets or []
            ],
            borders=[(ISTOK, ZAPAD)],
        )
    )


def find(index: Index, place: str, kind: Kind, name: str, in_: str | None = None) -> Match | None:
    return match_location(index, resolve_place(index, place), Location(kind, name, in_=in_))


@pytest.mark.parametrize(
    ("place", "municipality", "settlement"),
    [
        ("ИСТОК-НОВО СЕЛО", "Општина Исток", "Ново Село"),
        ("ИСТОК-СТАРО ИМЕ", "Општина Исток", "Ново Село"),
        ("ИСТОК-КАДИНО (ИСТОК)", "Општина Исток", "Кадино"),
        ("ИСТОК-ИСТОК-ИНД.ЗОНА", "Општина Исток", "Исток"),
        # the municipality alone means its seat
        ("ИСТОК", "Општина Исток", "Исток"),
        ("ЧЕШИНОВО - ОБЛЕШЕВО", "Општина Чешиново-Облешево", None),
        ("ДЕМИР ХИСАР", "Општина Демир Хисар/Мургашево", None),
        ("НЕПОЗНАТО-СЕЛО", None, None),
    ],
)
def test_resolves_the_feed_place(place: str, municipality: str, settlement: str | None) -> None:
    context = resolve_place(make_index(), place)
    assert (context.municipality.name if context.municipality else None) == municipality
    assert (context.settlement.name if context.settlement else None) == settlement


def test_street_is_found_in_its_own_municipality() -> None:
    index = make_index(streets=[(100, "Јајце", ZAPAD, None), (101, "Јајце", ISTOK, None)])

    match = find(index, "ИСТОК", "street", "ЈАЈЦЕ")

    assert match is not None
    assert [e.id for e in match.entries] == [101]
    assert (match.method, match.widened) == ("exact", False)


def test_street_across_the_border_is_found_but_flagged() -> None:
    index = make_index(streets=[(100, "Зеничка", ZAPAD, None), (101, "Зеничка", DALEKU, None)])

    match = find(index, "ИСТОК", "street", "ЗЕНИЧКА")

    assert match is not None
    assert [e.id for e in match.entries] == [100]
    assert match.widened


def test_street_in_a_municipality_that_is_not_next_door_is_not_found() -> None:
    index = make_index(streets=[(101, "Зеничка", DALEKU, None)])

    assert find(index, "ИСТОК", "street", "ЗЕНИЧКА") is None


@pytest.mark.parametrize(
    ("feed", "osm"),
    [
        ("МАК. КОСОВСКА", "Македонско-косовска бригада"),
        ("ВС БАТО", "Видое Смилевски Бато"),
        ("ЈОРГО ОСМАНО", "Ј. Османо"),
    ],
)
def test_abbreviations(feed: str, osm: str) -> None:
    index = make_index(streets=[(100, osm, ISTOK, None), (101, "Бато Бато", ISTOK, None)])

    match = find(index, "ИСТОК", "street", feed)

    assert match is not None
    assert (match.name, match.method) == (osm, "abbreviation")


def test_fuzzy_fixes_a_typo() -> None:
    index = make_index(streets=[(100, "Гвадалахара", ISTOK, None)])

    match = find(index, "ИСТОК", "street", "ГВАДАЛАХРА")

    assert match is not None
    assert (match.name, match.method) == ("Гвадалахара", "fuzzy")


@pytest.mark.parametrize(
    ("feed", "osm"),
    [
        # a missing word is a different street, not a typo
        ("МАКЕДОНСКА БРИГАДА", "Втора македонска бригада"),
        ("УЛИЦА 1", "Улица 7"),
    ],
)
def test_fuzzy_does_not_bridge_real_differences(feed: str, osm: str) -> None:
    index = make_index(streets=[(100, osm, ISTOK, None)])

    assert find(index, "ИСТОК", "street", feed) is None


def test_two_equally_good_answers_are_left_unmatched() -> None:
    index = make_index(
        streets=[(100, "Стојна Стевкова", ISTOK, None), (101, "Стојна Стефанова", ISTOK, None)]
    )

    assert find(index, "ИСТОК", "street", "СТОЈНА СТЕВАНОВА") is None


def test_a_name_repeated_in_two_villages_prefers_the_one_named_in_the_text() -> None:
    index = make_index(streets=[(100, "1", ISTOK, NOVO_SELO), (101, "1", ISTOK, KADINO)])

    match = find(index, "ИСТОК-НОВО СЕЛО", "street", "1", in_="КАДИНО")

    assert match is not None
    assert [e.id for e in match.entries] == [101]


def test_same_street_split_by_villages_prefers_the_outage_settlement() -> None:
    index = make_index(streets=[(100, "Јајце", ISTOK, NOVO_SELO), (101, "Јајце", ISTOK, KADINO)])

    match = find(index, "ИСТОК-КАДИНО", "street", "ЈАЈЦЕ")

    assert match is not None
    assert [e.id for e in match.entries] == [101]


def test_settlement_prefers_the_boundary_over_the_point() -> None:
    index = make_index(places=[(200, "village", "Ново Село", ISTOK)])

    match = find(index, "ИСТОК", "settlement", "НОВО СЕЛО")

    assert match is not None
    assert [(e.table, e.id) for e in match.entries] == [("admin_areas", 10), ("places", 200)]


def test_village_across_the_border_needs_an_exact_name() -> None:
    index = make_index(places=[(200, "village", "Соколарци", ZAPAD)])

    exact = find(index, "ИСТОК", "settlement", "СОКОЛАРЦИ")
    typo = find(index, "ИСТОК", "settlement", "СОКОЛАРЦЕ")

    assert exact is not None and exact.widened
    assert typo is None


def test_neighborhood_falls_back_to_a_street_of_that_name() -> None:
    index = make_index(streets=[(100, "Циглана", ISTOK, None)])

    match = find(index, "ИСТОК", "neighborhood", "ЦИГЛАНА")

    assert match is not None
    assert match.entries[0].kind == "street"


def test_municipality() -> None:
    match = find(make_index(), "ИСТОК", "municipality", "ЗАПАД")

    assert match is not None and match.name == "Општина Запад"


def test_unknown_municipality_matches_nothing() -> None:
    index = make_index(streets=[(100, "Јајце", ISTOK, None)])

    assert find(index, "НЕПОЗНАТО", "street", "ЈАЈЦЕ") is None


def test_a_tie_stops_the_search_instead_of_looking_further_away() -> None:
    index = make_index(
        streets=[
            (100, "Стојна Стевкова", ISTOK, None),
            (101, "Стојна Стефанова", ISTOK, None),
            (102, "Стојна Стеванова", ZAPAD, None),
        ]
    )

    assert find(index, "ИСТОК", "street", "СТОЈНА СТЕВАНОВА") is None


def test_an_abbreviation_needs_at_least_one_whole_word() -> None:
    index = make_index(streets=[(100, "Македонско-косовска бригада", ISTOK, None)])

    assert find(index, "ИСТОК", "street", "МАК КОС") is None
