#!/usr/bin/env python3
"""Observe one immutable gate event through the Node Architect shadow runtime."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.node_architect.shadow_orchestrator import run_shadow_event


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--observed-revision", required=True)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    event = load_json(args.event)
    registry = load_json(root / "core/node-architect/node-registry.json")
    activation = load_json(root / "core/node-architect/shadow-runtime-activation.json")
    output = run_shadow_event(event, registry, activation, observed_revision=args.observed_revision)
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
