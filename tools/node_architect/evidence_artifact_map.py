"""Canonical gate evidence artifact map for SCRUM-189 (MAT-F2-N06).

Implements ``build_gate_evidence_artifact_map``: a deterministic, closed map
that binds each GWC gate decision to exact canonical artifact requirements and
rejects projection-only, missing, stale, or mismatched evidence.

Design decision (issue): one closed evidence map is the single source for
gate-state and transition evaluators. Evidence is classified as:

* ``CANONICAL_AUTHORITY``
* ``CANONICAL_GATE_EVIDENCE``
* ``DELIVERY_EVIDENCE``
* ``AUDIT_PROJECTION``
* ``RESUME_HINT``

Only evidence classes permitted by the gate policy may satisfy a gate. Jira,
Slack, Notion, dashboards and comments never become canonical merely because
they contain matching text. This artifact is identification-only; it never
grants authority.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence

# Closed classification + gate-requirement policy.

EVIDENCE_CLASSES = frozenset({
    "CANONICAL_AUTHORITY",
    "CANONICAL_GATE_EVIDENCE",
    "DELIVERY_EVIDENCE",
    "AUDIT_PROJECTION",
    "RESUME_HINT",
})

# Source types that may never be canonical gate evidence.
PROJECTION_SOURCE_TYPES = frozenset({
    "jira_comment",
    "slack_message",
    "notion_page",
    "dashboard",
    "chat_message",
})

# Canonical per-gate requirement template. ``target`` is the required artifact
# path convention; ``class_`` is the minimum permitted classification.
_GATE_REQUIREMENTS: tuple[dict[str, str], ...] = (
    {"gate": "G0_CONTEXT", "artifact_role": "context-snapshot", "target": ".gwc/tasks/<task-id>/g0/context-snapshot.yaml", "class_": "CANONICAL_GATE_EVIDENCE", "required": "true"},
    {"gate": "G1_ALIGNMENT", "artifact_role": "intake", "target": ".gwc/tasks/<task-id>/g1/intake/g1-intake-brief.yaml", "class_": "CANONICAL_GATE_EVIDENCE", "required": "true"},
    {"gate": "G1_ALIGNMENT", "artifact_role": "preflight", "target": ".gwc/tasks/<task-id>/g1/preflight/g1-preflight-report.yaml", "class_": "CANONICAL_GATE_EVIDENCE", "required": "true"},
    {"gate": "G1_ALIGNMENT", "artifact_role": "options", "target": ".gwc/tasks/<task-id>/g1/brainstorming/g1-options.yaml", "class_": "CANONICAL_GATE_EVIDENCE", "required": "true"},
    {"gate": "G1_ALIGNMENT", "artifact_role": "decision", "target": ".gwc/tasks/<task-id>/g1/decision/g1-decision-record.yaml", "class_": "CANONICAL_GATE_EVIDENCE", "required": "true"},
    {"gate": "G2_EXECUTION", "artifact_role": "execution-envelope", "target": ".gwc/tasks/<task-id>/g2/execution-envelope.yaml", "class_": "CANONICAL_AUTHORITY", "required": "true"},
    {"gate": "G3_PR", "artifact_role": "delivery-record", "target": ".gwc/tasks/<task-id>/g3/delivery-record.yaml", "class_": "DELIVERY_EVIDENCE", "required": "true"},
    {"gate": "G4_MERGE", "artifact_role": "merge-approval", "target": ".gwc/tasks/<task-id>/g4/merge-approval.yaml", "class_": "CANONICAL_AUTHORITY", "required": "true"},
    # G5/G6 are required only when applicable (explicit manual deploy / production
    # operation). They are recorded as requirements but do not block a map that
    # simply has not reached those gates yet.
    {"gate": "G5_DEPLOY", "artifact_role": "deployment-approval", "target": ".gwc/tasks/<task-id>/g5/deployment-approval.yaml", "class_": "CANONICAL_AUTHORITY", "required": "false"},
    {"gate": "G6_PRODUCTION_DATA", "artifact_role": "production-approval", "target": ".gwc/tasks/<task-id>/g6/production-approval.yaml", "class_": "CANONICAL_AUTHORITY", "required": "false"},
)

_REASON_PRECEDENCE: list[str] = [
    "EVIDENCE_INPUT_INVALID",
    "EVIDENCE_BINDING_MISMATCH",
    "EVIDENCE_CONFLICT",
    "EVIDENCE_PROJECTION_ONLY",
    "EVIDENCE_STALE",
    "EVIDENCE_REQUIRED_MISSING",
    "EVIDENCE_OBSERVABILITY_INCOMPLETE",
    "EVIDENCE_CI_BINDING_MISMATCH",
    "EVIDENCE_G6_NOT_APPLICABLE",
]


def _canonical_json_bytes(model: dict[str, Any]) -> bytes:
    return json.dumps(
        model, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _min_class_priority(class_name: str) -> int:
    order = ["RESUME_HINT", "AUDIT_PROJECTION", "DELIVERY_EVIDENCE", "CANONICAL_GATE_EVIDENCE", "CANONICAL_AUTHORITY"]
    return order.index(class_name) if class_name in order else len(order)


def build_gate_evidence_artifact_map(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    evidence_candidates: list[dict[str, object]],
    policy_revision: str,
    mapped_at: str | None = None,
) -> dict[str, object]:
    """Build the canonical gate evidence artifact map for a task.

    Returns a ``gate-evidence-artifact-map`` artifact. ``outcome`` is ``READY``
    only when every required canonical evidence binds with no projection-only,
    missing, or stale conflict; otherwise ``BLOCKED`` with reason codes.
    ``authority_granted`` is always ``False``.
    """
    reasons: list[str] = []

    # --- Rule 1: invalid candidate shape / binding -----------------------
    if not isinstance(task_id, str) or not task_id.strip():
        reasons.append("EVIDENCE_INPUT_INVALID")
    if not isinstance(repository, str) or "/" not in repository.strip().lstrip():
        reasons.append("EVIDENCE_INPUT_INVALID")
    if not isinstance(base_sha, str) or len(base_sha) != 40 or not all(c in "0123456789abcdef" for c in base_sha):
        reasons.append("EVIDENCE_INPUT_INVALID")
    if not isinstance(policy_revision, str) or not policy_revision.strip():
        reasons.append("EVIDENCE_INPUT_INVALID")
    if not isinstance(evidence_candidates, list):
        reasons.append("EVIDENCE_INPUT_INVALID")

    # Normalize candidates; reject malformed shapes.
    norm_candidates: list[dict[str, Any]] = []
    if isinstance(evidence_candidates, list):
        for c in evidence_candidates:
            if not isinstance(c, dict) or "evidence_key" not in c or "gate" not in c:
                reasons.append("EVIDENCE_INPUT_INVALID")
                continue
            norm_candidates.append(c)

    # --- Build canonical per-gate requirements (task-id bound) -----------
    requirements = []
    for req in _GATE_REQUIREMENTS:
        requirements.append({
            "gate": req["gate"],
            "artifact_role": req["artifact_role"],
            "target": req["target"].replace("<task-id>", task_id or "<task-id>"),
            "required": req.get("required", "true") == "true",
        })

    # G6 is required only when explicitly applicable; flag NOT_APPLICABLE when
    # no G6 candidate exists (rule 7). This is informational, not a block.
    has_g6_candidate = any(
        c.get("gate") == "G6_PRODUCTION_DATA" for c in norm_candidates
    )
    if not has_g6_candidate:
        reasons.append("EVIDENCE_G6_NOT_APPLICABLE")

    # --- Rule 2/8: conflict detection on duplicate evidence keys ----------
    seen_digests: dict[str, str] = {}
    for c in norm_candidates:
        key = c.get("evidence_key")
        dig = c.get("digest")
        if key in seen_digests and seen_digests[key] != dig:
            reasons.append("EVIDENCE_CONFLICT")
        if key is not None:
            seen_digests[key] = dig if dig is not None else ""

    # --- Build entries from candidates -----------------------------------
    entries: list[dict[str, Any]] = []
    matched_targets: set[str] = set()
    for c in norm_candidates:
        gate = c.get("gate")
        cls = c.get("classification")
        src = c.get("source_type")
        target = c.get("target")
        # Rule 3: projection-only used as canonical.
        is_projection_src = src in PROJECTION_SOURCE_TYPES
        is_canonical_class = cls in ("CANONICAL_AUTHORITY", "CANONICAL_GATE_EVIDENCE", "DELIVERY_EVIDENCE")
        entry_reasons: list[str] = []
        material = c.get("materialization_status", "UNOBSERVED")
        fresh = c.get("freshness_status", "UNOBSERVED")
        binding = c.get("binding_status", "UNOBSERVED")
        if is_projection_src and is_canonical_class:
            entry_reasons.append("EVIDENCE_PROJECTION_ONLY")
        if binding == "MISMATCHED":
            entry_reasons.append("EVIDENCE_BINDING_MISMATCH")
        if fresh == "STALE":
            entry_reasons.append("EVIDENCE_STALE")
        if material == "MISSING":
            entry_reasons.append("EVIDENCE_REQUIRED_MISSING")
        if material == "UNOBSERVED" or fresh == "UNOBSERVED" or binding == "UNOBSERVED":
            entry_reasons.append("EVIDENCE_OBSERVABILITY_INCOMPLETE")
        if gate in ("G4_MERGE", "G5_DEPLOY") and binding == "MISMATCHED" and c.get("revision") != base_sha:
            entry_reasons.append("EVIDENCE_CI_BINDING_MISMATCH")
        # Propagate every entry-level reason code to the top-level reasons so
        # the map outcome reflects per-evidence failures (binding mismatch,
        # stale, projection-only, observability incomplete, CI mismatch).
        reasons.extend(entry_reasons)
        entries.append({
            "evidence_key": c.get("evidence_key"),
            "gate": gate,
            "artifact_role": c.get("artifact_role"),
            "artifact_type": c.get("artifact_type"),
            "classification": cls,
            "required": bool(c.get("required", False)),
            "source_type": src,
            "target": target,
            "ref": c.get("ref"),
            "revision": c.get("revision"),
            "digest": dig,
            "binding_status": binding,
            "freshness_status": fresh,
            "materialization_status": material,
            "source_of_truth": bool(c.get("source_of_truth", False)) and not is_projection_src,
            "reason_codes": entry_reasons,
        })
        if target and material == "MATERIALIZED" and not entry_reasons:
            matched_targets.add(target)

    # --- Derive missing / stale / projection-only sets --------------------
    missing_required: list[str] = []
    stale_required: list[str] = []
    projection_only: list[str] = []
    for req in requirements:
        tgt = req["target"]
        if req["required"] and tgt not in matched_targets:
            missing_required.append(tgt)
    for e in entries:
        if e["freshness_status"] == "STALE":
            if e.get("target"):
                stale_required.append(e["target"])
        if "EVIDENCE_PROJECTION_ONLY" in e["reason_codes"] and e.get("target"):
            projection_only.append(e["target"])

    if missing_required:
        reasons.append("EVIDENCE_REQUIRED_MISSING")
    if stale_required:
        reasons.append("EVIDENCE_STALE")
    if projection_only:
        reasons.append("EVIDENCE_PROJECTION_ONLY")

    sorted_reasons = sorted(
        set(reasons),
        key=lambda r: _REASON_PRECEDENCE.index(r) if r in _REASON_PRECEDENCE else len(_REASON_PRECEDENCE),
    )
    # EVIDENCE_G6_NOT_APPLICABLE is informational; it must not flip a complete
    # map to BLOCKED. Outcome is BLOCKED only when a blocking reason is present.
    blocking = [r for r in sorted_reasons if r != "EVIDENCE_G6_NOT_APPLICABLE"]
    if not blocking:
        blocking = ["EVIDENCE_MAP_READY"]
    outcome = "BLOCKED" if blocking != ["EVIDENCE_MAP_READY"] else "READY"
    # Surface the resolved outcome reason in the reported reason_codes.
    reported_reasons = [r for r in sorted_reasons if r != "EVIDENCE_G6_NOT_APPLICABLE"] or ["EVIDENCE_MAP_READY"]
    if "EVIDENCE_G6_NOT_APPLICABLE" in sorted_reasons:
        reported_reasons.append("EVIDENCE_G6_NOT_APPLICABLE")

    map_model = {
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "policy_revision": policy_revision,
        "requirements": requirements,
        "entries": sorted(entries, key=lambda e: (str(e.get("gate")), str(e.get("evidence_key")))),
        "missing_required": sorted(set(missing_required)),
        "stale_required": sorted(set(stale_required)),
        "projection_only": sorted(set(projection_only)),
    }
    map_digest = "sha256:" + hashlib.sha256(_canonical_json_bytes(map_model)).hexdigest()

    return {
        "schema_version": "1.0",
        "artifact_type": "gate-evidence-artifact-map",
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "head_sha": None,
        "policy_revision": policy_revision,
        "mapped_at": mapped_at,
        "outcome": outcome,
        "reason_codes": reported_reasons,
        "entries": entries,
        "requirements": requirements,
        "missing_required": sorted(set(missing_required)),
        "stale_required": sorted(set(stale_required)),
        "projection_only": sorted(set(projection_only)),
        "map_digest": map_digest,
        "authority_granted": False,
    }
