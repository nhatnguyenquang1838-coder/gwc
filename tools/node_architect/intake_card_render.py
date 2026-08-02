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
        if resolved is None:
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


def _valid_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _missing_fields(mapping: Mapping[str, Any], required: Iterable[str]) -> List[str]:
    return sorted(field for field in required if field not in mapping)


def _artifact_contract_invalid(artifact: Mapping[str, Any], artifact_type: str) -> bool:
    return artifact.get("artifact_type") != artifact_type or str(artifact.get("schema_version")) != "1.0"


def _binding_mismatch(
    artifact: Mapping[str, Any], *, task_id: str, repository: str, base_sha: str
) -> bool:
    bindings = {
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "protected_base_sha": base_sha,
    }
    return any(key in artifact and artifact.get(key) != expected for key, expected in bindings.items())


def validate_upstream_bindings(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    request_contract: Dict[str, Any],
    source_resolution: Dict[str, Any],
    repo_identity: Dict[str, Any],
    protected_base_snapshot: Dict[str, Any],
    risk_profile: Optional[Dict[str, Any]] = None,
    bounded_read_scope: Optional[Dict[str, Any]] = None,
    bounded_write_scope: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    errors: List[str] = []
    artifacts = [request_contract, source_resolution, repo_identity, protected_base_snapshot]
    artifacts.extend(
        artifact
        for artifact in (risk_profile, bounded_read_scope, bounded_write_scope)
        if artifact is not None
    )
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            errors.append("non-mapping upstream artifact")
            continue
        if _binding_mismatch(artifact, task_id=task_id, repository=repository, base_sha=base_sha):
            errors.append("upstream source binding mismatch")
    return {"has_errors": bool(errors), "errors": sorted(set(errors))}


def _source_revision_projection(source_resolution: Mapping[str, Any]) -> Dict[str, Any]:
    bindings = source_resolution.get("source_bindings", [])
    if not isinstance(bindings, list):
        bindings = []
    return {
        "source_mode": str(source_resolution.get("source_mode", source_resolution.get("mode", ""))),
        "revision": str(source_resolution.get("revision", "")),
        "bindings": _canonicalize(bindings),
        "artifact_revision": f"{source_resolution.get('artifact_type', '')}/{source_resolution.get('schema_version', '')}",
    }


def _safe_task_id(value: Any) -> str:
    return value if isinstance(value, str) and value else "UNKNOWN"


def _safe_repository(value: Any) -> str:
    return value if isinstance(value, str) and _REPOSITORY.fullmatch(value) else "invalid/invalid"


def _safe_sha(value: Any) -> str:
    return value if isinstance(value, str) and _SHA40.fullmatch(value) else "0" * 40


def _empty_projection_card(
    *,
    task_id: Any,
    repository: Any,
    base_sha: Any,
    reason_codes: List[str],
    created_at: Optional[str],
    redaction_status: str = "NONE",
) -> Dict[str, Any]:
    safe_task = _safe_task_id(task_id)
    safe_repo = _safe_repository(repository)
    safe_sha = _safe_sha(base_sha)
    codes = _sorted_reason_codes(reason_codes or ["CARD_INPUT_INVALID"])
    primary = reason_codes[0] if reason_codes else "CARD_INPUT_INVALID"
    card: Dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "artifact_type": _ARTIFACT_TYPE,
        "contract_revision": _CONTRACT_REVISION,
        "task_id": safe_task,
        "repository": safe_repo,
        "base_sha": safe_sha,
        "request": {"intent": "", "outcome": "", "constraints": [], "exclusions": []},
        "source_bindings": [
            {
                "source": "intake_context.intake-card-render",
                "binding": "blocked-input",
                "revision": _CONTRACT_REVISION,
            }
        ],
        "repository_context": {
            "repository": safe_repo,
            "protected_branch": "main",
            "protected_base_sha": safe_sha,
        },
        "risk_projection": {
            "outcome": "BLOCKED",
            "risk_level": None,
            "risk_flags": [],
            "required_gate": "",
            "additional_authority_gates": [],
            "risk_profile_digest": "",
        },
        "read_scope_projection": {
            "outcome": "BLOCKED",
            "failure_classification": None,
            "files_read": [],
            "files_exclude": [],
            "files_missing": [],
            "read_scope_hash": "",
        },
        "write_scope_projection": {
            "outcome": "BLOCKED",
            "candidate_paths": [],
            "exclusions": [],
            "prohibited_operations": [],
            "branch_binding_status": "",
            "required_authority_gates": [],
            "write_scope_hash": "",
        },
        "upstream_artifacts": [
            {
                "artifact_type": "blocked-input",
                "schema_version": "1.0",
                "digest": f"sha256:{digest_payload({'reason_codes': codes})}",
            }
        ],
        "context_status": "BLOCKED",
        "outcome": "BLOCKED",
        "next_required_action": "ESCALATE_CONTEXT_GAP",
        "scope_hash": digest_payload(
            {"task_id": safe_task, "repository": safe_repo, "base_sha": safe_sha}
        ),
        "snapshot_hash": "pending",
        "redaction_status": redaction_status,
        "redactions": [],
        "reason_code": primary,
        "reason_codes": codes,
        "created_at": "" if created_at is None else str(created_at),
        "read_only_projection": True,
        **{field: False for field in _AUTHORITY_FIELDS},
    }
    return _finalize_snapshot(card)


def _snapshot_payload(card: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in card.items() if key not in {"created_at", "snapshot_hash"}}


def _finalize_snapshot(card: Dict[str, Any]) -> Dict[str, Any]:
    finalized = copy.deepcopy(card)
    finalized["snapshot_hash"] = digest_payload(_snapshot_payload(finalized))
    return finalized


def _validate_required_contracts(
    *,
    request_contract: Mapping[str, Any],
    source_resolution: Mapping[str, Any],
    repo_identity: Mapping[str, Any],
    protected_base_snapshot: Mapping[str, Any],
    risk_profile: Mapping[str, Any],
    bounded_read_scope: Mapping[str, Any],
    bounded_write_scope: Mapping[str, Any],
) -> str | None:
    requirements = (
        (request_contract, ("intent", "outcome", "constraints", "exclusions")),
        (source_resolution, ("artifact_type", "schema_version", "source_mode")),
        (repo_identity, ("artifact_type", "schema_version", "repository", "default_branch")),
        (protected_base_snapshot, ("artifact_type", "schema_version", "protected_base_sha")),
        (
            risk_profile,
            (
                "artifact_type",
                "schema_version",
                "decision_digest",
                "risk_level",
                "risk_flags",
                "required_gate",
                "additional_authority_gates",
            ),
        ),
        (
            bounded_read_scope,
            (
                "artifact_type",
                "schema_version",
                "outcome",
                "failure_classification",
                "files_read",
                "files_exclude",
                "files_missing",
                "scope_hash",
            ),
        ),
        (
            bounded_write_scope,
            (
                "artifact_type",
                "schema_version",
                "outcome",
                "candidate_paths",
                "exclusions",
                "prohibited_operations",
                "branch_binding_status",
                "scope_hash",
            ),
        ),
    )
    if any(_missing_fields(artifact, required) for artifact, required in requirements):
        return "CARD_REQUIRED_FIELD_MISSING"

    if (
        _artifact_contract_invalid(source_resolution, "source-resolution")
        or _artifact_contract_invalid(repo_identity, "repo-identity")
        or _artifact_contract_invalid(protected_base_snapshot, "protected-base-snapshot")
        or _artifact_contract_invalid(risk_profile, "risk-profile")
        or _artifact_contract_invalid(bounded_read_scope, "bounded-read-scope")
        or _artifact_contract_invalid(bounded_write_scope, "bounded-write-scope")
    ):
        return "CARD_UPSTREAM_CONTRACT_INVALID"

    if not all(
        (
            isinstance(request_contract.get("intent"), str),
            isinstance(request_contract.get("outcome"), str),
            _valid_string_list(request_contract.get("constraints")),
            _valid_string_list(request_contract.get("exclusions")),
            isinstance(source_resolution.get("source_mode"), str),
            isinstance(repo_identity.get("default_branch"), str),
            _valid_string_list(risk_profile.get("risk_flags")),
            isinstance(risk_profile.get("required_gate"), str),
            _valid_string_list(risk_profile.get("additional_authority_gates")),
            _valid_string_list(bounded_read_scope.get("files_read")),
            _valid_string_list(bounded_read_scope.get("files_exclude")),
            _valid_string_list(bounded_read_scope.get("files_missing")),
            _valid_string_list(bounded_write_scope.get("candidate_paths")),
            _valid_string_list(bounded_write_scope.get("exclusions")),
            _valid_string_list(bounded_write_scope.get("prohibited_operations")),
            isinstance(bounded_write_scope.get("branch_binding_status"), str),
        )
    ):
        return "CARD_UPSTREAM_CONTRACT_INVALID"
    return None


def render_intake_card(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    request_contract: Dict[str, Any],
    source_resolution: Dict[str, Any],
    repo_identity: Dict[str, Any],
    protected_base_snapshot: Dict[str, Any],
    risk_profile: Dict[str, Any],
    bounded_read_scope: Dict[str, Any],
    bounded_write_scope: Dict[str, Any],
    redaction_directives: List[Dict[str, str]],
    expected_snapshot_hash: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    mappings = (
        request_contract,
        source_resolution,
        repo_identity,
        protected_base_snapshot,
        risk_profile,
        bounded_read_scope,
        bounded_write_scope,
    )
    if (
        not isinstance(task_id, str)
        or not task_id
        or not isinstance(repository, str)
        or not _REPOSITORY.fullmatch(repository)
        or not isinstance(base_sha, str)
        or not _SHA40.fullmatch(base_sha)
        or not all(isinstance(item, dict) for item in mappings)
        or not isinstance(redaction_directives, list)
    ):
        return _empty_projection_card(
            task_id=task_id,
            repository=repository,
            base_sha=base_sha,
            reason_codes=["CARD_INPUT_INVALID"],
            created_at=created_at,
        )

    contract_error = _validate_required_contracts(
        request_contract=request_contract,
        source_resolution=source_resolution,
        repo_identity=repo_identity,
        protected_base_snapshot=protected_base_snapshot,
        risk_profile=risk_profile,
        bounded_read_scope=bounded_read_scope,
        bounded_write_scope=bounded_write_scope,
    )
    if contract_error:
        return _empty_projection_card(
            task_id=task_id,
            repository=repository,
            base_sha=base_sha,
            reason_codes=[contract_error],
            created_at=created_at,
        )

    binding_result = validate_upstream_bindings(
        task_id=task_id,
        repository=repository,
        base_sha=base_sha,
        request_contract=request_contract,
        source_resolution=source_resolution,
        repo_identity=repo_identity,
        protected_base_snapshot=protected_base_snapshot,
        risk_profile=risk_profile,
        bounded_read_scope=bounded_read_scope,
        bounded_write_scope=bounded_write_scope,
    )
    if binding_result["has_errors"]:
        return _empty_projection_card(
            task_id=task_id,
            repository=repository,
            base_sha=base_sha,
            reason_codes=["CARD_SOURCE_BINDING_MISMATCH"],
            created_at=created_at,
        )

    computed_risk_digest = compute_risk_decision_digest(risk_profile)
    if not _digest_matches(risk_profile.get("decision_digest"), computed_risk_digest):
        return _empty_projection_card(
            task_id=task_id,
            repository=repository,
            base_sha=base_sha,
            reason_codes=["CARD_UPSTREAM_DIGEST_MISMATCH"],
            created_at=created_at,
        )

    scope_errors: List[str] = []
    if not _digest_matches(bounded_read_scope.get("scope_hash"), compute_scope_digest(bounded_read_scope)):
        scope_errors.append("CARD_SCOPE_HASH_MISMATCH")
    if not _digest_matches(bounded_write_scope.get("scope_hash"), compute_scope_digest(bounded_write_scope)):
        scope_errors.append("CARD_SCOPE_HASH_MISMATCH")
    if scope_errors:
        return _empty_projection_card(
            task_id=task_id,
            repository=repository,
            base_sha=base_sha,
            reason_codes=["CARD_UPSTREAM_DIGEST_MISMATCH", *scope_errors],
            created_at=created_at,
        )

    source_revisions = _source_revision_projection(source_resolution)
    request_projection = {
        "intent": request_contract["intent"],
        "outcome": request_contract["outcome"],
        "constraints": _sorted_unique_strings(request_contract["constraints"]),
        "exclusions": _sorted_unique_strings(request_contract["exclusions"]),
    }
    source_binding_rows = [
        {
            "source": "intake_context.request-intake",
            "binding": "request_contract",
            "revision": str(request_contract.get("revision", request_contract.get("schema_version", "1.0"))),
        },
        {
            "source": "intake_context.source-resolution",
            "binding": "source_resolution",
            "revision": str(source_resolution.get("revision", source_resolution.get("schema_version", "1.0"))),
            "mode": source_resolution["source_mode"],
        },
        {
            "source": "intake_context.repo-identity-check",
            "binding": "repo_identity",
            "revision": str(repo_identity.get("revision", repo_identity.get("schema_version", "1.0"))),
        },
        {
            "source": "intake_context.protected-base-capture",
            "binding": "protected_base_snapshot",
            "revision": str(
                protected_base_snapshot.get("revision", protected_base_snapshot.get("schema_version", "1.0"))
            ),
        },
    ]
    source_binding_rows = sorted(source_binding_rows, key=canonical_json)

    upstreams = [
        (request_contract, f"sha256:{_semantic_digest(request_contract, {'created_at'})}"),
        (source_resolution, f"sha256:{_semantic_digest(source_resolution, {'resolved_at', 'created_at'})}"),
        (repo_identity, f"sha256:{_semantic_digest(repo_identity, {'verified_at', 'created_at'})}"),
        (
            protected_base_snapshot,
            f"sha256:{_semantic_digest(protected_base_snapshot, {'captured_at', 'created_at'})}",
        ),
        (risk_profile, computed_risk_digest),
        (bounded_read_scope, str(bounded_read_scope["scope_hash"])),
        (bounded_write_scope, str(bounded_write_scope["scope_hash"])),
    ]
    upstream_artifacts = sorted(
        [
            {
                "artifact_type": str(artifact.get("artifact_type", "request-contract")),
                "schema_version": str(artifact.get("schema_version", "1.0")),
                "digest": digest,
            }
            for artifact, digest in upstreams
        ],
        key=lambda item: (item["artifact_type"], item["schema_version"], item["digest"]),
    )

    upstream_blocked = any(
        str(artifact.get("outcome", "")).upper() == "BLOCKED"
        for artifact in (risk_profile, bounded_read_scope, bounded_write_scope)
    )
    status = "BLOCKED" if upstream_blocked else "READY"
    primary_code = "CARD_UPSTREAM_BLOCKED" if upstream_blocked else "CARD_RENDERED"

    risk_digest_hex = _digest_hex(computed_risk_digest) or ""
    read_hash_hex = _digest_hex(bounded_read_scope["scope_hash"]) or ""
    write_hash_hex = _digest_hex(bounded_write_scope["scope_hash"]) or ""
    scope_hash = digest_payload(
        {
            "task_id": task_id,
            "repository": repository,
            "base_sha": base_sha,
            "canonical_source_revisions": source_revisions,
            "risk_profile_digest": risk_digest_hex,
            "read_scope_hash": read_hash_hex,
            "write_scope_hash": write_hash_hex,
        }
    )

    card: Dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "artifact_type": _ARTIFACT_TYPE,
        "contract_revision": _CONTRACT_REVISION,
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "request": request_projection,
        "source_bindings": source_binding_rows,
        "repository_context": {
            "repository": repo_identity["repository"],
            "protected_branch": str(repo_identity.get("protected_branch", repo_identity["default_branch"])),
            "protected_base_sha": protected_base_snapshot["protected_base_sha"],
        },
        "risk_projection": {
            "outcome": str(risk_profile.get("outcome", "READY")),
            "risk_level": risk_profile["risk_level"],
            "risk_flags": _sorted_unique_strings(risk_profile["risk_flags"]),
            "required_gate": risk_profile["required_gate"],
            "additional_authority_gates": _sorted_unique_strings(
                risk_profile["additional_authority_gates"]
            ),
            "risk_profile_digest": risk_digest_hex,
        },
        "read_scope_projection": {
            "outcome": str(bounded_read_scope["outcome"]),
            "failure_classification": bounded_read_scope["failure_classification"],
            "files_read": _sorted_unique_strings(bounded_read_scope["files_read"]),
            "files_exclude": _sorted_unique_strings(bounded_read_scope["files_exclude"]),
            "files_missing": _sorted_unique_strings(bounded_read_scope["files_missing"]),
            "read_scope_hash": read_hash_hex,
        },
        "write_scope_projection": {
            "outcome": str(bounded_write_scope["outcome"]),
            "candidate_paths": _sorted_unique_strings(bounded_write_scope["candidate_paths"]),
            "exclusions": _sorted_unique_strings(bounded_write_scope["exclusions"]),
            "prohibited_operations": _sorted_unique_strings(
                bounded_write_scope["prohibited_operations"]
            ),
            "branch_binding_status": bounded_write_scope["branch_binding_status"],
            "required_authority_gates": _sorted_unique_strings(
                bounded_write_scope.get("required_authority_gates", [])
            ),
            "write_scope_hash": write_hash_hex,
        },
        "upstream_artifacts": upstream_artifacts,
        "context_status": status,
        "outcome": status,
        "next_required_action": (
            "ESCALATE_CONTEXT_GAP" if status == "BLOCKED" else "CONTINUE_CONTEXT_EVALUATION"
        ),
        "scope_hash": scope_hash,
        "snapshot_hash": "pending",
        "redaction_status": "NONE",
        "redactions": [],
        "reason_code": primary_code,
        "reason_codes": [primary_code],
        "created_at": "" if created_at is None else str(created_at),
        "read_only_projection": True,
        **{field: False for field in _AUTHORITY_FIELDS},
    }

    if not validate_redaction_directives(card, redaction_directives):
        return _empty_projection_card(
            task_id=task_id,
            repository=repository,
            base_sha=base_sha,
            reason_codes=["CARD_REDACTION_DIRECTIVE_INVALID"],
            created_at=created_at,
            redaction_status="BLOCKED",
        )

    redacted, redactions = apply_redactions(card, redaction_directives)
    if _unredacted_protected_pointer(redacted):
        return _empty_projection_card(
            task_id=task_id,
            repository=repository,
            base_sha=base_sha,
            reason_codes=["CARD_REDACTION_REQUIRED"],
            created_at=created_at,
            redaction_status="BLOCKED",
        )

    if redactions:
        redacted["redaction_status"] = "APPLIED"
        redacted["redactions"] = redactions
        redacted["reason_code"] = "CARD_RENDERED_REDACTED" if status == "READY" else primary_code
        redacted["reason_codes"] = _sorted_reason_codes(
            [primary_code, "CARD_RENDERED_REDACTED"]
        )
    else:
        redacted["redaction_status"] = "NONE"
        redacted["redactions"] = []
        redacted["reason_codes"] = [primary_code]

    final_card = _finalize_snapshot(redacted)
    if expected_snapshot_hash is not None:
        expected = _digest_hex(expected_snapshot_hash)
        actual = _digest_hex(final_card["snapshot_hash"])
        if expected is None or expected != actual:
            return _empty_projection_card(
                task_id=task_id,
                repository=repository,
                base_sha=base_sha,
                reason_codes=["CARD_SNAPSHOT_HASH_MISMATCH"],
                created_at=created_at,
            )
    return final_card
