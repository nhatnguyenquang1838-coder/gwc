"""Pure deterministic SCRUM-182 intake-card renderer."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "intake-card"
CONTRACT_REVISION = "intake-context/v1"
REDACTED = "[REDACTED]"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")
PROTECTED_KEYS = {
    "password", "secret", "token", "access_token", "refresh_token",
    "authorization", "credential", "private_key", "client_secret", "cookie", "session",
}
REDACTION_CLASSES = {
    "SECRET", "CREDENTIAL", "TOKEN", "PRIVATE_KEY", "PERSONAL_SENSITIVE", "POLICY_REDACTED",
}
AUTHORITY_FIELDS = (
    "write_authority_granted", "commit_authority_granted", "push_authority_granted",
    "pr_authority_granted", "merge_authority_granted", "deployment_authority_granted",
    "production_authority_granted",
)
SOURCE_MODES = {"REPO", "PACKAGE", "MIXED"}
SOURCE_STATUSES = {"VERIFIED", "STALE", "MISSING", "AMBIGUOUS", "CONFLICT"}
OUTCOMES = {"READY", "BLOCKED"}
RISK_LEVELS = {"R0", "R1", "R2", "R3", None}
REQUIRED_GATES = {"G0_CONTEXT", "G2_EXECUTION"}
ADDITIONAL_GATES = {"G5_DEPLOY", "G6_PRODUCTION_DATA"}
READ_FAILURES = {None, "NONE", "AGENT_PREPARATION_BLOCKED", "REPOSITORY_EVIDENCE_MISSING", "VALIDATION_FAILED"}
BRANCH_STATUSES = {"BOUND", "REQUIRED_AT_G2", "UNBOUND"}
WRITE_GATES = {"G2_EXECUTION", "G5_DEPLOY", "G6_PRODUCTION_DATA"}
IMMUTABLE_POINTERS = {
    "/task_id", "/repository", "/base_sha", "/repository_context/repository",
    "/repository_context/protected_branch", "/repository_context/protected_base_sha", "/scope_hash",
}


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        items = [_canonical(v) for v in value]
        keyed = {json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False): v for v in items}
        return [keyed[k] for k in sorted(keyed)]
    return value


def canonical_json(payload: Any) -> str:
    return json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _semantic_digest(payload: Mapping[str, Any], excluded: set[str]) -> str:
    return digest_payload({k: v for k, v in payload.items() if k not in excluded and not str(k).startswith("_")})


def compute_risk_decision_digest(risk_profile: Mapping[str, Any]) -> str:
    return f"sha256:{_semantic_digest(risk_profile, {'classified_at', 'decision_digest'})}"


def compute_scope_digest(scope: Mapping[str, Any]) -> str:
    return f"sha256:{_semantic_digest(scope, {'scope_hash', 'observed_at', 'evaluated_at', 'created_at'})}"


def _digest_hex(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = SHA256.fullmatch(value)
    return match.group(1) if match else None


def _digest_matches(supplied: Any, computed: str) -> bool:
    return _digest_hex(supplied) is not None and _digest_hex(supplied) == _digest_hex(computed)


def _valid_strings(value: Any, *, allowed: set[Any] | None = None, allow_empty: bool = True) -> bool:
    if not isinstance(value, list) or (not allow_empty and not value):
        return False
    if not all(isinstance(item, str) and item for item in value) or len(value) != len(set(value)):
        return False
    return allowed is None or set(value).issubset(allowed)


def _sorted_strings(value: Iterable[Any]) -> list[str]:
    return sorted({item for item in value if isinstance(item, str) and item})


def _binding_mismatch(artifact: Mapping[str, Any], task_id: str, repository: str, base_sha: str) -> bool:
    expected = {"task_id": task_id, "repository": repository, "base_sha": base_sha, "protected_base_sha": base_sha}
    return any(key in artifact and artifact.get(key) != value for key, value in expected.items())


def validate_upstream_bindings(**kwargs: Any) -> dict[str, Any]:
    task_id = kwargs["task_id"]
    repository = kwargs["repository"]
    base_sha = kwargs["base_sha"]
    errors: list[str] = []
    for key in (
        "request_contract", "source_resolution", "repo_identity", "protected_base_snapshot",
        "risk_profile", "bounded_read_scope", "bounded_write_scope",
    ):
        artifact = kwargs.get(key)
        if artifact is None:
            continue
        if not isinstance(artifact, dict):
            errors.append("non-mapping upstream artifact")
        elif _binding_mismatch(artifact, task_id, repository, base_sha):
            errors.append("upstream source binding mismatch")
    return {"has_errors": bool(errors), "errors": sorted(set(errors))}


def _valid_source_bindings(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    seen: set[str] = set()
    for row in value:
        if not isinstance(row, dict) or set(row) != {"source_type", "ref", "revision", "status"}:
            return False
        if not all(isinstance(row[k], str) and row[k] for k in row):
            return False
        if row["status"] not in SOURCE_STATUSES:
            return False
        key = canonical_json(row)
        if key in seen:
            return False
        seen.add(key)
    return True


def _required(mapping: Mapping[str, Any], fields: Iterable[str]) -> bool:
    return all(field in mapping for field in fields)


def _contract_error(
    request: Mapping[str, Any], source: Mapping[str, Any], repo: Mapping[str, Any], protected: Mapping[str, Any],
    risk: Mapping[str, Any], read_scope: Mapping[str, Any], write_scope: Mapping[str, Any],
) -> str | None:
    common = ("artifact_type", "schema_version", "task_id", "repository", "base_sha")
    requirements = (
        (request, common + ("revision", "intent", "outcome", "constraints", "exclusions")),
        (source, common + ("revision", "source_mode", "source_bindings")),
        (repo, common + ("revision", "default_branch")),
        (protected, common + ("revision", "protected_base_sha")),
        (risk, common + ("decision_digest", "source_bindings", "outcome", "risk_level", "risk_flags", "required_gate", "additional_authority_gates")),
        (read_scope, common + ("source_bindings", "outcome", "failure_classification", "files_read", "files_exclude", "files_missing", "scope_hash")),
        (write_scope, common + ("source_bindings", "outcome", "candidate_paths", "exclusions", "prohibited_operations", "branch_binding_status", "required_authority_gates", "scope_hash")),
    )
    if any(not _required(item, fields) for item, fields in requirements):
        return "CARD_REQUIRED_FIELD_MISSING"
    expected_types = (
        (request, "request-contract"), (source, "source-resolution"), (repo, "repo-identity"),
        (protected, "protected-base-snapshot"), (risk, "risk-profile"),
        (read_scope, "bounded-read-scope"), (write_scope, "bounded-write-scope"),
    )
    if any(item.get("artifact_type") != kind or item.get("schema_version") != "1.0" for item, kind in expected_types):
        return "CARD_UPSTREAM_CONTRACT_INVALID"
    checks = (
        isinstance(request["revision"], str) and bool(request["revision"]),
        isinstance(request["intent"], str), isinstance(request["outcome"], str),
        _valid_strings(request["constraints"]), _valid_strings(request["exclusions"]),
        isinstance(source["revision"], str) and bool(source["revision"]), source["source_mode"] in SOURCE_MODES,
        _valid_source_bindings(source["source_bindings"]),
        isinstance(repo["revision"], str) and bool(repo["revision"]), isinstance(repo["default_branch"], str) and bool(repo["default_branch"]),
        isinstance(protected["revision"], str) and bool(protected["revision"]),
        risk["outcome"] in OUTCOMES, risk["risk_level"] in RISK_LEVELS,
        _valid_strings(risk["risk_flags"]), risk["required_gate"] in REQUIRED_GATES,
        _valid_strings(risk["additional_authority_gates"], allowed=ADDITIONAL_GATES),
        _valid_source_bindings(risk["source_bindings"]),
        read_scope["outcome"] in OUTCOMES, read_scope["failure_classification"] in READ_FAILURES,
        _valid_strings(read_scope["files_read"]), _valid_strings(read_scope["files_exclude"]), _valid_strings(read_scope["files_missing"]),
        _valid_source_bindings(read_scope["source_bindings"]),
        write_scope["outcome"] in OUTCOMES, _valid_strings(write_scope["candidate_paths"]),
        _valid_strings(write_scope["exclusions"]), _valid_strings(write_scope["prohibited_operations"]),
        write_scope["branch_binding_status"] in BRANCH_STATUSES,
        _valid_strings(write_scope["required_authority_gates"], allowed=WRITE_GATES),
        _valid_source_bindings(write_scope["source_bindings"]),
    )
    return None if all(checks) else "CARD_UPSTREAM_CONTRACT_INVALID"


def _safe_task(value: Any) -> str:
    return value if isinstance(value, str) and value else "UNKNOWN"


def _safe_repo(value: Any) -> str:
    return value if isinstance(value, str) and REPOSITORY.fullmatch(value) else "invalid/invalid"


def _safe_sha(value: Any) -> str:
    return value if isinstance(value, str) and SHA40.fullmatch(value) else "0" * 40


def _snapshot_payload(card: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in card.items() if k not in {"created_at", "snapshot_hash"}}


def _finalize(card: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(card)
    result["snapshot_hash"] = digest_payload(_snapshot_payload(result))
    return result


def _blocked(task_id: Any, repository: Any, base_sha: Any, codes: list[str], created_at: Any, redaction_status: str = "NONE") -> dict[str, Any]:
    task, repo, sha = _safe_task(task_id), _safe_repo(repository), _safe_sha(base_sha)
    unique = _sorted_strings(codes or ["CARD_INPUT_INVALID"])
    primary = codes[0] if codes else "CARD_INPUT_INVALID"
    card = {
        "schema_version": SCHEMA_VERSION, "artifact_type": ARTIFACT_TYPE, "contract_revision": CONTRACT_REVISION,
        "task_id": task, "repository": repo, "base_sha": sha,
        "request": {"intent": "", "outcome": "", "constraints": [], "exclusions": []},
        "source_bindings": [{"source": "intake_context.intake-card-render", "binding": "blocked-input", "revision": CONTRACT_REVISION}],
        "repository_context": {"repository": repo, "protected_branch": "main", "protected_base_sha": sha},
        "risk_projection": {"outcome": "BLOCKED", "risk_level": None, "risk_flags": [], "required_gate": "G0_CONTEXT", "additional_authority_gates": [], "risk_profile_digest": ""},
        "read_scope_projection": {"outcome": "BLOCKED", "failure_classification": "AGENT_PREPARATION_BLOCKED", "files_read": [], "files_exclude": [], "files_missing": [], "read_scope_hash": ""},
        "write_scope_projection": {"outcome": "BLOCKED", "candidate_paths": [], "exclusions": [], "prohibited_operations": [], "branch_binding_status": "REQUIRED_AT_G2", "required_authority_gates": [], "write_scope_hash": ""},
        "upstream_artifacts": [{"artifact_type": "blocked-input", "schema_version": "1.0", "digest": f"sha256:{digest_payload({'reason_codes': unique})}"}],
        "context_status": "BLOCKED", "outcome": "BLOCKED", "next_required_action": "ESCALATE_CONTEXT_GAP",
        "scope_hash": digest_payload({"task_id": task, "repository": repo, "base_sha": sha}), "snapshot_hash": "pending",
        "redaction_status": redaction_status, "redactions": [], "reason_code": primary, "reason_codes": unique,
        "created_at": "" if created_at is None else str(created_at), "read_only_projection": True,
        **{field: False for field in AUTHORITY_FIELDS},
    }
    return _finalize(card)


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _unescape(key: str) -> str:
    return key.replace("~1", "/").replace("~0", "~")


def _resolve(obj: Any, pointer: str) -> tuple[Any, str] | None:
    if not pointer.startswith("/") or pointer == "/":
        return None
    parts = [_unescape(p) for p in pointer.split("/")[1:]]
    current = obj
    for part in parts[:-1]:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current, parts[-1]


def validate_redaction_directives(obj: Any, directives: Any) -> bool:
    if not isinstance(directives, list):
        return False
    for directive in directives:
        if not isinstance(directive, dict) or set(directive) != {"json_pointer", "classification", "reason_code", "replacement"}:
            return False
        pointer = directive.get("json_pointer")
        if not isinstance(pointer, str) or pointer in IMMUTABLE_POINTERS or directive.get("classification") not in REDACTION_CLASSES:
            return False
        if not isinstance(directive.get("reason_code"), str) or not directive["reason_code"] or directive.get("replacement") != REDACTED:
            return False
        resolved = _resolve(obj, pointer)
        if resolved is None:
            return False
        parent, key = resolved
        if isinstance(parent, dict) and key not in parent:
            return False
        if isinstance(parent, list) and (not key.isdigit() or int(key) >= len(parent)):
            return False
    return True


def _protected(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in PROTECTED_KEYS or any(normalized.endswith("_" + item) for item in PROTECTED_KEYS)


def _auto_redact(node: Any, pointer: str = "") -> tuple[Any, list[dict[str, str]]]:
    if isinstance(node, dict):
        output: dict[str, Any] = {}
        records: list[dict[str, str]] = []
        for key, value in node.items():
            child_pointer = f"{pointer}/{_escape(str(key))}"
            if _protected(str(key)):
                output[key] = REDACTED
                records.append({"pointer": child_pointer, "classification": "CREDENTIAL", "replacement": REDACTED, "reason_code": "AUTO_PROTECTED_KEY_MATCH"})
            else:
                output[key], child = _auto_redact(value, child_pointer)
                records.extend(child)
        return output, records
    if isinstance(node, list):
        output, records = [], []
        for index, value in enumerate(node):
            child, found = _auto_redact(value, f"{pointer}/{index}")
            output.append(child)
            records.extend(found)
        return output, records
    return node, []


def apply_redactions(payload: dict[str, Any], directives: list[dict[str, str]]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    output = copy.deepcopy(payload)
    records: list[dict[str, str]] = []
    for directive in directives:
        parent, key = _resolve(output, directive["json_pointer"])  # validated by caller
        if isinstance(parent, dict):
            parent[key] = REDACTED
        else:
            parent[int(key)] = REDACTED
        records.append({"pointer": directive["json_pointer"], "classification": directive["classification"], "replacement": REDACTED, "reason_code": directive["reason_code"]})
    output, automatic = _auto_redact(output)
    records.extend(automatic)
    unique = {canonical_json(record): record for record in records}
    return output, sorted(unique.values(), key=lambda row: (row["pointer"], row["classification"], row["reason_code"]))


def _source_projection(source: Mapping[str, Any]) -> dict[str, Any]:
    return {"source_mode": source["source_mode"], "revision": source["revision"], "bindings": _canonical(source["source_bindings"]), "artifact_revision": f"{source['artifact_type']}/{source['schema_version']}"}


def render_intake_card(
    *, task_id: str, repository: str, base_sha: str, request_contract: dict[str, Any],
    source_resolution: dict[str, Any], repo_identity: dict[str, Any], protected_base_snapshot: dict[str, Any],
    risk_profile: dict[str, Any], bounded_read_scope: dict[str, Any], bounded_write_scope: dict[str, Any],
    redaction_directives: list[dict[str, str]], expected_snapshot_hash: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    mappings = (request_contract, source_resolution, repo_identity, protected_base_snapshot, risk_profile, bounded_read_scope, bounded_write_scope)
    if not isinstance(task_id, str) or not task_id or not isinstance(repository, str) or not REPOSITORY.fullmatch(repository) or not isinstance(base_sha, str) or not SHA40.fullmatch(base_sha) or not all(isinstance(item, dict) for item in mappings) or not isinstance(redaction_directives, list):
        return _blocked(task_id, repository, base_sha, ["CARD_INPUT_INVALID"], created_at)
    error = _contract_error(*mappings)
    if error:
        return _blocked(task_id, repository, base_sha, [error], created_at)
    bindings = validate_upstream_bindings(task_id=task_id, repository=repository, base_sha=base_sha, request_contract=request_contract, source_resolution=source_resolution, repo_identity=repo_identity, protected_base_snapshot=protected_base_snapshot, risk_profile=risk_profile, bounded_read_scope=bounded_read_scope, bounded_write_scope=bounded_write_scope)
    if bindings["has_errors"]:
        return _blocked(task_id, repository, base_sha, ["CARD_SOURCE_BINDING_MISMATCH"], created_at)
    risk_digest = compute_risk_decision_digest(risk_profile)
    if not _digest_matches(risk_profile["decision_digest"], risk_digest):
        return _blocked(task_id, repository, base_sha, ["CARD_UPSTREAM_DIGEST_MISMATCH"], created_at)
    scope_errors = []
    for scope in (bounded_read_scope, bounded_write_scope):
        if not _digest_matches(scope["scope_hash"], compute_scope_digest(scope)):
            scope_errors.append("CARD_SCOPE_HASH_MISMATCH")
    if scope_errors:
        return _blocked(task_id, repository, base_sha, ["CARD_UPSTREAM_DIGEST_MISMATCH", *scope_errors], created_at)

    lineage = [
        ("intake_context.request-intake", "request_contract", request_contract),
        ("intake_context.source-resolution", "source_resolution", source_resolution),
        ("intake_context.repo-identity-check", "repo_identity", repo_identity),
        ("intake_context.protected-base-capture", "protected_base_snapshot", protected_base_snapshot),
    ]
    source_rows = [{"source": src, "binding": binding, "revision": str(artifact["revision"]), **({"mode": source_resolution["source_mode"]} if binding == "source_resolution" else {})} for src, binding, artifact in lineage]
    source_rows.extend({"source": row["source_type"], "binding": row["ref"], "revision": row["revision"], "status": row["status"], "mode": source_resolution["source_mode"]} for row in source_resolution["source_bindings"])
    source_rows = sorted({canonical_json(row): row for row in source_rows}.values(), key=canonical_json)

    upstreams = (
        (request_contract, f"sha256:{_semantic_digest(request_contract, {'created_at'})}"),
        (source_resolution, f"sha256:{_semantic_digest(source_resolution, {'resolved_at', 'created_at'})}"),
        (repo_identity, f"sha256:{_semantic_digest(repo_identity, {'verified_at', 'created_at'})}"),
        (protected_base_snapshot, f"sha256:{_semantic_digest(protected_base_snapshot, {'captured_at', 'created_at'})}"),
        (risk_profile, risk_digest), (bounded_read_scope, bounded_read_scope["scope_hash"]), (bounded_write_scope, bounded_write_scope["scope_hash"]),
    )
    upstream_artifacts = sorted(({"artifact_type": artifact["artifact_type"], "schema_version": artifact["schema_version"], "digest": digest} for artifact, digest in upstreams), key=lambda row: (row["artifact_type"], row["schema_version"], row["digest"]))
    blocked = any(item["outcome"] == "BLOCKED" for item in (risk_profile, bounded_read_scope, bounded_write_scope))
    status = "BLOCKED" if blocked else "READY"
    primary = "CARD_UPSTREAM_BLOCKED" if blocked else "CARD_RENDERED"
    risk_hex, read_hex, write_hex = _digest_hex(risk_digest) or "", _digest_hex(bounded_read_scope["scope_hash"]) or "", _digest_hex(bounded_write_scope["scope_hash"]) or ""
    scope_hash = digest_payload({"task_id": task_id, "repository": repository, "base_sha": base_sha, "canonical_source_revisions": _source_projection(source_resolution), "risk_profile_digest": risk_hex, "read_scope_hash": read_hex, "write_scope_hash": write_hex})
    card = {
        "schema_version": SCHEMA_VERSION, "artifact_type": ARTIFACT_TYPE, "contract_revision": CONTRACT_REVISION,
        "task_id": task_id, "repository": repository, "base_sha": base_sha,
        "request": {"intent": request_contract["intent"], "outcome": request_contract["outcome"], "constraints": _sorted_strings(request_contract["constraints"]), "exclusions": _sorted_strings(request_contract["exclusions"])},
        "source_bindings": source_rows,
        "repository_context": {"repository": repo_identity["repository"], "protected_branch": repo_identity.get("protected_branch", repo_identity["default_branch"]), "protected_base_sha": protected_base_snapshot["protected_base_sha"]},
        "risk_projection": {"outcome": risk_profile["outcome"], "risk_level": risk_profile["risk_level"], "risk_flags": _sorted_strings(risk_profile["risk_flags"]), "required_gate": risk_profile["required_gate"], "additional_authority_gates": _sorted_strings(risk_profile["additional_authority_gates"]), "risk_profile_digest": risk_hex},
        "read_scope_projection": {"outcome": bounded_read_scope["outcome"], "failure_classification": bounded_read_scope["failure_classification"], "files_read": _sorted_strings(bounded_read_scope["files_read"]), "files_exclude": _sorted_strings(bounded_read_scope["files_exclude"]), "files_missing": _sorted_strings(bounded_read_scope["files_missing"]), "read_scope_hash": read_hex},
        "write_scope_projection": {"outcome": bounded_write_scope["outcome"], "candidate_paths": _sorted_strings(bounded_write_scope["candidate_paths"]), "exclusions": _sorted_strings(bounded_write_scope["exclusions"]), "prohibited_operations": _sorted_strings(bounded_write_scope["prohibited_operations"]), "branch_binding_status": bounded_write_scope["branch_binding_status"], "required_authority_gates": _sorted_strings(bounded_write_scope["required_authority_gates"]), "write_scope_hash": write_hex},
        "upstream_artifacts": upstream_artifacts, "context_status": status, "outcome": status,
        "next_required_action": "ESCALATE_CONTEXT_GAP" if blocked else "CONTINUE_CONTEXT_EVALUATION",
        "scope_hash": scope_hash, "snapshot_hash": "pending", "redaction_status": "NONE", "redactions": [],
        "reason_code": primary, "reason_codes": [primary], "created_at": "" if created_at is None else str(created_at),
        "read_only_projection": True, **{field: False for field in AUTHORITY_FIELDS},
    }
    if not validate_redaction_directives(card, redaction_directives):
        return _blocked(task_id, repository, base_sha, ["CARD_REDACTION_DIRECTIVE_INVALID"], created_at, "BLOCKED")
    redacted, records = apply_redactions(card, redaction_directives)
    if records:
        redacted["redaction_status"] = "APPLIED"
        redacted["redactions"] = records
        redacted["reason_code"] = "CARD_RENDERED_REDACTED" if not blocked else primary
        redacted["reason_codes"] = _sorted_strings([primary, "CARD_RENDERED_REDACTED"])
    final = _finalize(redacted)
    if expected_snapshot_hash is not None and _digest_hex(expected_snapshot_hash) != _digest_hex(final["snapshot_hash"]):
        return _blocked(task_id, repository, base_sha, ["CARD_SNAPSHOT_HASH_MISMATCH"], created_at)
    return final
