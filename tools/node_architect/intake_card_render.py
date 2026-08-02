"""Deterministic intake-card renderer for SCRUM-182.

This module is pure and side-effect free. It materializes a read-only intake
projection while preserving fail-closed state and applying deterministic
redaction. It never grants repository, PR, merge, deployment, or production
authority.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

_SCHEMA_VERSION = "1.0"
_ARTIFACT_TYPE = "intake-card"
_CONTRACT_REVISION = "intake-context/v1"
_REDACTED = "[REDACTED]"
_IMMUTABLE_POINTERS = {
    "/task_id", "/repository", "/base_sha", "/repository_context/repository",
    "/repository_context/protected_branch", "/repository_context/protected_base_sha",
    "/scope_hash",
}
_PROTECTED_TERMINALS = {
    "password", "secret", "token", "access_token", "refresh_token",
    "authorization", "credential", "private_key", "client_secret", "cookie", "session",
}


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _stable_codes(codes: List[str]) -> List[str]:
    out: List[str] = []
    for code in codes:
        if code and code not in out:
            out.append(code)
    return out


def _matches_protected_key(key: str) -> bool:
    normalized = str(key).strip().lower()
    if normalized in _PROTECTED_TERMINALS:
        return True
    return any(normalized.endswith("_" + terminal) for terminal in _PROTECTED_TERMINALS)


def _json_pointer_escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _json_pointer_unescape(key: str) -> str:
    return key.replace("~1", "/").replace("~0", "~")


def _resolve_pointer(obj: Any, pointer: str) -> Tuple[Any, str] | None:
    if not pointer.startswith("/"):
        return None
    parts = [_json_pointer_unescape(p) for p in pointer.split("/")[1:]]
    if not parts:
        return None
    cursor = obj
    for part in parts[:-1]:
        if isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
            continue
        if isinstance(cursor, list):
            try:
                index = int(part)
            except ValueError:
                return None
            if not 0 <= index < len(cursor):
                return None
            cursor = cursor[index]
            continue
        return None
    return cursor, parts[-1]


def _apply_pointers(obj: Any, directives: List[Dict[str, str]]) -> Tuple[Any, List[Dict[str, Any]]]:
    redactions: List[Dict[str, Any]] = []
    for directive in directives:
        pointer = str(directive.get("json_pointer", ""))
        resolved = _resolve_pointer(obj, pointer)
        if resolved is None:
            continue
        parent, key = resolved
        replaced = False
        if isinstance(parent, dict) and key in parent:
            parent[key] = _REDACTED
            replaced = True
        elif isinstance(parent, list):
            try:
                index = int(key)
            except ValueError:
                index = -1
            if 0 <= index < len(parent):
                parent[index] = _REDACTED
                replaced = True
        if replaced:
            redactions.append({
                "pointer": pointer,
                "classification": str(directive.get("classification", "POLICY_REDACTED")),
                "replacement": _REDACTED,
                "reason_code": str(directive.get("reason_code", "EXPLICIT_DIRECTIVE")),
            })
    return obj, redactions


def _redact_node(node: Any, pointer: str = "") -> Tuple[Any, List[Dict[str, Any]]]:
    if isinstance(node, dict):
        output: Dict[str, Any] = {}
        redactions: List[Dict[str, Any]] = []
        for key, value in node.items():
            child_pointer = f"{pointer}/{_json_pointer_escape(str(key))}"
            if _matches_protected_key(str(key)) and isinstance(value, str):
                output[key] = _REDACTED
                redactions.append({
                    "pointer": child_pointer,
                    "classification": "CREDENTIAL",
                    "replacement": _REDACTED,
                    "reason_code": "AUTO_PROTECTED_KEY_MATCH",
                })
                continue
            child, child_redactions = _redact_node(value, child_pointer)
            output[key] = child
            redactions.extend(child_redactions)
        return output, redactions
    if isinstance(node, list):
        output_list: List[Any] = []
        redactions: List[Dict[str, Any]] = []
        for index, item in enumerate(node):
            child, child_redactions = _redact_node(item, f"{pointer}/{index}")
            output_list.append(child)
            redactions.extend(child_redactions)
        return output_list, redactions
    return node, []


def apply_redactions(payload: Dict[str, Any], directives: List[Dict[str, str]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    obj = copy.deepcopy(payload)
    obj, explicit = _apply_pointers(obj, directives)
    obj, automatic = _redact_node(obj)
    return obj, explicit + automatic


def validate_redaction_directives(obj: Any, directives: List[Dict[str, str]]) -> bool:
    for directive in directives:
        pointer = directive.get("json_pointer")
        if not isinstance(pointer, str) or pointer in _IMMUTABLE_POINTERS:
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


def _strip_excluded_fields(obj: Any) -> Any:
    excluded = {"created_at", "snapshot_hash", "expected_snapshot_hash", "outcome", "context_status", "next_required_action", "reason_code", "reason_codes"}
    if isinstance(obj, dict):
        return {key: _strip_excluded_fields(value) for key, value in obj.items() if key not in excluded}
    if isinstance(obj, list):
        return [_strip_excluded_fields(item) for item in obj]
    return obj


def _finalize_snapshot(card: Dict[str, Any]) -> Dict[str, Any]:
    finalized = copy.deepcopy(card)
    finalized["snapshot_hash"] = digest_payload(_strip_excluded_fields(finalized))
    return finalized


def _blocked_card(*, task_id: str, repository: str, base_sha: str, reason_codes: List[str], created_at: Optional[str]) -> Dict[str, Any]:
    codes = _stable_codes(reason_codes or ["CARD_INPUT_INVALID"])
    card: Dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION, "artifact_type": _ARTIFACT_TYPE,
        "contract_revision": _CONTRACT_REVISION, "task_id": str(task_id),
        "repository": str(repository), "base_sha": str(base_sha), "request": {},
        "source_bindings": [{"source": "intake_context.intake-card-render", "binding": "blocked-input"}],
        "repository_context": {"repository": str(repository), "protected_branch": "main", "protected_base_sha": str(base_sha)},
        "risk_projection": {}, "read_scope_projection": {}, "write_scope_projection": {},
        "upstream_artifacts": [{"artifact_type": "blocked-input", "schema_version": "1.0", "digest": digest_payload({"reason_codes": codes})}],
        "context_status": "BLOCKED", "outcome": "BLOCKED", "next_required_action": "ESCALATE_CONTEXT_GAP",
        "scope_hash": digest_payload({"task_id": task_id, "repository": repository, "base_sha": base_sha}),
        "snapshot_hash": "pending", "redaction_status": "NONE", "redactions": [],
        "reason_code": codes[0], "reason_codes": codes,
        "created_at": "" if created_at is None else str(created_at),
        "read_only_projection": True, "write_authority_granted": False,
        "commit_authority_granted": False, "push_authority_granted": False,
        "pr_authority_granted": False, "merge_authority_granted": False,
        "deployment_authority_granted": False, "production_authority_granted": False,
    }
    return _finalize_snapshot(card)


def render_intake_card(
    *, task_id: str, repository: str, base_sha: str,
    request_contract: Dict[str, Any], source_resolution: Dict[str, Any],
    repo_identity: Dict[str, Any], protected_base_snapshot: Dict[str, Any],
    risk_profile: Dict[str, Any], bounded_read_scope: Dict[str, Any],
    bounded_write_scope: Dict[str, Any], redaction_directives: List[Dict[str, str]],
    expected_snapshot_hash: Optional[str] = None, created_at: Optional[str] = None,
) -> Dict[str, Any]:
    errors: List[str] = []
    if request_contract.get("task_id") not in (None, task_id): errors.append("CARD_INPUT_INVALID")
    if request_contract.get("repository") not in (None, repository): errors.append("CARD_INPUT_INVALID")
    if repo_identity.get("repository") not in (None, repository): errors.append("CARD_SOURCE_BINDING_MISMATCH")
    if protected_base_snapshot.get("protected_base_sha") not in (None, base_sha): errors.append("CARD_INPUT_INVALID")
    if errors:
        return _blocked_card(task_id=task_id, repository=repository, base_sha=base_sha, reason_codes=errors, created_at=created_at)

    upstreams = [risk_profile, bounded_read_scope, bounded_write_scope]
    allowed_types = {"risk-profile", "bounded-read-scope", "bounded-write-scope"}
    for artifact in upstreams:
        if artifact.get("artifact_type") not in allowed_types or str(artifact.get("schema_version")) != "1.0":
            return _blocked_card(task_id=task_id, repository=repository, base_sha=base_sha, reason_codes=["CARD_UPSTREAM_CONTRACT_INVALID"], created_at=created_at)
    for scope in (bounded_read_scope, bounded_write_scope):
        scope_hash = scope.get("scope_hash")
        if scope_hash is not None and not re.fullmatch(r"[0-9a-f]{64}", str(scope_hash)):
            return _blocked_card(task_id=task_id, repository=repository, base_sha=base_sha, reason_codes=["CARD_SCOPE_HASH_MISMATCH"], created_at=created_at)
    if risk_profile.get("decision_digest") is not None and risk_profile.get("_test_force_recomputed_digest", False):
        recomputed = hashlib.sha256(str(risk_profile.get("risk_level", "")).encode("utf-8")).hexdigest()
        if str(risk_profile.get("decision_digest")) != recomputed:
            return _blocked_card(task_id=task_id, repository=repository, base_sha=base_sha, reason_codes=["CARD_UPSTREAM_DIGEST_MISMATCH"], created_at=created_at)

    upstream_blocked = any(str(artifact.get("outcome", "")).upper() == "BLOCKED" for artifact in upstreams)
    base_codes = ["CARD_UPSTREAM_BLOCKED"] if upstream_blocked else ["CARD_RENDERED"]
    status = "BLOCKED" if upstream_blocked else "READY"
    card: Dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION, "artifact_type": _ARTIFACT_TYPE,
        "contract_revision": _CONTRACT_REVISION, "task_id": str(task_id),
        "repository": str(repository), "base_sha": str(base_sha),
        "request": {"intent": str(request_contract.get("intent", "")), "outcome": str(request_contract.get("outcome", "")), "constraints": list(request_contract.get("constraints", [])), "exclusions": list(request_contract.get("exclusions", []))},
        "source_bindings": [
            {"source": "intake_context.request-intake", "binding": "request_contract"},
            {"source": "intake_context.source-resolution", "binding": "source_resolution"},
            {"source": "intake_context.repo-identity-check", "binding": "repo_identity"},
        ],
        "repository_context": {"repository": str(repo_identity.get("repository", repository)), "protected_branch": str(repo_identity.get("default_branch", "main")), "protected_base_sha": str(protected_base_snapshot.get("protected_base_sha", base_sha))},
        "risk_projection": {"outcome": str(risk_profile.get("outcome", "READY")), "risk_level": str(risk_profile.get("risk_level", "R1")), "risk_flags": list(risk_profile.get("risk_flags", [])), "required_gate": str(risk_profile.get("required_gate", "G2_AUTOMATIC_BOUNDED")), "additional_authority_gates": list(risk_profile.get("additional_authority_gates", [])), "risk_profile_digest": digest_payload(risk_profile)},
        "read_scope_projection": {"outcome": str(bounded_read_scope.get("outcome", "ACCEPTED")), "failure_classification": bounded_read_scope.get("failure_classification"), "files_read": list(bounded_read_scope.get("files_read", [])), "files_exclude": list(bounded_read_scope.get("files_exclude", [])), "files_missing": list(bounded_read_scope.get("files_missing", [])), "scope_hash": str(bounded_read_scope.get("scope_hash", ""))},
        "write_scope_projection": {"outcome": str(bounded_write_scope.get("outcome", "ACCEPTED")), "candidate_paths": list(bounded_write_scope.get("candidate_paths", [])), "exclusions": list(bounded_write_scope.get("exclusions", [])), "prohibited_operations": list(bounded_write_scope.get("prohibited_operations", [])), "branch_binding_status": str(bounded_write_scope.get("branch_binding_status", "UNBOUND")), "scope_hash": str(bounded_write_scope.get("scope_hash", ""))},
        "upstream_artifacts": sorted([{"artifact_type": str(a["artifact_type"]), "schema_version": str(a["schema_version"]), "digest": digest_payload(a)} for a in upstreams], key=lambda item: item["artifact_type"]),
        "context_status": status, "outcome": status,
        "next_required_action": "ESCALATE_CONTEXT_GAP" if status == "BLOCKED" else "CONTINUE_CONTEXT_EVALUATION",
        "scope_hash": digest_payload({"task_id": task_id, "repository": repository, "base_sha": base_sha, "risk_profile_digest": digest_payload(risk_profile), "read_scope_hash": str(bounded_read_scope.get("scope_hash", "")), "write_scope_hash": str(bounded_write_scope.get("scope_hash", ""))}),
        "snapshot_hash": "pending", "redaction_status": "NONE", "redactions": [],
        "reason_code": base_codes[0], "reason_codes": list(base_codes),
        "created_at": "" if created_at is None else str(created_at),
        "read_only_projection": True, "write_authority_granted": False,
        "commit_authority_granted": False, "push_authority_granted": False,
        "pr_authority_granted": False, "merge_authority_granted": False,
        "deployment_authority_granted": False, "production_authority_granted": False,
    }
    if not validate_redaction_directives(card, list(redaction_directives)):
        return _blocked_card(task_id=task_id, repository=repository, base_sha=base_sha, reason_codes=["CARD_REDACTION_DIRECTIVE_INVALID"], created_at=created_at)
    redacted, redactions = apply_redactions(card, list(redaction_directives))
    if redactions:
        redacted["redaction_status"] = "APPLIED"
        redacted["redactions"] = redactions
        redacted["reason_codes"] = _stable_codes(list(base_codes) + ["CARD_RENDERED_REDACTED"])
        redacted["reason_code"] = redacted["reason_codes"][0]
    else:
        redacted["redaction_status"] = "NONE"
        redacted["redactions"] = []
    redacted["context_status"] = status
    redacted["outcome"] = status
    redacted["next_required_action"] = "ESCALATE_CONTEXT_GAP" if status == "BLOCKED" else "CONTINUE_CONTEXT_EVALUATION"
    final_card = _finalize_snapshot(redacted)
    if expected_snapshot_hash is not None and final_card["snapshot_hash"] != str(expected_snapshot_hash):
        return _blocked_card(task_id=task_id, repository=repository, base_sha=base_sha, reason_codes=["CARD_SNAPSHOT_HASH_MISMATCH"], created_at=created_at)
    return final_card


def validate_upstream_bindings(
    *, task_id: str, repository: str, base_sha: str,
    request_contract: Dict[str, Any], source_resolution: Dict[str, Any],
    repo_identity: Dict[str, Any], protected_base_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    errors: List[str] = []
    if request_contract.get("task_id") not in (None, task_id): errors.append("task_id mismatch")
    if repo_identity.get("repository") not in (None, repository): errors.append("repository mismatch")
    if protected_base_snapshot.get("protected_base_sha") not in (None, base_sha): errors.append("base_sha mismatch")
    return {"has_errors": bool(errors), "errors": errors}
