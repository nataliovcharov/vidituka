from __future__ import annotations

import pytest

from vidituka.parsing.evaluate import (
    GoldLocation,
    LabeledRecord,
    Parser,
    evaluate,
    load_labels,
    normalize_name,
)
from vidituka.parsing.models import Location


def gold(kind: str, name: str, partial: bool = False, uncertain: bool = False) -> GoldLocation:
    return GoldLocation(kind, name, partial, (), None, uncertain)


def record(*locations: GoldLocation, region_id: int = 10) -> LabeledRecord:
    return LabeledRecord("00000001", region_id, "ЦЕНТАР-СКОПЈЕ-ЦЕНТАР", "text", locations)


def parser_returning(*locations: Location) -> Parser:
    return lambda text, place: list(locations)


def test_names_compare_without_case_punctuation_or_spaces() -> None:
    assert normalize_name("Димо Димоски - Наредникот") == normalize_name("ДИМО ДИМОСКИ-НАРЕДНИКОТ")
    assert normalize_name("СВ. КИРИЛ") == "СВ КИРИЛ"


def test_counts_hits_misses_and_extras() -> None:
    rec = record(gold("street", "АВРОРА"), gold("street", "КРЕСНА"))
    parse = parser_returning(Location("street", "АВРОРА"), Location("street", "ЈАЈЦЕ"))

    report = evaluate(parse, [rec])

    assert (report.overall.tp, report.overall.fp, report.overall.fn) == (1, 1, 1)
    assert report.overall.precision == report.overall.recall == 0.5


def test_kind_must_match() -> None:
    rec = record(gold("neighborhood", "ЦИГЛАНА"))

    report = evaluate(parser_returning(Location("settlement", "ЦИГЛАНА")), [rec])

    assert report.by_kind["neighborhood"].fn == 1
    assert report.by_kind["settlement"].fp == 1


def test_uncertain_labels_are_neither_hits_nor_misses() -> None:
    rec = record(gold("street", "159 БИС", uncertain=True), gold("street", "ЧЕЛОПЕК"))

    found = evaluate(
        parser_returning(Location("street", "159 БИС"), Location("street", "ЧЕЛОПЕК")), [rec]
    )
    skipped = evaluate(parser_returning(Location("street", "ЧЕЛОПЕК")), [rec])

    assert (found.overall.tp, found.overall.fp, found.overall.fn) == (1, 0, 0)
    assert (skipped.overall.tp, skipped.overall.fp, skipped.overall.fn) == (1, 0, 0)


def test_partial_is_scored_only_on_matched_locations() -> None:
    rec = record(gold("street", "АЛПИ", partial=True), gold("street", "КРЕСНА"))

    report = evaluate(parser_returning(Location("street", "АЛПИ", partial=False)), [rec])

    assert (report.partial.correct, report.partial.total) == (0, 1)


def test_empty_gold_and_empty_prediction_is_perfect() -> None:
    report = evaluate(parser_returning(), [record()])

    assert report.overall.f1 == 1.0
    assert report.errors == []


def test_skopje_filter() -> None:
    recs = [record(gold("street", "А"), region_id=10), record(gold("street", "Б"), region_id=13)]

    assert evaluate(parser_returning(), recs, skopje_only=True).records == 1


@pytest.mark.parametrize("split", ["dev", "test"])
def test_split_is_stable_and_both_parts_are_used(split: str) -> None:
    records = load_labels()

    assert sum(r.split == split for r in records) > 20
    assert {r.split for r in records} == {"dev", "test"}
