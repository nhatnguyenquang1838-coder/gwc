"""Deterministic intake-card renderer for SCRUM-182.

The renderer is pure and side-effect free. It validates canonical upstream
artifacts, produces a closed read-only projection, redacts protected values,
and never grants repository, PR, merge, deployment, or production authority.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

_SCHEMA_VERSION = "1.0"
_ARTIFACT_TYPE = "intake-card"
_CONTRACT_REVISION = "intake-context/v1"
_REDACTED = "[REDACTED]"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
_REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")
_ALLOWED_REDACTION_CLASSIFICATIONS = {
    "SECRET",
    "CREDENTIAL",
    "TOKEN",
    "PRIVATE_KEY",
    "PERSONAL_SENSITIVE",
    "POLICY_REDACTED",
}
_IMMUTABLE_POINTERS = {
    "/task_id",
    "/repository",
    "/base_sha",
    "/repository_context/repository",
    "/repository_context/protected_branch",
    "/repository_context/protected_base_sha",
    "/scope_hash",
}
_PROTECTED_TERMINALS = {
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "credential",
    "private_key",
    "client_secret",
    "cookie",
    "session",
}
_ALLOWED_SOURCE_MODES = {"REPO", "PACKAGE", "MIXED"}
_ALLOWED_SOURCE_STATUSES = {"VERIFIED", "STALE", "MISSING", "AMBIGUOUS", "CONFLICT"}
_ALLOWED_OUTCOMES = {"READY", "BLOCKED"}
_ALLOWED_RISK_LEVELS = {"R0", "R1", "R2", "R3", None}
_ALLOWED_REQUIRED_GATES = {"G0_CONTEXT", "G2_EXECUTION"}
_ALLOWED_ADDITIONAL_GATES = {"G5_DEPLOY", "G6_PRODUCTION_DATA"}
_ALLOWED_READ_FAILURE_CLASSIFICATIONS = {
    None,
    "NONE",
    "AGENT_PREPARATION_BLOCKED",
    "REPOSITORY_EVIDENCE_MISSING",
    "VALIDATION_FAILED",
}
_ALLOWED_BRANCH_BINDING_STATUS = {"BOUND", "REQUIRED_AT_G2", "UNBOUND"}
_ALLOWED_WRITE_AUTHORITY_GATES = {"G2_EXECUTION", "G5_DEPLOY", "G6_PRODUCTION_DATA"}

_AUTHORITY_FIELDS = (
    "write_authority_granted",
    "commit_authority_granted",
    "push_authority_granted",
    "pr_authority_granted",
    "merge_authority_granted",
    "deployment_authority_granted",
    "production_authority_granted",
)


def _canonicalize(payload: Any) -> Any:
    """Normalize semantic arrays and mappings before canonical JSON hashing."""
    if isinstance(payload, Mapping):
        return {str(key): _canonicalize(value) for key, value in payload.items()}
    if isinstance(payload, list):
        normalized = [_canonicalize(item) for item in payload]
        unique: dict[str, Any] = {}
        for item in normalized:
            unique[json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)] = item
        return [unique[key] for key in sorted(unique)]
    return payload


def canonical_json(payload: Any) -> str:
    return json.dumps(_canonicalize(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _sorted_unique_strings(values: Iterable[Any]) -> List[str]:
    return sorted({str(value) for value in values if isinstance(value, str) and value})


def _sorted_reason_codes(values: Iterable[Any]) -> List[str]:
    return _sorted_unique_strings(values)


def _matches_protected_key(key: str) -> bool:
    normalized = str(key).strip().lower()
    return normalized in _PROTECTED_TERMINALS or any(
        normalized.endswith("_" + terminal) for terminal in _PROTECTED_TERMINALS
    )


def _json_pointer_escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _json_pointer_unescape(key: str) -> str:
    return key.replace("~1", "/").replace("~0", "~")


def _resolve_pointer(obj: Any, pointer: str) -> Tuple[Any, str] | None:
    if not pointer.startswith("/") or pointer == "/":
        return None
    parts = [_json_pointer_unescape(part) for part in pointer.split("/")[1:]]
    cursor = obj
    for part in parts[:-1]:
        if isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
        elif isinstance(cursor, list):
            try:
                index = int(part)
            except ValueError:
                return None
            if not 0 <= index < len(cursor):
                return None
            cursor = cursor[index]
        else:
            return None
    return cursor, parts[-1]


def validate_redaction_directives(obj: Any, directives: List[Dict[str, str]]) -> bool:
    if not isinstance(directives, list):
        return False
    for directive in directives:
        if not isinstance(directive, dict):
            return False
        if set(directive) != {"json_pointer", "classification", "reason_code", "replacement"}:
            return False
        pointer = directive.get("json_pointer")
        classification = directive.get("classification")
        reason_code = directive.get("reason_code")
        replacement = directive.get("replacement")
        if not isinstance(pointer, str) or pointer in _IMMUTABLE_POINTERS:
            return False
        if classification not in _ALLOWED_REDACTION_CLASSIFICATIONS:
            return False
        if not isinstance(reason_code, str) or not reason_code:
            return False
        if replacement != _REDACTED:
            return False
        resolved = _resolve_pointer(obj, pointer)
        if resolved is None:
            return False
        parent, key = resolved
        if isinstance(parent, dict):
            if key not in parent:
                return False
        elif isinstance(parent, list):
            try:
                index = int(key)
            except ValueError:
                return False
            if not 0 <= index < len(parent):
                return False
        else:
            return False
    return True


def _apply_pointers(obj: Any, directives: List[Dict[str, str]]) -> Tuple[Any, List[Dict[str, Any]]]:
    redactions: List[Dict[str, Any]] = []
    for directive in directives:
        pointer = directive["json_pointer"]
        resolved = _resolve_pointer(obj, pointer)
        if resolved is None:  # guarded by validate_redaction_directives
            continue
        parent, key = resolved
        if isinstance(parent, dict):
            parent[key] = _REDACTED
        else:
            parent[int(key)] = _REDACTED
        redactions.append(
            {
                "pointer": pointer,
                "classification": directive["classification"],
                "replacement": _REDACTED,
                "reason_code": directive["reason_code"],
            }
        )
    return obj, redactions


def _redact_node(node: Any, pointer: str = "") -> Tuple[Any, List[Dict[str, Any]]]:
    if isinstance(node, dict):
        output: Dict[str, Any] = {}
        redactions: List[Dict[str, Any]] = []
        for key, value in node.items():
            child_pointer = f"{pointer}/{_json_pointer_escape(str(key))}"
            if _matches_protected_key(str(key)):
                output[key] = _REDACTED
                redactions.append(
                    {
                        "pointer": child_pointer,
                        "classification": "CREDENTIAL",
                        "replacement": _REDACTED,
                        "reason_code": "AUTO_PROTECTED_KEY_MATCH",
                    }
                )
                continue
            child, child_redactions = _redact_node(value, child_pointer)
            output[key] = child
            redactions.extend(child_redactions)
        return output, redactions
    if isinstance(node, list):
        output: List[Any] = []
        redactions: List[Dict[str, Any]] = []
        for index, item in enumerate(node):
            child, child_redactions = _redact_node(item, f"{pointer}/{index}")
            output.append(child)
            redactions.extend(child_redactions)
        return output, redactions
    return node, []


def _unredacted_protected_pointer(node: Any, pointer: str = "") -> str | None:
    if isinstance(node, dict):
        for key, value in node.items():
            child_pointer = f"{pointer}/{_json_pointer_escape(str(key))}"
            if _matches_protected_key(str(key)) and value != _REDACTED:
                return child_pointer
            found = _unredacted_protected_pointer(value, child_pointer)
            if found:
                return found
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found = _unredacted_protected_pointer(item, f"{pointer}/{index}")
            if found:
                return found
    return None


def apply_redactions(
    payload: Dict[str, Any], directives: List[Dict[str, str]]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    obj = copy.deepcopy(payload)
    obj, explicit = _apply_pointers(obj, directives)
    obj, automatic = _redact_node(obj)
    redactions = explicit + automatic
    redactions = sorted(
        {canonical_json(item): item for item in redactions}.values(),
        key=lambda item: (item["pointer"], item["classification"], item["reason_code"]),
    )
    return obj, redactions


def _semantic_digest(artifact: Mapping[str, Any], excluded: set[str]) -> str:
    payload = {
        key: value
        for key, value in artifact.items()
        if key not in excluded and not str(key).startswith("_")
    }
    return digest_payload(payload)


def compute_risk_decision_digest(risk_profile: Mapping[str, Any]) -> str:
    return f"sha256:{_semantic_digest(risk_profile, {'classified_at', 'decision_digest'})}"


def compute_scope_digest(scope: Mapping[str, Any]) -> str:
    return f"sha256:{_semantic_digest(scope, {'scope_hash', 'observed_at', 'evaluated_at', 'created_at'})}"


def _digest_hex(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = _SHA256.fullmatch(value)
    return match.group(1) if match else None


def _digest_matches(value: Any, computed: str) -> bool:
    supplied = _digest_hex(value)
    expected = _digest_hex(computed)
    return supplied is not None and supplied == expected


def _valid_string_list(
    value: Any,
    *,
    allowed_values: Optional[setAny] = None,
    allow_empty: bool = True,
) -> bool:
    if not isinstance(value, list):
        return False
    if not all_empty and not value:
        return False
    if not all(isinstance(item, str) and item for item in value):
        return False
    if len(value) != len(set(value)):
        return False
    if allowed_values is not None and not set(value).issubset(allowed_values):
        return False
    return True


def _valid_source_bindings(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    seen: set[str] = set()
    for binding in value:
        if not isinstance(binding, dict):
            return False
        if set(binding) != {"source_type", "ref", "revision", "status"}:
            return False
        if not all(isinstance(binding.get(key), str) and binding.get(key) for key in binding):
            return False
        if binding["status"] not in _ALLOWED_SOURCE_STATUSES:
            return False
        key = canonical_json(binding)
        if key in seen:
            return False
        seen.add(key)
    return True


def _missing_fields(mapping: Mapping[str, Any], required: Iterable[str]) -> List[str]:
    return sorted(field for field in required if field not in mapping)


def _artifact_contract_invalid(artifact: Mapping[str, Any], artifact_type: str) -> bool:
    return artifact.get("artifact_type") != artifact_type or str(artifact.get("schema_version")) != "1.0"


def _binding_mismatch(
    artifact: Mapping[str, Any], *, task_id: str, repository: str, base_sha: str
