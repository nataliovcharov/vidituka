from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["street", "settlement", "neighborhood", "municipality"]


@dataclass(frozen=True)
class NumberRange:
    start: str
    end: str


HouseNumber = str | NumberRange


@dataclass
class Location:
    kind: Kind
    name: str
    partial: bool = False
    numbers: list[HouseNumber] = field(default_factory=list)
    in_: str | None = None
