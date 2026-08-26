#!/usr/bin/env python3
"""Convert one shadow observer output into append-only per-node telemetry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tools.node_architect.shadow_telemetry import append_telemetry, build_telemetry_event


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def emit_output_telemetry(event: dict[str, Any], output: dict[str, Any], ledger: Path) -> dict[str, Any]:
    results = output.get("results")
    if not isinstance(results, list):
        raise ValueError("SHADOW_OUTPUT_RESULTS_NOT_LIST")
    route_pack = output.get("route_pack")
    if results and (not isinstance(route_pack, str) or not route_pack):
        raise ValueError("SHADOW_OUTPUT_ROUTE_PACK_REQUIRED")
    graph_revision = str(event.get("route_graph_revision") or f"repo-bound:{event.get('exact_revision', '')}")
    appended = 0
    duplicates = 0
    digests: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("SHADOW_OUTPUT_RESULT_NOT_OBJECT")
        telemetry = build_telemetry_event(result, route_pack=route_pack, graph_revision=graph_revision)
        digests.append(telemetry["event_digest"])
        if append_telemetry(ledger, telemetry):
            appended += 1
        else:
            duplicates += 1
    return {"appended": appended, "duplicates": duplicates, "event_digests": digests}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = emit_output_telemetry(load_json(args.event), load_json(args.output), args.ledger)
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
