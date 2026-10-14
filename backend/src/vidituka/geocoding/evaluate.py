"""Scores the matcher against the hand-checked matches in the labeled set.

Each labeled location has a `match`: the gazetteer feature it refers to (its OSM name and
the municipalities it may be in), or null when OpenStreetMap doesn't have it. Locations
the parser labels leave as uncertain, or whose match is uncertain, are skipped.

The matcher gets the labeled locations, not the parser's output, so a parser mistake
can't count against it.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidituka.geocoding.context import resolve_place
from vidituka.geocoding.index import Index
from vidituka.geocoding.matching import Match, match_location
from vidituka.geocoding.names import query_key
from vidituka.parsing.evaluate import DEFAULT_LABELS, SKOPJE_REGIONS, Split
from vidituka.parsing.models import Location


@dataclass(frozen=True)
class GoldMatch:
    name: str
    municipalities: frozenset[str]


@dataclass(frozen=True)
class Case:
    record_id: str
    region_id: int
    place: str
    location: Location
    gold: GoldMatch | None  # None: not in OpenStreetMap

    @property
    def split(self) -> str:
        return "test" if int(self.record_id[:8], 16) % 4 == 0 else "dev"


@dataclass
class Result:
    case: Case
    predicted: Match | None
    outcome: str  # correct, wrong, missed, false_match, correct_none


@dataclass
class MatchReport:
    results: list[Result] = field(default_factory=list)

    def count(self, outcome: str, kind: str | None = None) -> int:
        return sum(
            1
            for r in self.results
            if r.outcome == outcome and (kind is None or r.case.location.kind == kind)
        )

    def precision(self, kind: str | None = None) -> float:
        # of the matches made, how many point at the right feature
        made = sum(self.count(o, kind) for o in ("correct", "wrong", "false_match"))
        return self.count("correct", kind) / made if made else 1.0

    def recall(self, kind: str | None = None) -> float:
        # of the locations OpenStreetMap has, how many were found
        findable = sum(self.count(o, kind) for o in ("correct", "wrong", "missed"))
        return self.count("correct", kind) / findable if findable else 1.0


def load_cases(path: Path = DEFAULT_LABELS) -> list[Case]:
    cases: list[Case] = []
    for line in path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        row: dict[str, Any] = json.loads(line)
        for loc in row["locations"]:
            if loc.get("uncertain") or "match" not in loc:
                continue
            match = loc["match"]
            if match is not None and match.get("uncertain"):
                continue
            gold = (
                None
                if match is None
                else GoldMatch(match["name"], frozenset(match["municipality"]))
            )
            cases.append(
                Case(
                    row["id"],
                    row["region_id"],
                    row["place"],
                    Location(loc["kind"], loc["name"], in_=loc.get("in")),
                    gold,
                )
            )
    return cases


def evaluate_matching(
    index: Index, cases: list[Case], split: Split = "all", skopje_only: bool = False
) -> MatchReport:
    report = MatchReport()
    for case in cases:
        if split != "all" and case.split != split:
            continue
        if skopje_only and case.region_id not in SKOPJE_REGIONS:
            continue
        context = resolve_place(index, case.place)
        predicted = match_location(index, context, case.location)
        report.results.append(Result(case, predicted, _outcome(index, case.gold, predicted)))
    return report


def _outcome(index: Index, gold: GoldMatch | None, predicted: Match | None) -> str:
    if gold is None:
        return "correct_none" if predicted is None else "false_match"
    if predicted is None:
        return "missed"
    same_name = query_key(predicted.name) == query_key(gold.name)
    municipalities = {
        (index.municipality_name(e) or "").removeprefix("Општина ") for e in predicted.entries
    }
    return "correct" if same_name and municipalities & gold.municipalities else "wrong"


def format_match_report(report: MatchReport, show_errors: bool = False) -> str:
    lines = [
        f"{len(report.results)} locations, "
        f"{sum(1 for r in report.results if r.case.gold is not None)} in OpenStreetMap",
        "",
        f"{'kind':<14}{'precision':>10}{'recall':>8}{'correct':>9}{'wrong':>7}"
        f"{'missed':>8}{'false':>7}",
    ]
    for kind in (None, "street", "settlement", "neighborhood", "municipality"):
        if kind and not any(r.case.location.kind == kind for r in report.results):
            continue
        lines.append(
            f"{kind or 'all':<14}{report.precision(kind):>10.3f}{report.recall(kind):>8.3f}"
            f"{report.count('correct', kind):>9}{report.count('wrong', kind):>7}"
            f"{report.count('missed', kind):>8}{report.count('false_match', kind):>7}"
        )
    methods = Counter(
        r.predicted.method + (" (nearby)" if r.predicted.widened else "")
        for r in report.results
        if r.predicted is not None
    )
    lines += ["", "matched by: " + ", ".join(f"{m} {n}" for m, n in methods.most_common())]

    if show_errors:
        lines.append("")
        for r in report.results:
            if r.outcome in ("correct", "correct_none"):
                continue
            got = f"{r.predicted.name} ({r.predicted.method})" if r.predicted else "-"
            want = r.case.gold.name if r.case.gold else "not in OSM"
            lines.append(
                f"{r.outcome:<12} {r.case.record_id} {r.case.location.kind:<12} "
                f"{r.case.location.name!r} in {r.case.place}: got {got}, want {want}"
            )
    return "\n".join(lines)
