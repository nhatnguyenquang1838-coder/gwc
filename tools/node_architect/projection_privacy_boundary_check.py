#!/usr/bin/env python3
"""Pure, deterministic projection privacy boundary check for SCRUM-228.

The evaluator receives an already-bounded candidate payload and sanitizes it
before it can be rendered for DS Admin, Task Center or an external audit surface.
Prohibited raw values (secrets, credentials, tokens, private keys, production
data, hidden reasoning) are rejected; approved sensitive metadata is redacted
per an explicit per-target policy. Raw protected values never appear in output,
diagnostics, redaction metadata or hashes.

It performs no secret retrieval, decryption, storage, connector call, target
write, policy mutation, DLP service invocation, or any authority grant.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "projection-privacy-decision"

# Closed classification model.
CLASSIFICATIONS = {
    "PUBLIC_METADATA",
    "INTERNAL_METADATA",
    "CONFIDENTIAL_METADATA",
    "PERSONAL_SENSITIVE",
    "SECRET",
    "CREDENTIAL",
    "TOKEN",
    "PRIVATE_KEY",
    "PRODUCTION_DATA",
    "HIDDEN_REASONING",
    "POLICY_REDACTED",
}

# Prohibited from projection under any policy.
PROHIBITED = {
    "SECRET",
    "CREDENTIAL",
    "TOKEN",
    "PRIVATE_KEY",
    "PRODUCTION_DATA",
    "HIDDEN_REASONING",
}

# Classes requiring explicit target policy + redaction (not allowed by omission).
RESTRICTED = {
    "PERSONAL_SENSITIVE",
    "CONFIDENTIAL_METADATA",
    "POLICY_REDACTED",
}

# Mandatory protected-key detection (case-insensitive).
PROTECTED_KEY_PATTERNS = [
    re.compile(r"^password$", re.IGNORECASE),
    re.compile(r"^secret(s)?$", re.IGNORECASE),
    re.compile(r"^token(s)?$", re.IGNORECASE),
    re.compile(r"^access_token(s)?$", re.IGNORECASE),
    re.compile(r"^refresh_token(s)?$", re.IGNORECASE),
    re.compile(r"^authorization$", re.IGNORECASE),
    re.compile(r"^credential(s)?$", re.IGNORECASE),
    re.compile(r"^private_key(s)?$", re.IGNORECASE),
    re.compile(r"^client_secret(s)?$", re.IGNORECASE),
    re.compile(r"^cookie(s)?$", re.IGNORECASE),
    re.compile(r"^session(s)?$", re.IGNORECASE),
    re.compile(r"^connection_string(s)?$", re.IGNORECASE),
    re.compile(r"^production_record(s)?$", re.IGNORECASE),
    re.compile(r"^chain_of_thought$", re.IGNORECASE),
]

SOURCE_AUTHORITY_REQUIRED_FIELDS = {
    "schema_version",
    "artifact_type",
    "task_id",
    "repository",
    "projection_target",
    "source_bindings",
    "field_authority",
    "outcome",
    "authority_status",
    "reason_code",
    "reason_codes",
    "observed_at",
    "read_only_projection",
    "write_authority_granted",
    "approval_authority_granted",
    "merge_authority_granted",
    "deployment_authority_granted",
    "production_authority_granted",
    "decision_digest",
}

REASON_PRECEDENCE = [
    "PRIVACY_INPUT_INVALID",
    "PRIVACY_SOURCE_AUTHORITY_INVALID",
    "PRIVACY_CLASSIFICATION_MISSING",
    "PRIVACY_SECRET_REJECTED",
    "PRIVACY_CREDENTIAL_REJECTED",
    "PRIVACY_TOKEN_REJECTED",
    "PRIVACY_PRIVATE_KEY_REJECTED",
    "PRIVACY_PRODUCTION_DATA_REJECTED",
    "PRIVACY_HIDDEN_REASONING_REJECTED",
    "PRIVACY_TARGET_POLICY_DENIED",
    "PRIVACY_REDACTION_DIRECTIVE_INVALID",
    "PRIVACY_PAYLOAD_LIMIT_EXCEEDED",
    "PRIVACY_LEAK_DETECTED",
    "PRIVACY_DIGEST_MISMATCH",
    "PRIVACY_APPROVED_REDACTED",
    "PRIVACY_APPROVED",
]

_TASK_RE = re.compile(r"^[A-Z][A-Z0-9]+-[1-9][0-9]*$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TARGET_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

MAX_PAYLOAD_BYTES = 1_048_576  # 1 MiB
MAX_DEPTH = 16

_ZERO_DIGEST = "sha256:" + "0" * 64


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _timestamp(value: object) -> str:
    if value is None:
        return "1970-01-01T00:00:00Z"
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_protected_key(key: str) -> bool:
    return any(pattern.fullmatch(key) for pattern in PROTECTED_KEY_PATTERNS)


def _primary(reasons: set[str]) -> str:
    for code in REASON_PRECEDENCE:
        if code in reasons:
            return code
    return "PRIVACY_INPUT_INVALID"


def _source_authority_is_valid(
    decision: object, task_id: str, repository: str, projection_target: str
) -> tuple[bool, str]:
    if not isinstance(decision, dict) or set(decision) != SOURCE_AUTHORITY_REQUIRED_FIELDS:
        return False, ""
    digest = decision.get("decision_digest")

    def _semantic_digest() -> str:
        semantic = {k: v for k, v in decision.items() if k not in {"reason_codes", "decision_digest"}}
        return _digest(semantic)

    try:
        digest_matches = (
            isinstance(digest, str)
            and bool(_DIGEST_RE.fullmatch(digest))
            and digest == _semantic_digest()
        )
    except Exception:
        digest_matches = False

    valid = (
        decision.get("schema_version") == "1.0"
        and decision.get("artifact_type") == "projection-source-authority-decision"
        and decision.get("task_id") == task_id
        and decision.get("repository") == repository
        and decision.get("projection_target") == projection_target
        and decision.get("outcome") == "READY"
        and decision.get("authority_status") == "CONFIRMED"
        and decision.get("reason_code") == "PROJECTION_SOURCE_AUTHORITY_CONFIRMED"
        and digest_matches
        and decision.get("read_only_projection") is True
        and all(
            decision.get(key) is False
            for key in (
                "write_authority_granted",
                "approval_authority_granted",
                "merge_authority_granted",
                "deployment_authority_granted",
                "production_authority_granted",
            )
        )
    )
    return valid, digest if isinstance(digest, str) and _DIGEST_RE.fullmatch(digest) else _ZERO_DIGEST


def _classify_field(
    key: str,
    classification_hint: str | None,
    field_classifications: dict[str, str],
) -> str | None:
    """Return a classification for `key`, or None if a protected key is unclassified."""
    if key in field_classifications:
        return field_classifications[key]
    if classification_hint in CLASSIFICATIONS:
        return classification_hint
    if _is_protected_key(key):
        return None  # mandatory protected key present but unclassified -> caller fails closed
    return "PUBLIC_METADATA"


def _recursive_scan(
    node: Any,
    path: str,
    depth: int,
    reasons: set[str],
    field_classifications: dict[str, str],
) -> None:
    """Recursively detect prohibited data, unclassified protected keys, and violations."""
    if depth > MAX_DEPTH:
        reasons.add("PRIVACY_PAYLOAD_LIMIT_EXCEEDED")
        return
    if isinstance(node, dict):
        for k, v in node.items():
            child_path = f"{path}/{k}" if path else k
            classification = _classify_field(k, None, field_classifications)
            if classification is None:
                reasons.add("PRIVACY_CLASSIFICATION_MISSING")
                continue
            if classification in PROHIBITED:
                reasons.add(f"PRIVACY_{classification}_REJECTED")
            elif classification == "HIDDEN_REASONING":
                reasons.add("PRIVACY_HIDDEN_REASONING_REJECTED")
            _recursive_scan(v, child_path, depth + 1, reasons, field_classifications)
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            _recursive_scan(item, f"{path}[{idx}]", depth + 1, reasons, field_classifications)


def _policy_allows(classification: str, allowed_classes: set[str]) -> bool:
    return classification in allowed_classes


def _sanitize(
    node: Any,
    path: str,
    depth: int,
    reasons: set[str],
    field_classifications: dict[str, str],
    policy: dict[str, Any],
    redactions: list[dict[str, Any]],
    allowed_classes: set[str],
) -> Any:
    """Return a sanitized copy; appends redaction records; leaves originals out entirely."""
    if depth > MAX_DEPTH:
        return None
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            child_path = f"{path}/{k}" if path else k
            classification = _classify_field(k, None, field_classifications)
            if classification is None:
                # unclassified protected key already flagged upstream; drop the value
                continue
            if classification in PROHIBITED or classification == "HIDDEN_REASONING":
                # rejected upstream; should not reach sanitize for valid payloads
                continue
            if classification in RESTRICTED:
                if not _policy_allows(classification, allowed_classes):
                    reasons.add("PRIVACY_TARGET_POLICY_DENIED")
                    continue
                if policy.get("redact_fields") and k in policy["redact_fields"]:
                    out[k] = "[REDACTED]"
                    redactions.append({
                        "field_path": child_path,
                        "classification": classification,
                        "action": "REDACT",
                        "replacement_token": "[REDACTED]",
                        "reason_code": "PRIVACY_APPROVED_REDACTED",
                    })
                elif policy.get("remove_fields") and k in policy["remove_fields"]:
                    redactions.append({
                        "field_path": child_path,
                        "classification": classification,
                        "action": "REMOVE",
                        "replacement_token": "[REMOVED]",
                        "reason_code": "PRIVACY_APPROVED_REDACTED",
                    })
                    # field omitted entirely
                else:
                    reasons.add("PRIVACY_TARGET_POLICY_DENIED")
                    continue
            else:
                out[k] = _sanitize(
                    v, child_path, depth + 1, reasons, field_classifications, policy, redactions, allowed_classes
                )
        return out
    if isinstance(node, list):
        return [
            _sanitize(item, f"{path}[{idx}]", depth + 1, reasons, field_classifications, policy, redactions, allowed_classes)
            for idx, item in enumerate(node)
        ]
    return node


def _leak_scan(node: Any, reasons: set[str], depth: int = 0) -> None:
    """Fail closed if any prohibited raw value survives after sanitization."""
    if depth > MAX_DEPTH or isinstance(node, (int, float, bool)) or node is None:
        return
    if isinstance(node, str):
        low = node.lower()
        for token in ("password", "secret", "token", "credential", "client_secret", "private_key",
                      "access_token", "refresh_token", "authorization", "connection_string",
                      "production_record", "chain_of_thought"):
            if token in low:
                reasons.add("PRIVACY_LEAK_DETECTED")
                return
        return
    if isinstance(node, dict):
        for v in node.values():
            _leak_scan(v, reasons, depth + 1)
    elif isinstance(node, list):
        for item in node:
            _leak_scan(item, reasons, depth + 1)


def decide_projection_privacy(
    *,
    task_id: str,
    repository: str,
    projection_target: str,
    source_authority_decision: dict[str, object],
    candidate_payload: dict[str, object],
    field_classifications: list[dict[str, str]],
    redaction_policy: dict[str, object],
    expected_sanitized_digest: str | None = None,
    evaluated_at: str | None = None,
) -> dict[str, object]:
    """Return a schema-valid projection-privacy-decision without I/O or mutation."""

    reasons: set[str] = set()

    safe_task_id = task_id if isinstance(task_id, str) and _TASK_RE.fullmatch(task_id) else "INVALID-1"
    safe_repository = repository if isinstance(repository, str) and _REPOSITORY_RE.fullmatch(repository) else "invalid/repository"
    safe_target = projection_target if isinstance(projection_target, str) and _TARGET_RE.fullmatch(projection_target) else "invalid-target"
    if safe_task_id != task_id or safe_repository != repository or safe_target != projection_target:
        reasons.add("PRIVACY_INPUT_INVALID")

    try:
        evaluated_text = _timestamp(evaluated_at)
    except Exception:
        evaluated_text = "1970-01-01T00:00:00Z"
        reasons.add("PRIVACY_INPUT_INVALID")

    if not isinstance(candidate_payload, dict):
        reasons.add("PRIVACY_INPUT_INVALID")
        candidate_payload = {}
    if not isinstance(field_classifications, list):
        reasons.add("PRIVACY_INPUT_INVALID")
        field_classifications = []
    if not isinstance(redaction_policy, dict):
        reasons.add("PRIVACY_INPUT_INVALID")
        redaction_policy = {}

    # Precedence 1: input validity (already above).

    # Precedence 2: source-authority binding.
    authority_valid, authority_digest = _source_authority_is_valid(
        source_authority_decision, task_id, repository, projection_target
    )
    if not authority_valid:
        reasons.add("PRIVACY_SOURCE_AUTHORITY_INVALID")

    # Build classification map from field_classifications list.
    classification_map: dict[str, str] = {}
    for entry in field_classifications:
        if not isinstance(entry, dict):
            reasons.add("PRIVACY_INPUT_INVALID")
            continue
        fpath = entry.get("field_path")
        cls = entry.get("classification")
        if not isinstance(fpath, str) or not fpath or not isinstance(cls, str) or cls not in CLASSIFICATIONS:
            reasons.add("PRIVACY_INPUT_INVALID")
            continue
        classification_map[fpath] = cls

    # Precedence 3-8: recursive analysis of the candidate payload.
    _recursive_scan(candidate_payload, "", 0, reasons, classification_map)

    # Payload size/depth limits.
    try:
        payload_bytes = len(_canonical_json(candidate_payload).encode("utf-8"))
    except Exception:
        payload_bytes = MAX_PAYLOAD_BYTES + 1
    if payload_bytes > MAX_PAYLOAD_BYTES:
        reasons.add("PRIVACY_PAYLOAD_LIMIT_EXCEEDED")

    # Redaction policy shape.
    allowed_classes = set(redaction_policy.get("allowed_classes", [])) if isinstance(redaction_policy.get("allowed_classes"), list) else set()
    if allowed_classes and not allowed_classes.issubset(CLASSIFICATIONS):
        reasons.add("PRIVACY_REDACTION_DIRECTIVE_INVALID")

    # Precedence 6: redaction directive validity (paths referenced must exist / be supported).
    redact_fields = redaction_policy.get("redact_fields")
    remove_fields = redaction_policy.get("remove_fields")
    if (redact_fields is not None and not isinstance(redact_fields, list)) or (
        remove_fields is not None and not isinstance(remove_fields, list)
    ):
        reasons.add("PRIVACY_REDACTION_DIRECTIVE_INVALID")

    # If any hard rejection reason already present, do not sanitize.
    hard_reasons = {
        "PRIVACY_INPUT_INVALID",
        "PRIVACY_SOURCE_AUTHORITY_INVALID",
        "PRIVACY_CLASSIFICATION_MISSING",
        "PRIVACY_SECRET_REJECTED",
        "PRIVACY_CREDENTIAL_REJECTED",
        "PRIVACY_TOKEN_REJECTED",
        "PRIVACY_PRIVATE_KEY_REJECTED",
        "PRIVACY_PRODUCTION_DATA_REJECTED",
        "PRIVACY_HIDDEN_REASONING_REJECTED",
        "PRIVACY_TARGET_POLICY_DENIED",
        "PRIVACY_REDACTION_DIRECTIVE_INVALID",
        "PRIVACY_PAYLOAD_LIMIT_EXCEEDED",
    }

    sanitized_payload: dict[str, Any] = {}
    redactions: list[dict[str, Any]] = []
    if not (reasons & hard_reasons):
        sanitized_payload = _sanitize(
            candidate_payload, "", 0, reasons, classification_map, redaction_policy, redactions, allowed_classes
        ) or {}
        # Precedence 8: residual leakage scan on the sanitized output.
        _leak_scan(sanitized_payload, reasons)

    # Precedence 9: expected digest comparison (participates in outcome determination).
    sanitized_digest_early = _digest({
        "task_id": safe_task_id,
        "repository": safe_repository,
        "projection_target": safe_target,
        "source_authority_digest": authority_digest,
        "policy_revision": (redaction_policy.get("policy_revision") if isinstance(redaction_policy.get("policy_revision"), str) and redaction_policy.get("policy_revision") else "unspecified"),
        "policy_digest": _digest({k: v for k, v in redaction_policy.items() if k != "policy_digest"}),
        "sanitized_payload": sanitized_payload,
        "redactions": sorted(redactions, key=_canonical_json),
    })
    if expected_sanitized_digest is not None:
        if not isinstance(expected_sanitized_digest, str) or not _DIGEST_RE.fullmatch(expected_sanitized_digest):
            reasons.add("PRIVACY_INPUT_INVALID")
        elif expected_sanitized_digest != sanitized_digest_early:
            reasons.add("PRIVACY_DIGEST_MISMATCH")

    # Precedence 10/11: outcome determination.
    redacted = bool(redactions)
    if not reasons:
        # No transformation needed -> APPROVED
        reasons.add("PRIVACY_APPROVED_REDACTED" if redacted else "PRIVACY_APPROVED")
    elif redacted and reasons <= {"PRIVACY_APPROVED_REDACTED"}:
        # redaction happened and nothing else blocks -> explicit redacted outcome
        reasons.add("PRIVACY_APPROVED_REDACTED")
    elif redacted:
        # redaction occurred but other benign reasons may co-occur; surface redacted
        reasons.add("PRIVACY_APPROVED_REDACTED")
    # Any hard rejection reason (or leak) is already a valid primary via precedence.

    primary = _primary(reasons)
    ready = reasons <= {"PRIVACY_APPROVED", "PRIVACY_APPROVED_REDACTED"}
    privacy_status = (
        "REDACTED" if "PRIVACY_APPROVED_REDACTED" in reasons else "APPROVED" if ready else "BLOCKED"
    )

    policy_revision = redaction_policy.get("policy_revision")
    if not isinstance(policy_revision, str) or not policy_revision:
        policy_revision = "unspecified"
    policy_digest_input = {k: v for k, v in redaction_policy.items() if k not in {"policy_digest"}}
    policy_digest = _digest(policy_digest_input)

    sanitized_digest = _digest({
        "task_id": safe_task_id,
        "repository": safe_repository,
        "projection_target": safe_target,
        "source_authority_digest": authority_digest,
        "policy_revision": policy_revision,
        "policy_digest": policy_digest,
        "sanitized_payload": sanitized_payload,
        "redactions": sorted(redactions, key=_canonical_json),
    })

    decision_digest = _digest({
        "task_id": safe_task_id,
        "repository": safe_repository,
        "projection_target": safe_target,
        "source_authority_digest": authority_digest,
        "policy_revision": policy_revision,
        "policy_digest": policy_digest,
        "sanitized_digest": sanitized_digest,
        "privacy_status": privacy_status,
        "outcome": "READY" if ready else "BLOCKED",
        "reason_code": primary,
        "reason_codes": sorted(reasons),
        "redactions": sorted(redactions, key=_canonical_json),
    })

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "task_id": safe_task_id,
        "repository": safe_repository,
        "projection_target": safe_target,
        "source_authority_digest": authority_digest,
        "policy_revision": policy_revision,
        "policy_digest": policy_digest,
        "sanitized_payload": sanitized_payload,
        "redactions": sorted(redactions, key=_canonical_json),
        "privacy_status": privacy_status,
        "outcome": "READY" if ready else "BLOCKED",
        "reason_code": primary,
        "reason_codes": sorted(reasons),
        "evaluated_at": evaluated_text,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "sanitized_digest": sanitized_digest,
        "decision_digest": decision_digest,
    }


# ---------------------------------------------------------------------------
# NA81 (SCRUM-351 / GitHub #286) explicit privacy-boundary assertion layer.
#
# Reuses the SCRUM-228 ``decide_projection_privacy`` core (closed,
# fail-closed classification) and asserts the explicit SCRUM-351 guarantees
# that consumers (SCRUM-343 / SCRUM-344 / SCRUM-345) rely on before any
# projection intent is emitted:
#
#   * every field resolves deterministically to ALLOW / SANITIZE / DENY;
#   * an unknown classification fails closed (never projected);
#   * secrets / credentials / prohibited data never reach the output;
#   * the boundary decision is never authoritative (read-only only).
#
# The base core is unchanged and reused as the decision engine. This layer is
# additive: it does not mutate the base decision, the node descriptor, or any
# ``*.node.json`` provenance field.
# ---------------------------------------------------------------------------

NA81_ARTIFACT_TYPE = "projection-privacy-boundary-decision"

# Deterministic per-field dispositions required by SCRUM-351.
DISPOSITION_ALLOW = "ALLOW"
DISPOSITION_SANITIZE = "SANITIZE"
DISPOSITION_DENY = "DENY"
DISPOSITION_UNKNOWN_FAIL_CLOSED = "UNKNOWN_FAIL_CLOSED"


def na81_disposition_for(
    key: str,
    classification: str | None,
    classification_map: dict[str, str],
) -> str:
    """Deterministically map one field to ALLOW / SANITIZE / DENY / UNKNOWN_FAIL_CLOSED.

    SCRUM-351 requires every field to resolve to exactly one disposition before
    any projection intent is emitted. An explicit but unrecognized classification
    fails closed (DENY / ``UNKNOWN_FAIL_CLOSED``) and must never be projected; a
    mandatory protected key without a classification also fails closed.
    """
    if classification in CLASSIFICATIONS:
        cls = classification
    elif key in classification_map:
        cls = classification_map[key]
    elif classification in (None, ""):
        # No hint: protected keys fail closed; other keys default to ALLOW (public).
        return DISPOSITION_UNKNOWN_FAIL_CLOSED if _is_protected_key(key) else DISPOSITION_ALLOW
    else:
        # Explicit but unrecognized classification -> fail closed.
        return DISPOSITION_UNKNOWN_FAIL_CLOSED

    if cls in PROHIBITED or cls == "HIDDEN_REASONING":
        return DISPOSITION_DENY
    if cls in RESTRICTED:
        return DISPOSITION_SANITIZE
    return DISPOSITION_ALLOW


def decide_projection_privacy_na81(
    *,
    task_id: str,
    repository: str,
    projection_target: str,
    source_authority_decision: dict[str, object],
    candidate_payload: dict[str, object],
    field_classifications: list[dict[str, str]],
    redaction_policy: dict[str, object],
    expected_sanitized_digest: str | None = None,
    evaluated_at: str | None = None,
) -> dict[str, object]:
    """Return an NA81-bounded projection-privacy-boundary decision.

    The base SCRUM-228 decision is reused as the privacy engine; this layer
    adds the explicit SCRUM-351 assertions and a consumer-bindable
    ``privacy_boundary_digest`` (the base ``decision_digest``). The base
    decision is preserved verbatim under ``privacy_decision`` so the underlying
    provenance is untouched.
    """

    # Explicit SCRUM-351 pre-flight: detect unknown classifications (fail closed).
    unknown_classification_detected = False
    if isinstance(field_classifications, list):
        for entry in field_classifications:
            if isinstance(entry, dict):
                cls = entry.get("classification")
                if isinstance(cls, str) and cls and cls not in CLASSIFICATIONS:
                    unknown_classification_detected = True

    def _run() -> dict[str, object]:
        return decide_projection_privacy(
            task_id=task_id,
            repository=repository,
            projection_target=projection_target,
            source_authority_decision=source_authority_decision,
            candidate_payload=candidate_payload,
            field_classifications=field_classifications,
            redaction_policy=redaction_policy,
            expected_sanitized_digest=expected_sanitized_digest,
            evaluated_at=evaluated_at,
        )

    base = _run()
    # Replay for determinism / idempotency assertion.
    replay = _run()
    deterministic = replay.get("decision_digest") == base.get("decision_digest")

    # Explicit non-authoritative guarantee.
    non_authoritative = (
        base.get("read_only_projection") is True
        and all(
            base.get(k) is False
            for k in (
                "write_authority_granted",
                "approval_authority_granted",
                "merge_authority_granted",
                "deployment_authority_granted",
                "production_authority_granted",
            )
        )
    )

    # No secrets / credentials: leak scan on the final sanitized output.
    leak = set()
    _leak_scan(base.get("sanitized_payload", {}), leak)
    no_secrets_credentials = not leak

    # Unknown classification fails closed: never yields a READY projection.
    unknown_classification_fail_closed = (not unknown_classification_detected) or (
        base.get("outcome") == "BLOCKED"
    )

    privacy_boundary_digest = base.get("decision_digest", _ZERO_DIGEST)

    na81 = {
        "deterministic": deterministic,
        "non_authoritative": non_authoritative,
        "no_secrets_credentials": no_secrets_credentials,
        "unknown_classification_fail_closed": unknown_classification_fail_closed,
        "unknown_classification_detected": unknown_classification_detected,
        "privacy_boundary_digest": privacy_boundary_digest,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": NA81_ARTIFACT_TYPE,
        "task_id": base.get("task_id"),
        "repository": base.get("repository"),
        "projection_target": base.get("projection_target"),
        "outcome": base.get("outcome"),
        "reason_code": base.get("reason_code"),
        "privacy_status": base.get("privacy_status"),
        "privacy_boundary_digest": privacy_boundary_digest,
        "privacy_decision": base,
        "na81": na81,
    }
