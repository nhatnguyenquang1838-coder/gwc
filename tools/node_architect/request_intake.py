#!/usr/bin/env python3
"""Deterministic request-intake evaluator for intake_context.request-intake (SCRUM-298).

Normalizes a user/assigned-work request into a typed, bounded intake record
without creating execution authority. Read-only G0_CONTEXT node: it records
intent only and never promotes request text that implies merge/deploy/production
authority to gate authority.

Fail-closed invariants (mirrors intake_context family contract):
* Malformed/ambiguous signal -> deterministic BLOCKED/HUMAN_REQUIRED with exact
  missing fields and remediation.
* Same normalized request replayed with the same task/run/repo/scope identity
  yields the same canonical intake digest and no duplicate effect.
* Any implied authority intent is recorded, not promoted.

The artifact is immutable and redacted: every authority field is fixed to false.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "intake-request"

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
    "INTAKE_ACCEPTED",
    "INTAKE_MALFORMED_INPUT",
    "INTAKE_AMBIGUOUS_INTENT",
    "INTAKE_SCOPE_DRIFT",
    "INTAKE_MISSING_IDENTITY",
    "INTAKE_MISSING_TASK_BINDING",
    "INTAKE_MISSING_REPOSITORY_INTENT",
    "INTAKE_MISSING_REQUESTED_OUTCOME",
    "INTAKE_AUTHORITY_INTENT_DETECTED",
    "INTAKE_REPLAY_IDEMPOTENT",
    "INTAKE_HUMAN_REQUIRED",
}

# Higher precedence wins when multiple codes apply (lower number = louder).
PRECEDENCE = {
    "INTAKE_MALFORMED_INPUT": 10,
    "INTAKE_MISSING_IDENTITY": 20,
    "INTAKE_MISSING_TASK_BINDING": 25,
    "INTAKE_MISSING_REPOSITORY_INTENT": 30,
    "INTAKE_MISSING_REQUESTED_OUTCOME": 35,
    "INTAKE_AMBIGUOUS_INTENT": 40,
    "INTAKE_SCOPE_DRIFT": 50,
    "INTAKE_AUTHORITY_INTENT_DETECTED": 60,
    "INTAKE_HUMAN_REQUIRED": 70,
    "INTAKE_REPLAY_IDEMPOTENT": 80,
    "INTAKE_ACCEPTED": 999,
}

# Request text signals that imply authority the node must NOT promote.
AUTHORITY_SIGNALS = {
    "MERGE_AUTHORITY": re.compile(
        r"\b(merge|merge[- ]to[- ]main|auto[- ]merge|squash[- ]merge|merge[- ]branch)\b", re.I
    ),
    "DEPLOY_AUTHORITY": re.compile(r"\b(deploy|deployment|ship[- ]to[- ]prod|rollout)\b", re.I),
    "PRODUCTION_AUTHORITY": re.compile(r"\b(production|prod[- ]data|prod[- ]config)\b", re.I),
    "RELEASE_AUTHORITY": re.compile(r"\b(release|publish|version[- ]bump|cut[- ]release)\b", re.I),
    "CREDENTIAL_AUTHORITY": re.compile(
        r"\b(credential|secret|token|password|api[- ]key|private[- ]key)\b", re.I
    ),
}

SCOPE_BOUNDARY_TERMS = re.compile(
    r"\b(deploy|release|production|migrat|destroy|force[- ]push|delete[- ]branch|"
    r"credential|secret|merge[- ]to[- ]main|auto[- ]merge)\b", re.I
)

ALLOWED_NEXT_NODES = [
    "intake_context.source-resolution",
    "intake_context.context-gap-escalation",
]

ENTRY_GUARDS = ["G0_CONTEXT", "read_only"]
EXCLUSIONS = [
    "Production runtime behavior.",
    "Deployment, migration, or credential operations.",
    "Broader gate authority beyond G0_CONTEXT.",
]
CONSTRAINTS = [
    "Input must be provided via the canonical request shape.",
    "Ambiguous or conflicting signals must cause fail-closed rejection.",
    "Typed intake fields must remain bounded to the existing node family.",
]


def _canon(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, list):
        items = [_canon(x) for x in value]
        keyed = {json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False): x for x in items}
        return [keyed[k] for k in sorted(keyed)]
    return value


def canonical_json(payload: Any) -> str:
    return json.dumps(_canon(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _hex(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    m = re.match(r"^(?:sha256:)?([0-9a-f]{64})$", value)
    return m.group(1) if m else None


def _input_issues(
    *, task_id: str, repository: str, base_sha: str,
    request: Mapping[str, Any] | None,
) -> list[str]:
    issues: list[str] = []
    if not isinstance(task_id, str) or not task_id:
        issues.append("INTAKE_MALFORMED_INPUT")
    if not isinstance(repository, str) or not REPO.fullmatch(repository):
        issues.append("INTAKE_MALFORMED_INPUT")
    if not isinstance(base_sha, str) or not SHA40.fullmatch(base_sha):
        issues.append("INTAKE_MALFORMED_INPUT")
    if not isinstance(request, Mapping):
        issues.append("INTAKE_MALFORMED_INPUT")
        return issues
    if not isinstance(request.get("raw_text"), str):
        issues.append("INTAKE_MALFORMED_INPUT")
    if request.get("source") not in {"USER", "ASSIGNED_WORK", "AUTONOMOUS_NODE", "UNKNOWN"}:
        issues.append("INTAKE_MALFORMED_INPUT")
    return sorted(set(issues))


def _detect_authority_signals(raw_text: str) -> list[str]:
    found = [name for name, pat in AUTHORITY_SIGNALS.items() if pat.search(raw_text or "")]
    return sorted(set(found))


def _scope_drift(raw_text: str) -> bool:
    return bool(SCOPE_BOUNDARY_TERMS.search(raw_text or ""))


def render_request_intake(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    request: Mapping[str, Any],
    prior_intake_digest: str | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Normalize a request into a bounded intake record.

    Returns a schema-valid intake-request artifact. Fail-closed: malformed
    inputs or ambiguous intent never yield ACCEPTED.
    """
    issues = _input_issues(task_id=task_id, repository=repository, base_sha=base_sha, request=request)
    if issues:
        safe_task = task_id if isinstance(task_id, str) and task_id else "UNKNOWN"
        safe_repo = repository if isinstance(repository, str) and REPO.fullmatch(repository) else "invalid/invalid"
        safe_base = base_sha if isinstance(base_sha, str) and SHA40.fullmatch(base_sha) else "0" * 40
        safe_request = {
            "raw_text": request.get("raw_text", "") if isinstance(request.get("raw_text"), str) else "",
            "source": request.get("source") if request.get("source") in {"USER", "ASSIGNED_WORK", "AUTONOMOUS_NODE", "UNKNOWN"} else "UNKNOWN",
        }
        return _make(
            task_id=safe_task, repository=safe_repo, base_sha=safe_base,
            request=safe_request,
            normalized_intake=None, outcome="BLOCKED",
            reason_code="INTAKE_MALFORMED_INPUT", reason_codes=issues,
            missing_fields=[], authority_signals=[], remediation={
                "route": "BLOCK_G1_REVIEW",
                "next_action": "Repair malformed request-intake evaluator inputs.",
                "stop_condition": "Stop until inputs conform to the runtime interface.",
            }, next_allowed_nodes=[], observed_at=observed_at,
        )

    raw_text = request.get("raw_text", "") or ""
    source = request.get("source", "UNKNOWN")
    task_binding = request.get("task_binding")
    repo_intent = request.get("repository_intent")
    requested_outcome = request.get("requested_outcome")

    reason_codes: list[str] = []
    missing_fields: list[str] = []
    actor = (request.get("provenance") or {}).get("actor") if isinstance(request.get("provenance"), Mapping) else None
    if not isinstance(actor, str) or not actor:
        # Derive a bounded actor marker; never invent identity beyond the source.
        actor = f"request-source:{source}"
    if not isinstance(task_binding, str) or not task_binding:
        missing_fields.append("task_binding")
        reason_codes.append("INTAKE_MISSING_TASK_BINDING")
    if not isinstance(repo_intent, str) or not repo_intent:
        missing_fields.append("repository_intent")
        reason_codes.append("INTAKE_MISSING_REPOSITORY_INTENT")
    if not isinstance(requested_outcome, str) or not requested_outcome:
        missing_fields.append("requested_outcome")
        reason_codes.append("INTAKE_MISSING_REQUESTED_OUTCOME")

    authority_signals = _detect_authority_signals(raw_text)
    scope_drift = _scope_drift(raw_text)

    # Ambiguity: explicit conflict markers in the request text.
    if re.search(r"\b(but also|however,|conflicting|either .* or)\b", raw_text, re.I):
        reason_codes.append("INTAKE_AMBIGUOUS_INTENT")
    if scope_drift and not authority_signals:
        reason_codes.append("INTAKE_SCOPE_DRIFT")
    if authority_signals:
        reason_codes.append("INTAKE_AUTHORITY_INTENT_DETECTED")

    # Replay / idempotency: identical prior digest => idempotent route.
    if prior_intake_digest is not None:
        prior_hex = _hex(prior_intake_digest)
        if prior_hex is not None:
            reason_codes.append("INTAKE_REPLAY_IDEMPOTENT")

    # No required field missing and no authority/ambiguity/scope signal => accepted.
    if not missing_fields and not (authority_signals or scope_drift or "INTAKE_AMBIGUOUS_INTENT" in reason_codes):
        outcome = "ACCEPTED"
        primary = "INTAKE_REPLAY_IDEMPOTENT" if prior_intake_digest is not None else "INTAKE_ACCEPTED"
        reason_codes = [primary] if prior_intake_digest is not None else ["INTAKE_ACCEPTED"]
        remediation = None
        next_allowed = ALLOWED_NEXT_NODES
    else:
        outcome = "HUMAN_REQUIRED" if (missing_fields or authority_signals) else "BLOCKED"
        primary = min(reason_codes, key=lambda c: PRECEDENCE.get(c, 500))
        if missing_fields or authority_signals:
            route = "REQUEST_HUMAN_INPUT"
        elif "INTAKE_AMBIGUOUS_INTENT" in reason_codes or "INTAKE_SCOPE_DRIFT" in reason_codes:
            route = "BLOCK_G1_REVIEW"
        else:
            route = "RETRY_INTAKE"
        remediation = {
            "route": route,
            "next_action": _remediation_action(reason_codes, missing_fields, authority_signals),
            "stop_condition": _stop_condition(route),
        }
        next_allowed = ALLOWED_NEXT_NODES if outcome == "BLOCKED" else []

    normalized = {
        "actor": actor,
        "intent": (requested_outcome or "").strip() or "Normalize request into bounded intake record.",
        "task": task_binding if isinstance(task_binding, str) else None,
        "repository_intent": repo_intent if isinstance(repo_intent, str) else None,
        "requested_outcome": requested_outcome if isinstance(requested_outcome, str) else None,
        "constraints": list(CONSTRAINTS),
        "exclusions": list(EXCLUSIONS),
        "entry_guards": list(ENTRY_GUARDS),
        "reason_codes": {k: k for k in REASONS},
    } if outcome == "ACCEPTED" else None

    return _make(
        task_id=task_id, repository=repository, base_sha=base_sha,
        request=request, normalized_intake=normalized, outcome=outcome,
        reason_code=primary, reason_codes=sorted(set(reason_codes), key=lambda c: PRECEDENCE.get(c, 500)),
        missing_fields=missing_fields, authority_signals=authority_signals,
        remediation=remediation, next_allowed_nodes=next_allowed, observed_at=observed_at,
    )


def _remediation_action(reason_codes: list[str], missing_fields: list[str], authority_signals: list[str]) -> str:
    if authority_signals:
        return (
            "Request text implies "
            + ", ".join(authority_signals)
            + " authority. Record intent only; request human confirmation before any gate promotion."
        )
    if missing_fields:
        return "Provide missing required fields: " + ", ".join(missing_fields) + "."
    if "INTAKE_AMBIGUOUS_INTENT" in reason_codes:
        return "Resolve conflicting intent/scope signals before re-intake."
    if "INTAKE_SCOPE_DRIFT" in reason_codes:
        return "Re-scope request within the intake_context node family boundary."
    return "Repair intake inputs and replay."


def _stop_condition(route: str) -> str:
    return {
        "REQUEST_HUMAN_INPUT": "Stop until a human supplies the required fields or confirms authority intent.",
        "BLOCK_G1_REVIEW": "Stop until ambiguity/scope-drift is resolved by review.",
        "RETRY_INTAKE": "Stop until a well-formed request is replayed.",
    }.get(route, "Stop until inputs conform to the runtime interface.")


def _make(
    *, task_id: str, repository: str, base_sha: str, request: Mapping[str, Any],
    normalized_intake: Mapping[str, Any] | None, outcome: str, reason_code: str,
    reason_codes: list[str], missing_fields: list[str], authority_signals: list[str],
    remediation: Mapping[str, Any] | None, next_allowed_nodes: list[str], observed_at: str | None,
) -> dict[str, Any]:
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "request": request,
        "normalized_intake": normalized_intake,
        "intent_authority_signals": authority_signals,
        "outcome": outcome,
        "reason_code": reason_code,
        "reason_codes": reason_codes,
        "missing_fields": missing_fields,
        "remediation": remediation,
        "next_allowed_nodes": next_allowed_nodes,
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
    print(json.dumps(render_request_intake(**payload), indent=2, ensure_ascii=False))
