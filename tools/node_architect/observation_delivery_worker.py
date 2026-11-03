#!/usr/bin/env python3
"""Dedicated non-authorizing GWC -> DWO observation outbox worker."""
from __future__ import annotations

import argparse
import json
import time

from .observation_publisher import drain_observation_outbox_from_env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Drain once and exit.")
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    parser.add_argument("--max-items", type=int, default=32)
    args = parser.parse_args(argv)
    if args.interval_seconds <= 0 or args.max_items < 1:
        raise SystemExit("interval/max-items must be positive")

    while True:
        result = drain_observation_outbox_from_env(max_items=args.max_items)
        print(json.dumps(result, sort_keys=True))
        if args.once:
            return 0 if result.get("status") not in {"DEGRADED"} else 1
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
