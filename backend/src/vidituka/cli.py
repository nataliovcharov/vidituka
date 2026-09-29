from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from vidituka.config import get_settings
from vidituka.sources import elektrodistribucija as ed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vidituka")
    commands = parser.add_subparsers(dest="command", required=True)

    fetch_power = commands.add_parser("fetch-power", help="fetch the power outages feed once")
    fetch_power.add_argument("--save", type=Path, help="save the raw response (for fixtures)")

    args = parser.parse_args(argv)
    if args.command == "fetch-power":
        return _fetch_power(args.save)
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


if __name__ == "__main__":
    raise SystemExit(main())
