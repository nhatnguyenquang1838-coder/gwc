#!/usr/bin/env python3
"""Run canonical-81 E0 replay qualification on an exact repository revision."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.node_architect.shadow_81_qualification import build_qualification_report


def load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain an object")
    return payload


def live_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        node_id = item.get("node_id")
        if isinstance(node_id, str):
            ids.add(node_id)
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--revision", required=True)
    parser.add_argument("--live-ledger", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    report = build_qualification_report(
        load(root / "core/node-architect/node-registry.json"),
        load(root / "core/node-architect/shadow-runtime-activation.json"),
        revision=args.revision,
        root=root,
        live_observed_node_ids=live_ids(args.live_ledger),
    )
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
