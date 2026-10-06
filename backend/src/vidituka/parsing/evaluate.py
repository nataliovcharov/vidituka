"""Scores the location parser against the hand-labeled set (docs/labeling-guidelines.md)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from vidituka.parsing.models import HouseNumber, Location, NumberRange

DEFAULT_LABELS = Path(__file__).resolve().parents[3] / "tests/fixtures/labels/power_v1.jsonl"
SKOPJE_REGIONS = frozenset({10, 38, 39})

Split = Literal["all", "dev", "test"]
Parser = Callable[[str, str], list[Location]]
Key = tuple[str, str]


@dataclass(frozen=True)
class GoldLocation:
    kind: str
    name: str
    partial: bool
    numbers: tuple[str, ...]
    in_: str | None
    uncertain: bool


@dataclass(frozen=True)
class LabeledRecord:
    id: str
    region_id: int
    place: str
    text: str
    locations: tuple[GoldLocation, ...]

    @property
    def split(self) -> Literal["dev", "test"]:
        # fixed by id, so a record never moves between splits
        return "test" if int(self.id[:8], 16) % 4 == 0 else "dev"


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


@dataclass
class Accuracy:
    correct: int = 0
    total: int = 0

    @property
    def value(self) -> float:
        return self.correct / self.total if self.total else 1.0


@dataclass
class RecordError:
    record: LabeledRecord
    missed: list[Key]
    extra: list[Key]
    wrong_attributes: list[str]


@dataclass
class Report:
    records: int = 0
    overall: Counts = field(default_factory=Counts)
    by_kind: dict[str, Counts] = field(default_factory=dict)
    partial: Accuracy = field(default_factory=Accuracy)
    numbers: Accuracy = field(default_factory=Accuracy)
    errors: list[RecordError] = field(default_factory=list)


def normalize_name(name: str) -> str:
    return " ".join(re.sub(r"[.,\-–—()\"„“”']", " ", name.upper()).split())


def load_labels(path: Path = DEFAULT_LABELS) -> list[LabeledRecord]:
    records = []
    for line in path.read_text("utf-8").splitlines():
        if line.strip():
            records.append(_to_record(json.loads(line)))
    return records


def evaluate(
    parse: Parser,
    records: Iterable[LabeledRecord],
    split: Split = "all",
    skopje_only: bool = False,
) -> Report:
    report = Report()
    for record in records:
        if split != "all" and record.split != split:
            continue
        if skopje_only and record.region_id not in SKOPJE_REGIONS:
            continue
        report.records += 1
        _score_record(report, record, parse(record.text, record.place))
    return report


def _score_record(report: Report, record: LabeledRecord, predicted: list[Location]) -> None:
    gold = {_key(g.kind, g.name): g for g in record.locations if not g.uncertain}
    uncertain = {_key(g.kind, g.name) for g in record.locations if g.uncertain}
    pred = {_key(p.kind, p.name): p for p in predicted}

    missed = [k for k in gold if k not in pred]
    # a prediction matching an uncertain label is neither right nor wrong
    extra = [k for k in pred if k not in gold and k not in uncertain]
    matched = [k for k in gold if k in pred]

    for key in matched:
        _counts(report, key[0]).tp += 1
    for key in missed:
        _counts(report, key[0]).fn += 1
    for key in extra:
        _counts(report, key[0]).fp += 1
    report.overall.tp += len(matched)
    report.overall.fn += len(missed)
    report.overall.fp += len(extra)

    wrong = []
    for key in matched:
        g, p = gold[key], pred[key]
        report.partial.total += 1
        if g.partial == p.partial:
            report.partial.correct += 1
        else:
            wrong.append(f"{g.name}: partial should be {g.partial}")
        if g.numbers or p.numbers:
            report.numbers.total += 1
            if list(g.numbers) == [_number_str(n) for n in p.numbers]:
                report.numbers.correct += 1
            else:
                wrong.append(f"{g.name}: numbers should be {list(g.numbers)}")

    if missed or extra or wrong:
        report.errors.append(RecordError(record, missed, extra, wrong))


def _counts(report: Report, kind: str) -> Counts:
    return report.by_kind.setdefault(kind, Counts())


def _key(kind: str, name: str) -> Key:
    return (kind, normalize_name(name))


def _number_str(n: HouseNumber) -> str:
    return f"{n.start}-{n.end}" if isinstance(n, NumberRange) else n


def _to_record(row: dict[str, Any]) -> LabeledRecord:
    locations = tuple(
        GoldLocation(
            kind=loc["kind"],
            name=loc["name"],
            partial=loc["partial"],
            numbers=tuple(_label_number(n) for n in loc.get("numbers", [])),
            in_=loc.get("in"),
            uncertain=loc.get("uncertain", False),
        )
        for loc in row["locations"]
    )
    return LabeledRecord(row["id"], row["region_id"], row["place"], row["text"], locations)


def _label_number(n: Any) -> str:
    if isinstance(n, dict):
        return f"{n['from']}-{n['to']}"
    return str(n)


def format_report(report: Report, show_errors: bool = False) -> str:
    o = report.overall
    lines = [
        f"{report.records} records",
        f"{'':14}{'precision':>10}{'recall':>8}{'F1':>7}{'tp':>5}{'fp':>5}{'fn':>5}",
    ]
    rows = [*sorted(report.by_kind.items()), ("all", o)]
    for kind, c in rows:
        lines.append(
            f"{kind:14}{c.precision:>10.3f}{c.recall:>8.3f}{c.f1:>7.3f}{c.tp:>5}{c.fp:>5}{c.fn:>5}"
        )
    lines.append(f"partial correct: {report.partial.value:.3f} of {report.partial.total}")
    lines.append(f"numbers correct: {report.numbers.value:.3f} of {report.numbers.total}")
    if show_errors:
        for e in report.errors:
            lines.append(f"\n{e.record.id}  {e.record.place}")
            lines.append(f"  {' '.join(e.record.text.split())}")
            lines += [f"  missed: {kind} {name}" for kind, name in e.missed]
            lines += [f"  extra:  {kind} {name}" for kind, name in e.extra]
            lines += [f"  wrong:  {w}" for w in e.wrong_attributes]
    return "\n".join(lines)
