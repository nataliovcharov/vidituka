from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path

from vidituka.config import get_settings
from vidituka.db import make_engine, make_session_factory
from vidituka.ingest import ingest_power
from vidituka.parsing.evaluate import DEFAULT_LABELS, evaluate, format_report, load_labels
from vidituka.parsing.locations import parse_locations
from vidituka.sources import elektrodistribucija as ed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vidituka")
    commands = parser.add_subparsers(dest="command", required=True)

    fetch_power = commands.add_parser("fetch-power", help="fetch the power outages feed once")
    fetch_power.add_argument("--save", type=Path, help="save the raw response (for fixtures)")

    commands.add_parser("ingest-power", help="fetch the power feed and store it in the database")

    eval_parser = commands.add_parser("eval-parser", help="score the address parser on the labels")
    eval_parser.add_argument("--split", choices=["all", "dev", "test"], default="all")
    eval_parser.add_argument("--skopje", action="store_true", help="only Skopje records")
    eval_parser.add_argument("--errors", action="store_true", help="list every mistake")
    eval_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.command == "fetch-power":
        return _fetch_power(args.save)
    if args.command == "ingest-power":
        return _ingest_power()
    if args.command == "eval-parser":
        report = evaluate(parse_locations, load_labels(args.labels), args.split, args.skopje)
        print(format_report(report, show_errors=args.errors))
        return 0
    return 2


def _fetch_power(save_to: Path | None) -> int:
    settings = get_settings()
    with ed.build_client(settings.http_user_agent, settings.http_timeout_seconds) as client:
        response = client.get(ed.FEED_URL)
        response.raise_for_status()
        payload = response.json()

    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        save_to.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")

    result = ed.parse_feed(payload)
    skopje = [o for o in result.outages if o.is_skopje]
    print(
        f"{len(result.outages)} outages, {len(skopje)} in Skopje, {len(result.rejected)} rejected"
    )
    for outage in sorted(skopje, key=lambda o: o.start_local):
        print(f"  {outage.starts_at:%d.%m %H:%M}-{outage.ends_at:%H:%M}  {outage.place}")
    return 0


def _ingest_power() -> int:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        with ed.build_client(settings.http_user_agent, settings.http_timeout_seconds) as client:
            stats = ingest_power(make_session_factory(engine), client)
    finally:
        engine.dispose()
    print(
        f"{stats.total} outages, {stats.new} new, {stats.withdrawn} withdrawn, "
        f"{stats.rejected} rejected"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
