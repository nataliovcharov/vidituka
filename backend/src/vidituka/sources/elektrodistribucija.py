"""Elektrodistribucija planned outages feed (see docs/adr/0001-data-sources.md)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

FEED_URL: Final = "https://portal-api.elektrodistribucija.mk/DSO/Prekini/ZemiPrekini"
SKOPJE_KEC_IDS: Final = frozenset({10, 38, 39})
LOCAL_TZ: Final = ZoneInfo("Europe/Skopje")

_records_adapter: Final = TypeAdapter(list[dict[str, Any]])


class RawOutage(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    # changes on every request, don't use as a key
    feed_id: str = Field(alias="prekinID")
    kec_id: int = Field(alias="kecId")
    outage_type: str = Field(alias="tipPrekin")
    place: str = Field(alias="nasMesto")
    location_text: str = Field(alias="adresa")
    start_local: datetime = Field(alias="pocetok")
    end_local: datetime = Field(alias="kraj")
    voltage_level: str = Field(alias="napNivo")

    @property
    def starts_at(self) -> datetime:
        return self.start_local.replace(tzinfo=LOCAL_TZ)

    @property
    def ends_at(self) -> datetime:
        return self.end_local.replace(tzinfo=LOCAL_TZ)

    @property
    def is_skopje(self) -> bool:
        return self.kec_id in SKOPJE_KEC_IDS

    @property
    def content_hash(self) -> str:
        parts = (
            str(self.kec_id),
            _collapse_whitespace(self.place),
            _collapse_whitespace(self.location_text),
            self.start_local.isoformat(),
            self.end_local.isoformat(),
        )
        return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


@dataclass(frozen=True)
class RejectedRecord:
    record: dict[str, Any]
    error: str


@dataclass(frozen=True)
class FeedResult:
    outages: list[RawOutage] = field(default_factory=list)
    rejected: list[RejectedRecord] = field(default_factory=list)


def parse_feed(payload: object) -> FeedResult:
    # skip bad records, but fail if the whole shape changed
    outages: list[RawOutage] = []
    rejected: list[RejectedRecord] = []
    for record in _records_adapter.validate_python(payload):
        try:
            outages.append(RawOutage.model_validate(record))
        except ValidationError as exc:
            rejected.append(RejectedRecord(record=record, error=str(exc)))
    return FeedResult(outages=outages, rejected=rejected)


def fetch_feed(client: httpx.Client) -> FeedResult:
    response = client.get(FEED_URL)
    response.raise_for_status()
    return parse_feed(response.json())


def build_client(user_agent: str, timeout_seconds: float) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        timeout=timeout_seconds,
        follow_redirects=True,
    )


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())
