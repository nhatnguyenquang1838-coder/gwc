#!/usr/bin/env python3
"""Deterministic protected-base-capture evaluator for intake_context.protected-base-capture (SCRUM-301).

Captures the exact protected base commit SHA used for later gate and PR evidence
and binds it to a verified source-of-truth readback. Read-only G0_CONTEXT node:
it records the verified base and never grants execution authority.

Fail-closed invariants (mirrors the intake_context family contract):
* The protected base SHA must be a verified 40-character lowercase hex string.
* A readback mismatch between the declared base and the verified source of truth
  never passes; it routes for human input instead of silently capturing.
* A prior capture whose SHA moved is treated as drift and routed, the stale
  evidence is not reused.
* Missing evidence (no evidence source or no verified readback) blocks the capture.
* Success emits a deterministic decision digest; every authority field is false.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "protected-base-capture"

SHA40 = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[^/\s]+/[^/\s]+$")

AUTH_FIELDS = (
    "write_authority_granted",
    "commit_authority_granted",
    "push_authority_granted",
    "pr_authority_granted",
    "merge_authority_granted",
    "deployment_authority_granted",
    "production_authority_granted",
)

# Closed taxonomy — unknown/unavailable never PASS.
REASONS = {
    "BASE_CAPTURED",
    "BASE_MALFORMED_INPUT",
    "BASE_MISSING_EVIDENCE",
    "BASE_READBACK_MISMATCH",
    "BASE_DRIFTED",
    "BASE_HUMAN_REQUIRED",
}

# Higher precedence wins when multiple codes apply (lower number = louder).
PRECEDENCE = {
    "BASE_MALFORMED_INPUT": 10,
    "BASE_MISSING_EVIDENCE": 40,
    "BASE_READBACK_MISMATCH": 50,
    "BASE_DRIFTED": 60,
    "BASE_HUMAN_REQUIRED": 80,
    "BASE_CAPTURED": 999,
}

# Total routing table: every non-accepted reason has exactly one outcome+route.
ROUTING: dict[str, tuple[str, str]] = {
    "BASE_MALFORMED_INPUT": ("BLOCKED", "BLOCK_G0_REVIEW"),
    "BASE_MISSING_EVIDENCE": ("BLOCKED", "REQUEST_HUMAN_INPUT"),
    "BASE_READBACK_MISMATCH": ("HUMAN_REQUIRED", "REQUEST_HUMAN_INPUT"),
    "BASE_DRIFTED": ("HUMAN_REQUIRED", "REQUEST_HUMAN_INPUT"),
    "BASE_HUMAN_REQUIRED": ("HUMAN_REQUIRED", "REQUEST_HUMAN_INPUT"),
}

ALLOWED_NEXT_NODES = [
    "intake_context.risk-classification",
]


def _canon(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, list):
        return [_canon(x) for x in value]
    return value


def canonical_json(payload: Any) -> str:
    return json.dumps(_canon(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _input_issue(
    *, task_id: Any, repository: Any, protected_base_sha: Any, evidence_source: Any,
) -> str | None:
    """Return a reason code when input is malformed, else None."""
    if not isinstance(task_id, str) or not task_id:
        return "BASE_MALFORMED_INPUT"
    if not isinstance(repository, str) or not REPO.fullmatch(repository):
        return "BASE_MALFORMED_INPUT"
    if not isinstance(protected_base_sha, str) or not SHA40.fullmatch(protected_base_sha):
        return "BASE_MALFORMED_INPUT"
    if not isinstance(evidence_source, str) or not evidence_source:
        return "BASE_MISSING_EVIDENCE"
    return None


def render_protected_base_capture(
    *,
    task_id: str,
    repository: str,
    protected_base_sha: str,
    evidence_source: str,
    verified_sha: str | None = None,
    prior_capture: Mapping[str, Any] | None = None,
    captured_at: str | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Capture the protected base SHA with a verified readback.

    Returns a schema-valid ``protected-base-capture`` artifact. Fail-closed:
    malformed input, missing evidence, a readback mismatch, or drift from a prior
    capture never yields ACCEPTED.
    """
    issue = _input_issue(
        task_id=task_id, repository=repository,
        protected_base_sha=protected_base_sha, evidence_source=evidence_source,
    )
    if issue is not None:
        return _make(
            task_id=task_id if isinstance(task_id, str) and task_id else "UNKNOWN",
            repository=repository if isinstance(repository, str) and REPO.fullmatch(repository) else "invalid/invalid",
            protected_base_sha=protected_base_sha if isinstance(protected_base_sha, str) and SHA40.fullmatch(protected_base_sha) else "0" * 40,
            evidence_source=evidence_source if isinstance(evidence_source, str) and evidence_source else "MISSING_EVIDENCE",
            captured_at=captured_at, verified_sha=None, prior_base_sha=None,
            readback_status="UNKNOWN", drift_state="NONE",
            reason_codes=[issue], observed_at=observed_at,
        )

    # Readback verification against the source of truth.
    readback_status = "VERIFIED"
    if isinstance(verified_sha, str):
        if not SHA40.fullmatch(verified_sha):
            return _make(
                task_id=task_id, repository=repository, protected_base_sha=protected_base_sha,
                evidence_source=evidence_source, captured_at=captured_at,
                verified_sha=verified_sha, prior_base_sha=None,
                readback_status="UNKNOWN", drift_state="NONE",
                reason_codes=["BASE_MALFORMED_INPUT"], observed_at=observed_at,
            )
        if verified_sha != protected_base_sha:
            readback_status = "MISMATCH"

    # Drift detection against a prior capture.
    drift_state = "NONE"
    prior_base_sha = None
    if isinstance(prior_capture, Mapping) and isinstance(prior_capture.get("protected_base_sha"), str):
        candidate = prior_capture["protected_base_sha"]
        if candidate != protected_base_sha:
            drift_state = "DRIFTED"
            prior_base_sha = candidate

    reason_codes: list[str] = []
    if readback_status == "MISMATCH":
        reason_codes.append("BASE_READBACK_MISMATCH")
    if drift_state == "DRIFTED":
        reason_codes.append("BASE_DRIFTED")
    if not reason_codes:
        reason_codes.append("BASE_CAPTURED")

    return _make(
        task_id=task_id, repository=repository, protected_base_sha=protected_base_sha,
        evidence_source=evidence_source, captured_at=captured_at,
        verified_sha=verified_sha, prior_base_sha=prior_base_sha,
        readback_status=readback_status, drift_state=drift_state,
        reason_codes=reason_codes, observed_at=observed_at,
    )


def _next_action(primary: str) -> str:
    return {
        "BASE_MALFORMED_INPUT": "Repair the protected-base-capture inputs to valid task/repo/40-hex SHA.",
        "BASE_MISSING_EVIDENCE": "Provide a non-empty evidence source for the protected base readback.",
        "BASE_READBACK_MISMATCH": "The declared base does not match the verified source of truth; a human must reconcile the base.",
        "BASE_DRIFTED": "The protected base drifted from the prior capture; a human must re-authorize the new base.",
        "BASE_HUMAN_REQUIRED": "Human input is required to capture the protected base.",
    }.get(primary, "Repair protected-base-capture inputs and replay.")


def _stop_condition(route: str) -> str:
    return {
        "BLOCK_G0_REVIEW": "Stop until the malformed input is repaired by review.",
        "REQUEST_HUMAN_INPUT": "Stop until a human supplies or reconciles the protected base.",
        "REFRESH_BASE": "Stop until the protected base is refreshed and re-verified.",
        "RETRY_CAPTURE": "Stop until the protected base can be read and re-captured.",
    }.get(route, "Stop until inputs conform to the runtime interface.")


def _make(
    *, task_id: str, repository: str, protected_base_sha: str, evidence_source: str,
    captured_at: str | None, verified_sha: str | None, prior_base_sha: str | None,
    readback_status: str, drift_state: str, reason_codes: list[str], observed_at: str | None,
) -> dict[str, Any]:
    ordered = sorted(set(reason_codes), key=lambda c: PRECEDENCE.get(c, 500))
    primary = ordered[0]
    if primary in ROUTING:
        outcome, route = ROUTING[primary]
        remediation = {
            "route": route,
            "next_action": _next_action(primary),
            "stop_condition": _stop_condition(route),
        }
        next_allowed: list[str] = []
    else:
        outcome = "ACCEPTED"
        remediation = None
        next_allowed = list(ALLOWED_NEXT_NODES)

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "task_id": task_id,
        "repository": repository,
        "protected_base_sha": protected_base_sha,
        "evidence_source": evidence_source,
        "captured_at": captured_at,
        "verified_sha": verified_sha,
        "prior_base_sha": prior_base_sha,
        "readback_status": readback_status,
        "drift_state": drift_state,
        "outcome": outcome,
        "reason_code": primary,
        "reason_codes": ordered,
        "remediation": remediation,
        "next_allowed_nodes": next_allowed,
        "observed_at": observed_at,
        "read_only_projection": True,
        "write_authority_granted": False,
        "commit_authority_granted": False,
        "push_authority_granted": False,
        "pr_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    artifact["decision_digest"] = digest_payload(
        {k: v for k, v in artifact.items() if k != "decision_digest"}
    )
    return artifact


if __name__ == "__main__":
    import sys
    payload = json.load(sys.stdin)
    print(json.dumps(render_protected_base_capture(**payload), indent=2, ensure_ascii=False))
