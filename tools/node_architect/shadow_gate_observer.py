#!/usr/bin/env python3
"""Observe one immutable gate event through the canonical Node Architect shadow runtime."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.node_architect.resolve_gate_node_route import _graph_revision, _node_registry_revision
from tools.node_architect.shadow_orchestrator import run_shadow_event


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _policy_revision(policy_registry: dict) -> str:
    revision = policy_registry.get("revision")
    if isinstance(revision, dict):
        return str(revision.get("revision_id", ""))
    return str(revision or "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--observed-revision", required=True)
    parser.add_argument("--observed-repository", required=True)
    parser.add_argument("--observed-branch", required=True)
    parser.add_argument("--observed-base-sha", required=True)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    event = load_json(args.event)
    registry = load_json(root / "core/node-architect/node-registry.json")
    activation = load_json(root / "core/node-architect/shadow-runtime-activation.json")
    profile = load_json(root / "core/node-architect/gate-node-route-profile.json")
    graph = load_json(root / "core/node-architect/runtime-graph-registry.json")
    policy = load_json(root / "core/node-architect/gate-applicability-policy-registry.json")

    observed_state = {
        "repository": args.observed_repository,
        "branch": args.observed_branch,
        "base_sha": args.observed_base_sha,
        "head_sha": args.observed_revision,
        "profile_revision": str(profile.get("revision", "")),
        "graph_revision": _graph_revision(graph),
        "node_registry_revision": _node_registry_revision(registry),
        "policy_revision": _policy_revision(policy),
    }
    output = run_shadow_event(
        event,
        registry,
        activation,
        observed_revision=args.observed_revision,
        observed_state=observed_state,
        profile=profile,
        graph_registry=graph,
        root=root,
        policy_registry=policy,
    )
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
