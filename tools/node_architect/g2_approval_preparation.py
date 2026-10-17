#!/usr/bin/env python3
"""SCRUM-844: real-source G1 -> G2 human approval preparation.

The full gate-state resolver *correctly* reports G2 BLOCKED while the G2
execution envelope is absent. That fact cannot grant G2 effect authority, but
must not prevent a bounded, read-only REQUEST for future G2 authority.

This adapter consumes real, schema-valid canonical producers; it does not
invent a PASS gate projection or alter the existing execution authorization.
"""
from __future__ import annotations

import argparse
import json
import re
from typing import Any, Mapping

from tools.node_architect.approval_token_generation import generate_approval_request
from tools.node_architect.authority_boundary_check import (
    ACTION_TO_MINIMUM_GATE,
    _finish,
    check_authority_boundary,
)
from tools.node_architect.g2_execution_envelope_render import render_g2_execution_envelope
from tools.node_architect.gate_state_resolution import (
    _entry_policy_valid,
    _map_valid,
    resolve_gate_state,
)

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_EARLY = ("G0_CONTEXT", "G1_ALIGNMENT")
_ALLOWED_MISSING = ("G2_EXECUTION", "G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA")
_RISK_PRODUCER_KEYS = frozenset(
    ("request_intake", "source_resolution", "repo_identity", "protected_base_capture")
)
_AUTHORITY_FLAGS = (
    "write_authority_granted", "commit_authority_granted",
    "push_authority_granted", "pr_authority_granted", "merge_authority_granted",
    "deployment_authority_granted", "production_authority_granted",
)


class G2PreparationBlocked(ValueError):
    """No fabricated approval request may escape a failed precondition."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise G2PreparationBlocked(code)


def prepare_g2_approval(
    *,
    task_id: str,
    repository: str,
    current_base_sha: str,
    scope_identity: dict[str, Any],
    evidence_map: dict[str, Any],
    transition_map: dict[str, Any],
    risk_profile: dict[str, Any],
    requested_action: str,
    actor_target: dict[str, str],
    issued_at: str,
    expires_at: str,
    event_id_or_idempotency_key: str,
    checkpoint_id: str,
    bounded_read_paths: list[str] | None = None,
    gate_policy: dict[str, Any] | None = None,
    prior_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a human approval request + NON-EXECUTABLE pending envelope.

    This is approval *preparation*, not activation and not authorization for a
    repository write. After actual approval the existing native gate/authority
    and envelope validators remain the only path to protected effects.
    """
    _require(isinstance(scope_identity, dict) and isinstance(evidence_map, dict),
             "G2_PREP_INPUT_INVALID")
    _require(isinstance(risk_profile, dict) and isinstance(transition_map, dict),
             "G2_PREP_INPUT_INVALID")
    _require(isinstance(actor_target, dict) and bool(actor_target.get("id")),
             "G2_PREP_ACTOR_MISSING")
    _require(bool(checkpoint_id) and bool(event_id_or_idempotency_key),
             "G2_PREP_EVENT_MISSING")
    _require(ACTION_TO_MINIMUM_GATE.get(requested_action) == "G2_EXECUTION",
             "G2_PREP_ACTION_NOT_G2")

    # The source-bound scope hash is validated inside resolve_gate_state; this
    # check also pins risk identity and prevents a foreign task/repository/base.
    _require(
        scope_identity.get("outcome") == "READY"
        and scope_identity.get("task_id") == task_id
        and scope_identity.get("repository") == repository
        and scope_identity.get("base_sha") == current_base_sha
        and scope_identity.get("risk_class") == risk_profile.get("risk_level")
        and bool(scope_identity.get("working_branch"))
        and scope_identity.get("head_sha") == current_base_sha
        and _DIGEST.fullmatch(str(scope_identity.get("scope_hash"))) is not None,
        "G2_PREP_SCOPE_BINDING_INVALID",
    )
    _require(
        risk_profile.get("artifact_type") == "risk-profile"
        and risk_profile.get("task_id") == task_id
        and risk_profile.get("repository") == repository
        and risk_profile.get("base_sha") == current_base_sha
        and risk_profile.get("outcome") == "ACCEPTED"
        and risk_profile.get("risk_level") == "R2"
        and risk_profile.get("required_gate") == "G2_HUMAN_DIRECTION"
        and _DIGEST.fullmatch(str(risk_profile.get("decision_digest"))) is not None
        and isinstance(risk_profile.get("source_bindings"), dict)
        and _RISK_PRODUCER_KEYS <= set(risk_profile["source_bindings"])
        and all(risk_profile.get(k) is False for k in _AUTHORITY_FLAGS),
        "G2_PREP_RISK_NOT_ACCEPTED",
    )
    _require(_map_valid(evidence_map, task_id), "G2_PREP_EVIDENCE_MAP_INVALID")
    _require(
        evidence_map.get("repository") == repository
        and evidence_map.get("base_sha") == current_base_sha
        and evidence_map.get("outcome") == "BLOCKED"
        and not set(evidence_map.get("reason_codes", [])) - {
            "EVIDENCE_REQUIRED_MISSING", "EVIDENCE_G6_NOT_APPLICABLE"
        },
        "G2_PREP_EVIDENCE_CONFLICT",
    )
    # Check real, typed, source-of-truth G0/G1 evidence. An accepted G1
    # projection or a hand-edited status cannot satisfy these conditions.
    required_early = {
        req["target"] for req in evidence_map["requirements"]
        if req["gate"] in _EARLY and req["required"]
    }
    validated_early = {
        entry["target"] for entry in evidence_map["entries"]
        if entry["gate"] in _EARLY
        and _entry_policy_valid(entry, evidence_map=evidence_map,
                                scope_identity=scope_identity)
    }
    _require(bool(required_early) and required_early == validated_early,
             "G2_PREP_G01_SOURCE_MISSING")
    early_targets = {req["target"] for req in evidence_map["requirements"]
                     if req["gate"] in _EARLY}
    _require(
        not early_targets.intersection(
            evidence_map.get("missing_required", []) +
            evidence_map.get("stale_required", []) +
            evidence_map.get("projection_only", [])
        )
        and not evidence_map.get("stale_required")
        and not evidence_map.get("projection_only"),
        "G2_PREP_EARLY_EVIDENCE_STALE",
    )
    # Full producer still lists future delivery/merge evidence. It must NOT
    # list an unknown requirement or any pre-G2 artifact as missing.
    allowable_future = {
        req["target"] for req in evidence_map["requirements"]
        if req["gate"] in _ALLOWED_MISSING
    }
    missing = set(evidence_map.get("missing_required", []))
    envelope_target = f".gwc/tasks/{task_id}/g2/execution-envelope.yaml"
    _require(envelope_target in missing and missing <= allowable_future,
             "G2_PREP_ENVELOPE_ABSENCE_NOT_PROVEN")

    state = resolve_gate_state(
        task_id=task_id, repository=repository, current_base_sha=current_base_sha,
        scope_identity=scope_identity, evidence_map=evidence_map,
        transition_map=transition_map, task_projection=None,
        event_id_or_idempotency_key=event_id_or_idempotency_key,
        prior_resolution=prior_resolution,
    )
    evaluations = {x["gate"]: x["status"] for x in state.get("gate_evaluations", [])}
    _require(
        all(evaluations.get(g) == "PASS" for g in _EARLY)
        and state.get("current_gate") == "G2_EXECUTION"
        and state.get("gate_status") == "BLOCKED"
        and state.get("last_passed_gate") == "G1_ALIGNMENT"
        and state.get("replay_status") != "REPLAY_CONFLICT"
        and state.get("drift_decision", {}).get("status") == "NO_DRIFT"
        and set(state.get("reason_codes", [])) <= {
            "GATE_STATE_REQUIRED_EVIDENCE_MISSING", "GATE_STATE_G6_NOT_APPLICABLE"
        }
        and "GATE_STATE_REQUIRED_EVIDENCE_MISSING" in state.get("reason_codes", []),
        "G2_PREP_CANONICAL_G01_NOT_PASS",
    )

    # Verify that ordinary execution remains BLOCKED *solely* because the
    # future G2 envelope is absent, and not because of a forbidden action,
    # foreign scope, stale evidence, policy mismatch, or replay conflict.
    denied = check_authority_boundary(
        task_id=task_id, repository=repository,
        requested_action=requested_action, gate_state_resolution=state,
        scope_identity=scope_identity,
        gate_policy=gate_policy or {"action_map": ACTION_TO_MINIMUM_GATE},
        risk_class="R2", production_scope_applicable=False,
        manual_g5_action=False, event_id_or_idempotency_key=event_id_or_idempotency_key,
        envelope_expires_at=expires_at, evaluated_at=issued_at,
    )
    _require(denied.get("decision") == "BLOCK"
             and denied.get("reason_codes") == ["AUTHORITY_GATE_INSUFFICIENT"]
             and denied.get("prohibited") is False,
             "G2_PREP_PRECHECK_REJECTED")

    # SOURCE-DEFINED canonical PREPARATION decision: never replace the actual
    # G2 BLOCKED gate state. No authority flag is set, and the normal execution
    # boundary will still reject repository mutations until real approval.
    preparation = dict(denied)
    preparation.update(
        decision="REQUIRE_APPROVAL",
        approval_required=True,
        required_approval_gate="G2_EXECUTION",
        next_authorized_preparation=["prepare_g2_approval_request"],
    )
    preparation = _finish(preparation, ["AUTHORITY_APPROVAL_PREPARATION_REQUIRED"])
    _require(all(preparation.get(k) is False for k in (
        "authority_granted", "execution_authority_granted",
        "write_authority_granted", "pr_authority_granted",
        "merge_authority_granted", "deployment_authority_granted",
        "production_authority_granted"
    )), "G2_PREP_FORGED_AUTHORITY")

    request = generate_approval_request(
        task_id=task_id, repository=repository, gate="G2_EXECUTION",
        action=requested_action,
        scope_identity={
            "base_sha": current_base_sha, "head_sha": scope_identity["head_sha"],
            "branch": scope_identity["working_branch"],
            "scope_hash": scope_identity["scope_hash"],
        },
        authority_boundary_decision=preparation, actor_target=actor_target,
        issued_at=issued_at, expires_at=expires_at,
    )
    pending = render_g2_execution_envelope(
        task_id=task_id, repository=repository,
        base_ref=scope_identity["base_ref"], base_sha=current_base_sha,
        risk_profile={"risk_class": "R2",
                      "risk_digest": risk_profile["decision_digest"]},
        bounded_read_scope={"paths": bounded_read_paths or []},
        bounded_write_scope={
            "working_branch": scope_identity["working_branch"],
            "paths": scope_identity["authorized_paths"],
            "authorized_actions": scope_identity["authorized_actions"],
        },
        scope_identity=scope_identity, gate_state_resolution=state,
        authority_boundary_decision=preparation, evidence_map=evidence_map,
        approval_request=request, approval_validation=None,
        checkpoint={"checkpoint_id": checkpoint_id},
        rendered_at=issued_at,
    )
    _require(
        pending.get("activation_state") == "AWAITING_APPROVAL"
        and pending.get("execution_started") is False
        and pending.get("approval_validation_ref") is None,
        "G2_PREP_PENDING_ENVELOPE_UNSAFE",
    )
    return {
        "schema_version": "1.0", "artifact_type": "g2-approval-preparation",
        "task_id": task_id, "repository": repository,
        "source_base_sha": current_base_sha,
        "scope_hash": scope_identity["scope_hash"],
        "risk_digest": risk_profile["decision_digest"],
        "gate_state_resolution": state,
        "authority_boundary_decision": preparation,
        "approval_request": request,
        "pending_g2_envelope": pending,
        "status": "AWAITING_HUMAN_APPROVAL",
        "authority_granted": False,
        "execution_authority_granted": False,
        "write_authority_granted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to canonical JSON producer inputs")
    args = parser.parse_args()
    try:
        with open(args.input, encoding="utf-8") as handle:
            inputs = json.load(handle)
        result = prepare_g2_approval(**inputs)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc),
                          "authority_granted": False}))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
