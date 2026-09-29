from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from vidituka.sources import elektrodistribucija as ed

FIXTURE = Path(__file__).parent / "fixtures" / "elektrodistribucija" / "2026-09-29_sample.json"


@pytest.fixture
def payload() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(FIXTURE.read_text("utf-8"))
    return data


def test_parses_every_record_in_the_sample(payload: list[dict[str, Any]]) -> None:
    result = ed.parse_feed(payload)

    assert len(result.outages) == len(payload) == 16
    assert result.rejected == []


def test_maps_fields_and_attaches_skopje_timezone(payload: list[dict[str, Any]]) -> None:
    outage = ed.parse_feed(payload).outages[0]

    assert outage.kec_id == 38
    assert outage.place == "БУТЕЛ-СКОПЈЕ-БУТЕЛ"
    assert outage.voltage_level == "10 kV"
    assert outage.starts_at.isoformat() == "2026-09-29T07:55:36+02:00"
    assert outage.ends_at > outage.starts_at


def test_filters_skopje_by_customer_centre(payload: list[dict[str, Any]]) -> None:
    outages = ed.parse_feed(payload).outages

    skopje = [o for o in outages if o.is_skopje]

    assert len(skopje) == 14
    assert {o.place for o in outages if not o.is_skopje} == {"МАВРОВО-РОСТУШЕ", "БИТОЛА"}


def test_content_hash_is_unique_per_outage(payload: list[dict[str, Any]]) -> None:
    hashes = {o.content_hash for o in ed.parse_feed(payload).outages}

    assert len(hashes) == len(payload)


def test_content_hash_ignores_the_unstable_feed_id(payload: list[dict[str, Any]]) -> None:
    refetched = [
        {**record, "prekinID": "00000000-0000-0000-0000-000000000000"} for record in payload
    ]

    before = [o.content_hash for o in ed.parse_feed(payload).outages]
    after = [o.content_hash for o in ed.parse_feed(refetched).outages]

    assert before == after


def test_content_hash_ignores_whitespace_only_edits(payload: list[dict[str, Any]]) -> None:
    record = payload[0]
    edited = {**record, "adresa": "  " + record["adresa"].replace(" ", "   ") + "\n"}

    original_hash = ed.RawOutage.model_validate(record).content_hash
    edited_hash = ed.RawOutage.model_validate(edited).content_hash

    assert original_hash == edited_hash


def test_content_hash_changes_when_the_time_changes(payload: list[dict[str, Any]]) -> None:
    record = payload[0]
    moved = {**record, "pocetok": "2026-09-29T08:30:00"}

    assert (
        ed.RawOutage.model_validate(record).content_hash
        != ed.RawOutage.model_validate(moved).content_hash
    )


def test_bad_record_is_rejected_without_losing_the_rest(payload: list[dict[str, Any]]) -> None:
    broken = {k: v for k, v in payload[0].items() if k != "kraj"}

    result = ed.parse_feed([broken, *payload[1:]])

    assert len(result.outages) == len(payload) - 1
    assert len(result.rejected) == 1
    assert "kraj" in result.rejected[0].error


def test_payload_that_is_not_a_list_raises() -> None:
    with pytest.raises(ValueError):
        ed.parse_feed({"error": "maintenance"})


def test_fetch_sends_user_agent_and_parses_response(payload: list[dict[str, Any]]) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    with httpx.Client(
        transport=httpx.MockTransport(handler), headers={"User-Agent": "test-agent"}
    ) as client:
        result = ed.fetch_feed(client)

    assert str(seen[0].url) == ed.FEED_URL
    assert seen[0].headers["User-Agent"] == "test-agent"
    assert len(result.outages) == 16


def test_fetch_raises_on_server_error() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503))

    with httpx.Client(transport=transport) as client, pytest.raises(httpx.HTTPStatusError):
        ed.fetch_feed(client)


def test_start_is_parsed_as_naive_local_time(payload: list[dict[str, Any]]) -> None:
    outage = ed.parse_feed(payload).outages[0]

    assert outage.start_local == datetime(2026, 9, 29, 7, 55, 36)
    assert outage.start_local.tzinfo is None
