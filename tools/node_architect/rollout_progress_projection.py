#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def attach_digest(decision: dict[str, Any]) -> dict[str, Any]:
    decision["decision_digest"] = digest_payload(
        {key: value for key, value in decision.items() if key != "decision_digest"}
    )
    return decision


def _valid_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(ch in "0123456789abcdef" for ch in value[7:])
    )


def _valid_non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_family(item: object) -> bool:
    return (
        isinstance(item, dict)
        and _valid_non_empty(item.get("family"))
        and isinstance(item.get("total_nodes"), int)
        and not isinstance(item.get("total_nodes"), bool)
        and isinstance(item.get("completed_nodes"), int)
        and not isinstance(item.get("completed_nodes"), bool)
        and 0 <= item["completed_nodes"] <= item["total_nodes"]
    )


def _valid_gate(item: object) -> bool:
    return (
        isinstance(item, dict)
        and _valid_non_empty(item.get("gate"))
        and item.get("status") in {"PASS", "READY", "SUCCESS", "NOT_APPLICABLE", "PENDING", "BLOCKED"}
        and _valid_sha(item.get("evidence_sha"))
    )


def decide_rollout_progress_projection(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    evidence_revision: str,
    expected_revision: str,
    family_progress: list[dict[str, Any]],
    gate_evidence: list[dict[str, Any]],
    expected_total_families: int = 9,
    expected_total_nodes: int = 81,
    audit_ready_required: bool = True,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Project rollout progress from canonical evidence without granting authority."""
    projection_status = "BLOCKED"
    reason_code = "ROLLOUT_PROGRESS_NOT_READY"

    identity_invalid = not all(_valid_non_empty(value) for value in (task_id, repository, branch))
    sha_invalid = not (_valid_sha(base_sha) and _valid_sha(head_sha))
    revision_invalid = not (_valid_digest(evidence_revision) and _valid_digest(expected_revision))
    limits_invalid = not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in (expected_total_families, expected_total_nodes))
    family_invalid = not (isinstance(family_progress, list) and all(_valid_family(item) for item in family_progress))
    gate_invalid = not (isinstance(gate_evidence, list) and all(_valid_gate(item) for item in gate_evidence))

    completed_nodes = 0 if family_invalid else sum(item["completed_nodes"] for item in family_progress)
    total_nodes = 0 if family_invalid else sum(item["total_nodes"] for item in family_progress)
    family_count = 0 if family_invalid else len({item["family"] for item in family_progress})
    incomplete_families = [] if family_invalid else sorted(item["family"] for item in family_progress if item["completed_nodes"] != item["total_nodes"])
    blocked_gates = [] if gate_invalid else sorted(item["gate"] for item in gate_evidence if item["status"] == "BLOCKED")
    pending_gates = [] if gate_invalid else sorted(item["gate"] for item in gate_evidence if item["status"] == "PENDING")
    passing_gates = [] if gate_invalid else sorted(item["gate"] for item in gate_evidence if item["status"] in {"PASS", "READY", "SUCCESS", "NOT_APPLICABLE"})

    if identity_invalid:
        reason_code = "REQUIRED_IDENTITY_MISSING"
    elif sha_invalid:
        reason_code = "INVALID_OR_MISSING_SHA_BINDING"
    elif revision_invalid:
        reason_code = "INVALID_EVIDENCE_REVISION"
    elif evidence_revision != expected_revision:
        reason_code = "EVIDENCE_REVISION_MISMATCH"
    elif limits_invalid:
        reason_code = "INVALID_ROLLOUT_LIMITS"
    elif family_invalid:
        reason_code = "INVALID_FAMILY_PROGRESS_INPUT"
    elif gate_invalid:
        reason_code = "INVALID_GATE_EVIDENCE_INPUT"
    elif family_count != expected_total_families:
        reason_code = "FAMILY_COUNT_MISMATCH"
    elif total_nodes != expected_total_nodes:
        reason_code = "TOTAL_NODE_COUNT_MISMATCH"
    elif completed_nodes > expected_total_nodes:
        reason_code = "COMPLETED_NODE_COUNT_OVERFLOW"
    elif blocked_gates:
        reason_code = "BLOCKED_GATE_PRESENT"
    elif pending_gates:
        reason_code = "ROLLOUT_GATES_PENDING"
        projection_status = "IN_PROGRESS"
    elif incomplete_families:
        reason_code = "ROLLOUT_NODES_INCOMPLETE"
        projection_status = "IN_PROGRESS"
    else:
        reason_code = "ROLLOUT_READY_FOR_INDEPENDENT_AUDIT_HANDOFF" if audit_ready_required else "ROLLOUT_COMPLETE"
        projection_status = "READY_FOR_AUDIT_HANDOFF"

    progress_percent = round((completed_nodes / expected_total_nodes) * 100, 2) if expected_total_nodes else 0.0
    decision = {
        "schema_version": "1.0",
        "artifact_type": "rollout-progress-projection-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "evidence_revision": evidence_revision,
        "expected_revision": expected_revision,
        "expected_total_families": expected_total_families,
        "expected_total_nodes": expected_total_nodes,
        "observed_family_count": family_count,
        "observed_total_nodes": total_nodes,
        "completed_nodes": completed_nodes,
        "progress_percent": progress_percent,
        "incomplete_families": incomplete_families,
        "pending_gates": pending_gates,
        "blocked_gates": blocked_gates,
        "passing_gates": passing_gates,
        "projection_status": projection_status,
        "reason_code": reason_code,
        "read_only_projection": True,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "audit_authority_granted": False,
        "scale_authority_granted": False,
        "observed_at": observed_at or now_utc(),
    }
    return attach_digest(decision)
