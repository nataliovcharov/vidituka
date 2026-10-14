from __future__ import annotations

import json
from pathlib import Path

from vidituka.geocoding.evaluate import evaluate_matching, load_cases
from vidituka.geocoding.index import DEFAULT_SNAPSHOT, Snapshot, build_index

from .test_matching import ISTOK, make_index


def write_labels(path: Path, locations: list[dict[str, object]]) -> Path:
    row = {"id": "00000001", "region_id": 10, "place": "ИСТОК", "text": "", "locations": locations}
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", "utf-8")
    return path


def street(name: str, match: object = "absent") -> dict[str, object]:
    location: dict[str, object] = {"kind": "street", "name": name}
    if match != "absent":
        location["match"] = match
    return location


def in_istok(name: str) -> dict[str, object]:
    return {"name": name, "municipality": ["Исток"]}


def test_outcomes(tmp_path: Path) -> None:
    index = make_index(streets=[(100, "Јајце", ISTOK, None), (101, "Алпи", ISTOK, None)])
    labels = write_labels(
        tmp_path / "labels.jsonl",
        [
            {
                "kind": "street",
                "name": "ЈАЈЦЕ",
                "match": {"name": "Јајце", "municipality": ["Исток"]},
            },
            {"kind": "street", "name": "АЛПИ", "match": None},
            {
                "kind": "street",
                "name": "АВРОРА",
                "match": {"name": "Аврора", "municipality": ["Исток"]},
            },
            {"kind": "street", "name": "КРЕСНА", "match": None},
            # skipped: no match label, or an uncertain one
            {"kind": "street", "name": "ЈАЈЦЕ"},
            {"kind": "street", "name": "ЈАЈЦЕ", "match": {"uncertain": True}},
        ],
    )

    report = evaluate_matching(index, load_cases(labels))

    assert [r.outcome for r in report.results] == [
        "correct",
        "false_match",
        "missed",
        "correct_none",
    ]
    assert report.precision() == 0.5
    assert report.recall() == 0.5


def test_matcher_does_not_drop_below_baseline() -> None:
    # raise these when matching improves; never lower them to make a change pass.
    # A wrong place on the map is worse than none, so precision has the higher bar.
    report = evaluate_matching(build_index(Snapshot.load(DEFAULT_SNAPSHOT)), load_cases())

    assert report.precision() >= 0.99
    assert report.recall() >= 0.95
