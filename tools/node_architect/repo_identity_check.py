#!/usr/bin/env python3
"""Deterministic repository-identity evaluator for intake_context.repo-identity-check (SCRUM-300).

Verifies repository identity, default branch, protected branch, and execution
mode against verified source evidence. Read-only G0_CONTEXT node: it records
provenance only and never grants execution authority.

Fail-closed invariants (mirrors the intake_context family contract):
* Verified source identity is the single source of truth; observed identity is
  compared against it deterministically, never inferred from local path/name.
* Any mismatch (owner, name, default branch, protected branch, execution mode)
  must cause fail-closed rejection with an explicit reason code.
* Missing or ambiguous evidence must not PASS; it routes to BLOCKED / HUMAN_REQUIRED.
* Success emits a deterministic identity digest; every authority field is
  fixed to false.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "repo-identity"

SHA40 = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[^/\s]+/[^/\s]+$")
EXECUTION_MODES = {"MAIN_GOVERNANCE", "PREPROD_AUTONOMOUS", "UNKNOWN"}

AUTH_FIELDS = (
    "write_authority_granted",
    "commit_authority_granted",
    "push_authority_granted",
    "pr_authority_granted",
    "merge_authority_granted",
    "deployment_authority_granted",
    "production_authority_granted",
)

REASON_CODES = {
    "ACCEPTED",
    "REPO_MISMATCH",
    "DEFAULT_BRANCH_MISMATCH",
    "PROTECTED_BRANCH_MISMATCH",
    "EXECUTION_MODE_MISMATCH",
    "EVIDENCE_GAP",
    "MALFORMED_INPUT",
}


def _identity_keys() -> tuple[str, ...]:
    return ("owner", "name", "default_branch", "protected_branch", "execution_mode")


def _is_valid_identity(ident: Any) -> bool:
    if not isinstance(ident, dict):
        return False
    if missing := set(_identity_keys()) - set(ident):
        return False
    if not isinstance(ident["owner"], str) or not ident["owner"].strip():
        return False
    if not isinstance(ident["name"], str) or not ident["name"].strip():
        return False
    if not isinstance(ident["default_branch"], str) or not ident["default_branch"].strip():
        return False
    if not isinstance(ident["protected_branch"], str) or not ident["protected_branch"].strip():
        return False
    if ident["execution_mode"] not in EXECUTION_MODES:
        return False
    return True


def _digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_repo_identity_check(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    observed_identity: Mapping[str, Any],
    verified_source: Mapping[str, Any],
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Render a deterministic repository-identity check record.

    Args:
        task_id: The SCRUM task id (e.g. "SCRUM-300").
        repository: "<owner>/<name>" of the task repository.
        base_sha: 40-hex protected-base SHA the check is bound to.
        observed_identity: identity observed from repository/runtime evidence.
        verified_source: verified canonical identity the observed must match.
        observed_at: optional ISO-8601 timestamp of the observation.

    Returns:
        A schema-valid repo-identity record with every authority field false.
    """
    reason_codes: list[str] = []
    outcome = "ACCEPTED"
    identity_match = False
    missing_fields: list[str] = []

    if not isinstance(task_id, str) or not task_id.strip():
        reason_codes.append("MALFORMED_INPUT")
    if not isinstance(repository, str) or not REPO.fullmatch(repository or ""):
        reason_codes.append("MALFORMED_INPUT")
    if not isinstance(base_sha, str) or not SHA40.fullmatch(base_sha or ""):
        reason_codes.append("MALFORMED_INPUT")

    if not _is_valid_identity(observed_identity):
        reason_codes.append("EVIDENCE_GAP")
    if not _is_valid_identity(verified_source):
        reason_codes.append("EVIDENCE_GAP")

    # Deterministic mismatch detection only when both identities are well-formed.
    if not reason_codes:
        observed = {k: observed_identity[k] for k in _identity_keys()}
        verified = {k: verified_source[k] for k in _identity_keys()}
        mismatches: list[str] = []
        if (observed["owner"], observed["name"]) != (verified["owner"], verified["name"]):
            mismatches.append("REPO_MISMATCH")
        if observed["default_branch"] != verified["default_branch"]:
            mismatches.append("DEFAULT_BRANCH_MISMATCH")
        if observed["protected_branch"] != verified["protected_branch"]:
            mismatches.append("PROTECTED_BRANCH_MISMATCH")
        if observed["execution_mode"] != verified["execution_mode"]:
            mismatches.append("EXECUTION_MODE_MISMATCH")

        if mismatches:
            reason_codes.extend(mismatches)
            outcome = "BLOCKED"
            identity_match = False
        else:
            reason_codes.append("ACCEPTED")
            outcome = "ACCEPTED"
            identity_match = True

    if not reason_codes:
        # Defensive: never fall through to a silent ACCEPTED.
        reason_codes.append("EVIDENCE_GAP")
        outcome = "BLOCKED"

    # Fail-closed: any malformed/evidence-gap reason forces a non-ACCEPTED outcome
    # and clears any accidental ACCEPTED marker before it is recorded.
    if any(rc in ("MALFORMED_INPUT", "EVIDENCE_GAP") for rc in reason_codes):
        outcome = "BLOCKED"
        if "ACCEPTED" in reason_codes:
            reason_codes.remove("ACCEPTED")

    reason_code = reason_codes[0]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "observed_identity": dict(observed_identity) if isinstance(observed_identity, dict) else None,
        "verified_source": dict(verified_source) if isinstance(verified_source, dict) else None,
        "identity_match": identity_match,
        "outcome": outcome,
        "reason_code": reason_code,
        "reason_codes": reason_codes,
        "missing_fields": missing_fields,
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
    payload["decision_digest"] = _digest(payload)
    return payload
