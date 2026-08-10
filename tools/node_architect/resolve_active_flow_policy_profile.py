"""Resolve the exact active compiled Flow x Policy profile from the activation pointer.

Activation is a pointer to one immutable ``compiled_digest``. Rollback changes
the pointer to another previously registered COMPATIBLE digest; it never
rewrites Workflow, Policy or historical evidence. This module is pure and
performs no execution.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from typing import Any, Mapping

from tools.node_architect.compile_flow_policy_profile import compute_compiled_digest

ACTIVATION_PATH = "core/node-architect/flow-policy-activation-registry.json"


def resolve_active_compiled_profile(
    *, activation_registry: Mapping[str, Any], root: Path,
) -> dict[str, Any]:
    """Return the active compiled profile plus a fail-closed activation decision."""
    reasons: list[str] = []
    active = str(activation_registry.get("active_compiled_profile") or "")
    entries = [
        item for item in activation_registry.get("registered", [])
        if isinstance(item, Mapping) and item.get("compiled_digest") == active
    ]
    if len(entries) != 1:
        return {"outcome": "BLOCKED", "reason_codes": ["ACTIVE_COMPILED_PROFILE_UNREGISTERED"],
                "compiled_profile": None, "compiled_digest": active or None}
    entry = entries[0]
    if str(entry.get("status")) != "COMPATIBLE":
        reasons.append("ACTIVE_COMPILED_PROFILE_NOT_COMPATIBLE")

    path = root / str(entry.get("profile_ref") or "")
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"outcome": "BLOCKED", "reason_codes": ["ACTIVE_COMPILED_PROFILE_UNREADABLE"],
                "compiled_profile": None, "compiled_digest": active}

    if str(profile.get("compiled_digest") or "") != active:
        reasons.append("ACTIVE_COMPILED_PROFILE_DIGEST_DRIFT")
    expected = compute_compiled_digest(
        workflow_digest=str(profile.get("workflow", {}).get("workflow_digest") or ""),
        policy=profile.get("policy", {}),
        bindings=profile.get("bindings", {}),
        compiler_version=str(profile.get("compiler_version") or ""),
    )
    if expected != active:
        reasons.append("ACTIVE_COMPILED_PROFILE_RECOMPUTE_MISMATCH")
    if str(profile.get("result", {}).get("status")) != "COMPATIBLE":
        reasons.append("ACTIVE_COMPILED_PROFILE_NOT_COMPATIBLE")

    unique = list(dict.fromkeys(reasons))
    return {
        "outcome": "ACTIVE" if not unique else "BLOCKED",
        "reason_codes": unique or ["FLOW_POLICY_PROFILE_ACTIVE"],
        "compiled_profile": profile if not unique else None,
        "compiled_digest": active,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    registry = json.loads((args.root / ACTIVATION_PATH).read_text(encoding="utf-8"))
    result = resolve_active_compiled_profile(activation_registry=registry, root=args.root)
    printable = {k: v for k, v in result.items() if k != "compiled_profile"}
    print(json.dumps(printable, indent=2, sort_keys=True))
    return 0 if result["outcome"] == "ACTIVE" else 2


__all__ = ["resolve_active_compiled_profile", "ACTIVATION_PATH"]


if __name__ == "__main__":
    raise SystemExit(main())
