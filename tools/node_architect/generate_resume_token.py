#!/usr/bin/env python3
"""Generate deterministic, fail-closed GWC resume tokens."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

GATES = {"G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SCOPE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ResumeTokenError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _required(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResumeTokenError("RESUME_TOKEN_BINDING_MISSING", f"{name} is required")
    return value


def _utc(value: str, name: str) -> datetime:
    value = _required(value, name)
    if not value.endswith("Z"):
        raise ResumeTokenError("RESUME_TOKEN_TIME_INVALID", f"{name} must be UTC")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResumeTokenError("RESUME_TOKEN_TIME_INVALID", f"{name} is not ISO-8601") from exc


def _sha(value: str, name: str) -> str:
    value = _required(value, name)
    if not SHA40.fullmatch(value):
        raise ResumeTokenError("RESUME_TOKEN_BINDING_INVALID", f"{name} must be a lowercase 40-character SHA")
    return value


def generate_resume_token(
    *, checkpoint: Mapping[str, Any], task_id: str, run_id: str,
    node_id: str = "runtime_checkpoint.resume-token-generation",
    gate: str = "G2_EXECUTION", scope_hash: str, base_sha: str,
    head_sha: str | None, state_digest: str, lease_token: str,
    fencing_token: str, issued_at_utc: str, expires_at_utc: str,
    next_gate: str = "G2_EXECUTION", next_action: str = "validate_resume_token",
    requires_human_approval: bool = False, approval_envelope_ref: str | None = None,
    approval_command: str | None = None, audit_links: list[str] | None = None,
) -> dict[str, Any]:
    task_id = _required(task_id, "task_id")
    run_id = _required(run_id, "run_id")
    node_id = _required(node_id, "node_id")
    gate = _required(gate, "gate")
    scope_hash = _required(scope_hash, "scope_hash")
    next_gate = _required(next_gate, "next_gate")
    next_action = _required(next_action, "next_action")
    checkpoint_id = _required(checkpoint.get("checkpoint_id"), "checkpoint.checkpoint_id")
    state_digest = _required(state_digest, "state_digest")
    checkpoint_task = checkpoint.get("task") or {}
    if not isinstance(checkpoint_task, Mapping):
        raise ResumeTokenError("RESUME_TOKEN_CHECKPOINT_MISMATCH", "checkpoint task must be an object")
    if checkpoint_task.get("id") not in {None, task_id}:
        raise ResumeTokenError("RESUME_TOKEN_CHECKPOINT_MISMATCH", "checkpoint task does not match task_id")
    if checkpoint.get("state_digest") not in {None, state_digest}:
        raise ResumeTokenError("RESUME_TOKEN_STATE_DIGEST_MISMATCH", "checkpoint state digest does not match state_digest")
    if not SCOPE.fullmatch(scope_hash):
        raise ResumeTokenError("RESUME_TOKEN_BINDING_INVALID", "scope_hash must be sha256-prefixed")
    base_sha = _sha(base_sha, "base_sha")
    if head_sha is not None:
        head_sha = _sha(head_sha, "head_sha")
    if not SCOPE.fullmatch(state_digest):
        raise ResumeTokenError("RESUME_TOKEN_BINDING_INVALID", "state_digest must be sha256-prefixed")
    lease_token = _required(lease_token, "lease_token")
    fencing_token = _required(fencing_token, "fencing_token")
    issued = _utc(issued_at_utc, "issued_at_utc")
    expires = _utc(expires_at_utc, "expires_at_utc")
    if expires <= issued:
        raise ResumeTokenError("RESUME_TOKEN_TIME_INVALID", "expires_at_utc must be after issued_at_utc")
    if gate not in GATES or next_gate not in GATES:
        raise ResumeTokenError("RESUME_TOKEN_GATE_INVALID", "gate and next_gate must be known gates")
    if gate != "G2_EXECUTION":
        raise ResumeTokenError("RESUME_TOKEN_GATE_INVALID", "resume-token-generation is G2-only")
    if not isinstance(requires_human_approval, bool):
        raise ResumeTokenError("RESUME_TOKEN_APPROVAL_INVALID", "requires_human_approval must be boolean")
    if requires_human_approval and not (approval_envelope_ref or approval_command):
        raise ResumeTokenError("RESUME_TOKEN_APPROVAL_MISSING", "approval reference is required when approval is required")

    binding = {
        "task_id": task_id, "run_id": run_id, "node_id": node_id, "gate": gate,
        "scope_hash": scope_hash, "base_sha": base_sha, "head_sha": head_sha,
        "checkpoint_id": checkpoint_id, "state_digest": state_digest,
        "lease_token": lease_token, "fencing_token": fencing_token,
        "issued_at_utc": issued_at_utc, "expires_at_utc": expires_at_utc,
        "next_gate": next_gate, "next_action": next_action,
        "requires_human_approval": requires_human_approval,
        "approval_envelope_ref": approval_envelope_ref, "approval_command": approval_command,
    }
    token = {
        "schema_version": "0.1",
        **binding,
        "resume_token_id": "resume_" + digest(binding)[7:27],
        "audit_projection": {"source_of_truth": False, "links": sorted(set(audit_links or []))},
        "authority_granted": False,
        "write_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    token["token_digest"] = digest(token)
    return token


def validate_generated_token(token: Mapping[str, Any], checkpoint: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if token.get("checkpoint_id") != checkpoint.get("checkpoint_id"):
        errors.append("RESUME_TOKEN_CHECKPOINT_MISMATCH")
    if checkpoint.get("state_digest") not in {None, token.get("state_digest")}:
        errors.append("RESUME_TOKEN_STATE_DIGEST_MISMATCH")
    if token.get("token_digest") != digest({key: value for key, value in token.items() if key != "token_digest"}):
        errors.append("RESUME_TOKEN_DIGEST_MISMATCH")
    if any(token.get(key) is not False for key in ("authority_granted", "write_authority_granted", "merge_authority_granted", "deployment_authority_granted", "production_authority_granted")):
        errors.append("RESUME_TOKEN_AUTHORITY_ESCALATION")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    checkpoint = payload.pop("checkpoint")
    token = generate_resume_token(checkpoint=checkpoint, **payload)
    errors = validate_generated_token(token, checkpoint)
    if errors:
        raise SystemExit(json.dumps({"status": "FAIL", "errors": errors}, sort_keys=True))
    encoded = json.dumps(token, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
