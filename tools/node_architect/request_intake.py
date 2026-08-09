"""Deterministic request-intake evaluator for SCRUM-298."""
from __future__ import annotations
import hashlib, json, re
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "request-intake-record"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
REPO = re.compile(r"^[^/\s]+/[^/\\s]+$")

REASONS = {
    "ACCEPTED",
    "MALFORMED_INPUT",
    "AMBIGUOUS_INTENT",
    "SCOPE_DRIFT",
}

def _canon(v: Any) -> Any:
    if isinstance(v, Mapping):
        return {str(k): _canon(v[k]) for k in sorted(v, key=str)}
    if isinstance(v, list):
        items = [_canon(x) for x in v]
        keyed = {json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False): x for x in items}
        return [keyed[k] for k in sorted(keyed)]
    return v

def canonical_json(payload: Any) -> str:
    return json.dumps(_canon(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode()).hexdigest()

def _validate_request_shape(request: Any) -> list[str]:
    """Validate the incoming request shape."""
    if not isinstance(request, Mapping):
        return ["MALFORMED_INPUT"]
    req_fields = ("intent", "outcome", "constraints", "exclusions", "entry_guards")
    if any(k not in request for k in req_fields):
        return ["MALFORMED_INPUT"]
    if not isinstance(request.get("intent"), str) or not request["intent"].strip():
        return ["MALFORMED_INPUT"]
    if not isinstance(request.get("outcome"), str) or not request["outcome"].strip():
        return ["MALFORMED_INPUT"]
    for field in ("constraints", "exclusions", "entry_guards"):
        val = request.get(field)
        if not isinstance(val, list) or not all(isinstance(x, str) and x for x in val):
            return ["MALFORMED_INPUT"]
        if len(val) != len(set(val)):
            return ["MALFORMED_INPUT"]
    return []

def _check_ambiguous_intent(request: Mapping[str, Any]) -> list[str]:
    """Check for ambiguous or conflicting intent signals."""
    issues = []
    intent = str(request.get("intent", ""))
    outcome = str(request.get("outcome", ""))
    constraints = request.get("constraints", [])
    exclusions = request.get("exclusions", [])
    guards = request.get("entry_guards", [])

    # Ambiguous intent: empty or generic without specific signals
    if not intent.strip() or intent.lower() in {"test", "debug", "fix", "update", "change"}:
        issues.append("AMBIGUOUS_INTENT")

    # Conflicting constraints vs exclusions
    if set(constraints) & set(exclusions):
        issues.append("AMBIGUOUS_INTENT")

    # Entry guards must include G0_CONTEXT
    if "G0_CONTEXT" not in guards:
        issues.append("AMBIGUOUS_INTENT")

    return issues

def _check_scope_drift(request: Mapping[str, Any]) -> list[str]:
    """Check if request scope exceeds the intake_context family boundary."""
    issues = []
    intent = str(request.get("intent", "")).lower()
    outcome = str(request.get("outcome", "")).lower()
    # Production/deployment authority keywords
    prod_keywords = ("production", "deploy", "release", "migration", "credential", "secret", "merge authority", "gate authority", "write authority")
    if any(k in intent or k in outcome for k in prod_keywords):
        issues.append("SCOPE_DRIFT")
    return issues

def normalize_request_intake(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    request: dict[str, object]
) -> dict[str, Any]:
    """
    Normalize a user/assigned-work request into a typed, bounded intake record.

    Args:
        task_id: Jira task identifier (e.g., SCRUM-298)
        repository: Owner/repo (e.g., nhatnguyenquang1838-coder/gwc)
        base_sha: 40-char protected base commit SHA
        request: Raw request with intent, outcome, constraints, exclusions, entry_guards

    Returns:
        Normalized intake record artifact (request-intake-record)
    """
    # Validate inputs
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be a non-empty string")
    if not isinstance(repository, str) or not REPO.fullmatch(repository):
        raise ValueError("repository must be in owner/repo format")
    if not isinstance(base_sha, str) or not SHA40.fullmatch(base_sha):
        raise ValueError("base_sha must be a 40-char lowercase hex string")

    issues = _validate_request_shape(request)
    issues += _check_ambiguous_intent(request)
    issues += _check_scope_drift(request)

    # Determine primary reason code
    if issues:
        # Order by precedence for deterministic primary
        precedence = {"MALFORMED_INPUT": 10, "AMBIGUOUS_INTENT": 20, "SCOPE_DRIFT": 30}
        primary = min(issues, key=lambda c: precedence.get(c, 999))
        outcome = "BLOCKED"
        reason_codes = sorted(set(issues), key=lambda c: (precedence.get(c, 999), c))
    else:
        outcome = "ACCEPTED"
        primary = "ACCEPTED"
        reason_codes = ["ACCEPTED"]

    # Build canonical payload for snapshot hash
    payload = {
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "intent": str(request.get("intent", "")).strip(),
        "outcome": outcome,
        "constraints": sorted(set(request.get("constraints", []))),
        "exclusions": sorted(set(request.get("exclusions", []))),
        "entry_guards": sorted(set(request.get("entry_guards", []))),
        "reason_codes": reason_codes,
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
    }

    snapshot_hash = digest_payload(payload)

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "intent": payload["intent"],
        "outcome": payload["outcome"],
        "constraints": payload["constraints"],
        "exclusions": payload["exclusions"],
        "entry_guards": payload["entry_guards"],
        "reason_code": primary,
        "reason_codes": reason_codes,
        "snapshot_hash": snapshot_hash,
        "read_only_projection": True,
        "write_authority_granted": False,
        "commit_authority_granted": False,
        "push_authority_granted": False,
        "pr_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def _validate_artifact(artifact: Mapping[str, Any]) -> list[str]:
    """Validate a request-intake-record artifact."""
    if not isinstance(artifact, Mapping):
        return ["MALFORMED_INPUT"]
    required = (
        "schema_version", "artifact_type", "task_id", "repository", "base_sha",
        "intent", "outcome", "constraints", "exclusions", "entry_guards",
        "reason_code", "reason_codes", "snapshot_hash",
        "read_only_projection",
        "write_authority_granted", "commit_authority_granted",
        "push_authority_granted", "pr_authority_granted",
        "merge_authority_granted", "deployment_authority_granted",
        "production_authority_granted"
    )
    if any(k not in artifact for k in required):
        return ["MALFORMED_INPUT"]
    if artifact.get("schema_version") != SCHEMA_VERSION:
        return ["MALFORMED_INPUT"]
    if artifact.get("artifact_type") != ARTIFACT_TYPE:
        return ["MALFORMED_INPUT"]
    if artifact.get("read_only_projection") is not True:
        return ["MALFORMED_INPUT"]
    # Verify snapshot hash matches
    payload = {k: v for k, v in artifact.items() if k != "snapshot_hash"}
    expected = digest_payload(payload)
    if artifact.get("snapshot_hash") != expected:
        return ["MALFORMED_INPUT"]
    return []


if __name__ == "__main__":
    # Self-test
    test_req = {
        "intent": "Normalize a user request into a typed intake record",
        "outcome": "Normalized intake record with structured fields",
        "constraints": ["Input must be canonical request shape", "No ambiguous signals"],
        "exclusions": ["Production runtime behavior", "Deployment, migration, or credential operations"],
        "entry_guards": ["G0_CONTEXT", "read_only authority_boundary"],
    }
    art = normalize_request_intake(
        task_id="SCRUM-298",
        repository="nhatnguyenquang1838-coder/gwc",
        base_sha="cff9fb1bbe55493ccc8bc7b48e48f613521a58b2",
        request=test_req
    )
    print(json.dumps(art, indent=2, ensure_ascii=False))
    assert not _validate_artifact(art), "Self-test artifact validation failed"
    print("Self-test PASS")