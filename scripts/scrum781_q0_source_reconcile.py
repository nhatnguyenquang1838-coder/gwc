#!/usr/bin/env python3
"""Read-only source binding precheck for the active SCRUM-781 Q0 run.

Protected-main divergence is information, not a Universal v2 authority source.
This does not mint a gate receipt, validate runtime admission or replan.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUN = "scrum781-q0-fresh-20261010-r1"
BRANCH = "fix/SCRUM-781-q0-fresh-20261010-r1"
EPOCH = "UNIVERSAL_V2_DEVELOPMENT"
PLAN = "core/node-architect/scrum781-q0-fresh-execution-plan-r2.json"
FIXTURE = ".gwc/tasks/SCRUM-781/fixtures/q0-c91-e52-reconstructed-v1.json"
RUNBOOK = "core/runbooks/Q0_LIVE_QUALIFICATION_RUNBOOK_v1.0.md"
POLICY = "AGENTS.md"
OVERRIDE = "## UNIVERSAL_V2_DEVELOPMENT override — SCRUM-781 Q0 development lane"


class SourceBindingError(ValueError):
    """A source-bound Q0 precondition is absent or drifted."""


def sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _read(root: Path, path: str) -> bytes:
    try:
        return (root / path).read_bytes()
    except OSError as exc:
        raise SourceBindingError("Q0_REQUIRED_SOURCE_MISSING:" + path) from exc


def reconcile(q0_root: Path = ROOT, protected_main_root: Path | None = None) -> dict[str, Any]:
    """Check Q0 branch-scoped binding, do not infer any native GWC gate effect."""
    plan_raw = _read(q0_root, PLAN)
    fixture_raw = _read(q0_root, FIXTURE)
    policy_raw = _read(q0_root, POLICY)
    runbook_raw = _read(q0_root, RUNBOOK)
    try:
        plan = json.loads(plan_raw)
        fixture = json.loads(fixture_raw)
        policy_text = policy_raw.decode("utf-8")
        runbook_text = runbook_raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceBindingError("Q0_SOURCE_FORMAT_INVALID") from exc

    if not all((
        plan.get("run_id") == RUN,
        plan.get("parent_task") == "SCRUM-781",
        plan.get("branch") == BRANCH,
        plan.get("runtime_epoch") == EPOCH,
        plan.get("current_gate") == "UR.G2",
        plan.get("contract_mode") == "EXECUTE",
        plan.get("scope", {}).get("max_children") == 0,
        plan.get("scope", {}).get("max_parallel") == 1,
    )):
        raise SourceBindingError("Q0_RUNTIMEPLAN_IDENTITY_INVALID")
    canonical = str(plan.get("authority_basis", {}).get("canonical_source", ""))
    if not all((
        "AGENTS.md#UNIVERSAL_V2_DEVELOPMENT" in canonical,
        OVERRIDE in policy_text,
        "One Q0 run -> one development branch" in policy_text,
        "## UNIVERSAL_V2_DEVELOPMENT lane addendum" in runbook_text,
    )):
        raise SourceBindingError("Q0_BRANCH_POLICY_BINDING_INVALID")

    source = fixture.get("source_binding", {})
    if not all((
        fixture.get("run_id") == RUN,
        fixture.get("runtime_epoch") == EPOCH,
        fixture.get("gate") == "UR.G2",
        source.get("repository") == "nhatnguyenquang1838-coder/gwc",
        source.get("branch") == BRANCH,
        source.get("runtimeplan_path") == PLAN,
    )):
        raise SourceBindingError("Q0_FIXTURE_BINDING_INVALID")
    plan_digest = sha256(plan_raw)
    if source.get("runtimeplan_sha256") != plan_digest:
        raise SourceBindingError("Q0_IMMUTABLE_PLAN_DIGEST_DRIFT")
    if (fixture.get("incident", {}).get("provenance_class")
            != "RECONSTRUCTED_SOURCE_BOUND"):
        raise SourceBindingError("Q0_RECONSTRUCTED_PROVENANCE_INVALID")

    base_comparison: dict[str, Any] = {"status": "NOT_CHECKED"}
    if protected_main_root is not None:
        base_comparison = {"status": "MATCH", "nonblocking": True, "files": {}}
        for filename, bound_raw in ((POLICY, policy_raw), (RUNBOOK, runbook_raw)):
            base_raw = _read(protected_main_root, filename)
            changed = base_raw != bound_raw
            base_comparison["files"][filename] = {
                "different": changed, "main_digest": sha256(base_raw),
                "q0_digest": sha256(bound_raw),
            }
            if changed:
                base_comparison["status"] = "PROTECTED_MAIN_DIVERGENCE_NONBLOCKING"

    return {
        "schema_id": "gwc.q0.source-binding-reconciliation.v1",
        "run_id": RUN, "branch": BRANCH, "gate": "UR.G2",
        "binding": "Q0_SOURCE_BOUND",
        "current_runtimeplan_sha256": plan_digest,
        "replan_required": False,
        "fixture_digest": sha256(fixture_raw),
        "fixture_class": "RECONSTRUCTED_SOURCE_BOUND",
        "q0_policy_sha256": sha256(policy_raw),
        "q0_runbook_sha256": sha256(runbook_raw),
        "protected_main": base_comparison,
        "scope": "P1_SOURCE_PRECHECK_ONLY",
        "q0_l3_qualified": False,
        "native_gate_receipt": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--q0-root", type=Path, default=ROOT)
    parser.add_argument("--protected-main-root", type=Path, default=None)
    args = parser.parse_args()
    try:
        result = reconcile(args.q0_root, args.protected_main_root)
    except SourceBindingError as exc:
        print(json.dumps({
            "binding": "BLOCKED_AFFECTED_SOURCE_PRECHECK_ONLY",
            "reason_code": str(exc),
            "global_controller_stop": False,
            "native_gate_receipt": None,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
