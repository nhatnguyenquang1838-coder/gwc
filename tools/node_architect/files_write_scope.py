#!/usr/bin/env python3
"""Deterministic, read-only candidate write-scope evaluator.

SCRUM-304 upgrades the historical path-list renderer into the runtime contract
already consumed by ``intake_card_render`` and the G2 execution envelope. It
derives the smallest candidate future write set, records explicit exclusions
and prohibited targets, fails closed on ambiguous/missing/out-of-root/protected
evidence, invalidates stale scope after repository/UA drift, and never grants
write/commit/push/PR/merge/deploy/production authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "bounded-write-scope"
NODE_ID = "intake_context.files-write-scope"
CONTRACT_REVISION = "files-write-scope/v2"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")

AUTH_FIELDS = (
    "write_authority_granted",
    "commit_authority_granted",
    "push_authority_granted",
    "pr_authority_granted",
    "merge_authority_granted",
    "deployment_authority_granted",
    "production_authority_granted",
)

DEFAULT_EXCLUDED_ACTIONS = [
    "direct_push_main",
    "force_push",
    "delete_branch",
    "change_pr_base",
    "merge",
    "auto_merge",
    "deploy",
    "release",
    "production_config",
    "credentials",
    "secrets",
    "migration",
    "production_data",
]

# Built-in prohibited targets: protected/secret/control-plane paths that must
# never appear in a candidate write scope, regardless of caller intent.
DEFAULT_PROHIBITED = (
    {"path": "secrets", "reason": "Secret material is prohibited write scope.", "match": "prefix"},
    {"path": "credentials", "reason": "Credential material is prohibited write scope.", "match": "prefix"},
    {"path": ".github", "reason": "Generated control-plane configuration is prohibited write scope.", "match": "prefix"},
    {"path": "core/node-architect/authority", "reason": "Authority control-plane is prohibited write scope.", "match": "prefix"},
    {"path": ".env", "reason": "Environment secrets are prohibited write scope.", "match": "exact"},
    {"path": ".git", "reason": "VCS internals are prohibited write scope.", "match": "prefix"},
)


def _canon(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canon(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        items = [_canon(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_canon(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def compute_scope_hash(scope: Mapping[str, Any]) -> str:
    semantic = {
        key: value
        for key, value in scope.items()
        if key not in {"scope_hash", "observed_at", "evaluated_at", "created_at"}
        and not str(key).startswith("_")
    }
    return digest_payload(semantic)


def _path(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("write-scope path must be a non-empty trimmed string")
    if value.startswith("/") or "\\" in value or ":" in value:
        raise ValueError(f"unsafe write-scope path: {value}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe write-scope path: {value}")
    return value


def _paths(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("write-scope path collection must be a list")
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        normalized = _path(item)
        if normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return sorted(out)


def _root_allows(path: str, root: str) -> bool:
    root = root.rstrip("/")
    return path == root or path.startswith(root + "/")


def _is_matched(path: str, rows: list[dict[str, str]]) -> str | None:
    for row in rows:
        candidate = row["path"]
        if row["match"] == "exact" and path == candidate:
            return row["reason"]
        if row["match"] == "prefix" and _root_allows(path, candidate):
            return row["reason"]
    return None


def _identity(payload: Mapping[str, Any]) -> tuple[str, str, str, str]:
    task_id = payload.get("task_id")
    repository = payload.get("repository")
    base_sha = payload.get("base_sha")
    branch = payload.get("branch")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("task_id is required")
    if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository):
        raise ValueError("repository must be owner/name")
    if not isinstance(base_sha, str) or not SHA40.fullmatch(base_sha):
        raise ValueError("base_sha must be a lowercase 40-character SHA")
    if not isinstance(branch, str) or not branch:
        raise ValueError("branch is required")
    return task_id, repository, base_sha, branch


def _source_bindings(payload: Mapping[str, Any], *, branch: str, base_sha: str) -> tuple[list[dict[str, str]], str | None]:
    supplied = payload.get("source_bindings")
    if supplied is None:
        return ([{
            "source_type": "repository",
            "ref": branch,
            "revision": base_sha,
            "status": "VERIFIED",
        }], None)
    if not isinstance(supplied, list) or not supplied:
        return [], "MALFORMED_INPUT"
    rows: list[dict[str, str]] = []
    for row in supplied:
        if not isinstance(row, Mapping) or set(row) != {"source_type", "ref", "revision", "status"}:
            return [], "MALFORMED_INPUT"
        normalized = {key: row.get(key) for key in ("source_type", "ref", "revision", "status")}
        if not all(isinstance(value, str) and value for value in normalized.values()):
            return [], "MALFORMED_INPUT"
        rows.append(normalized)  # type: ignore[arg-type]
    rows = sorted({canonical_json(row): row for row in rows}.values(), key=canonical_json)
    if any(row["status"] != "VERIFIED" for row in rows):
        return rows, "SCOPE_DRIFT"
    return rows, None


def _requirements(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    supplied = payload.get("write_requirements")
    if supplied is not None:
        if not isinstance(supplied, list) or not supplied:
            raise ValueError("write_requirements must be a non-empty list")
        rows: list[dict[str, Any]] = []
        ids: set[str] = set()
        for row in supplied:
            if not isinstance(row, Mapping):
                raise ValueError("write requirement must be an object")
            requirement_id = row.get("requirement_id")
            candidates = row.get("candidates")
            reason = row.get("reason")
            if not isinstance(requirement_id, str) or not requirement_id or requirement_id in ids:
                raise ValueError("write requirement ids must be unique non-empty strings")
            if not isinstance(reason, str) or not reason:
                raise ValueError("write requirement reason is required")
            normalized_candidates = _paths(candidates)
            if not normalized_candidates:
                raise ValueError("write requirement candidates must not be empty")
            ids.add(requirement_id)
            rows.append({
                "requirement_id": requirement_id,
                "candidates": normalized_candidates,
                "reason": reason,
            })
        return sorted(rows, key=lambda row: row["requirement_id"]), False

    raw = payload.get("files_write")
    if raw is None:
        raw = list(payload.get("write_candidates", []))
    files = _paths(raw)
    if not files:
        raise ValueError("at least one write-scope path is required")
    return ([{
        "requirement_id": f"legacy-{index:03d}",
        "candidates": [path],
        "reason": "Explicit caller write requirement.",
    } for index, path in enumerate(files, start=1)], True)


def _rule_set(payload: Mapping[str, Any], key: str, defaults: tuple[dict[str, str], ...]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = [dict(item) for item in defaults]
    supplied = payload.get(key)
    if supplied:
        if not isinstance(supplied, list):
            raise ValueError(f"{key} must be a list")
        for row in supplied:
            if not isinstance(row, Mapping):
                raise ValueError(f"{key} rule must be an object")
            path = _path(row.get("path"))
            reason = row.get("reason")
            match = row.get("match", "exact")
            if not isinstance(reason, str) or not reason or match not in {"exact", "prefix"}:
                raise ValueError(f"{key} rule requires reason and exact|prefix match")
            rows.append({"path": path, "reason": str(reason), "match": str(match)})
    return sorted({canonical_json(row): row for row in rows}.values(), key=canonical_json)


def _artifact(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    branch: str,
    source_bindings: list[dict[str, str]],
    outcome: str,
    failure_classification: str | None,
    files_write: list[str],
    files_exclude: list[str],
    prohibited_targets: list[str],
    exclusion_reasons: Mapping[str, str],
    reason_code: str,
    next_route: str,
    observed_at: Any,
) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "contract_revision": CONTRACT_REVISION,
        "node_id": NODE_ID,
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "branch": branch,
        "gate": "G0_CONTEXT",
        "authority_boundary": "read_only",
        "source_bindings": source_bindings,
        "outcome": outcome,
        "failure_classification": failure_classification,
        "files_write": sorted(set(files_write)),
        "files_exclude": sorted(set(files_exclude)),
        "prohibited_targets": sorted(set(prohibited_targets)),
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        "constraints": [
            "Write scope must be repo-relative and bounded to approved task files only.",
            "Write scope must exclude protected-branch, merge, deploy, release, credential, migration, and production-data actions.",
            "Write scope must fail closed when the candidate write set is empty, ambiguous, or includes a prohibited target.",
        ],
        "exclusions": [
            "Direct push to protected branches.",
            "Force push, branch deletion, or PR base changes.",
            "Merge, auto-merge, deploy, release, production config, credentials, secrets, migration, and production data.",
        ],
        "excluded_actions": list(DEFAULT_EXCLUDED_ACTIONS),
        "entry_guards": ["G0_CONTEXT", "read_only authority_boundary"],
        "reason_code": reason_code,
        "reason_codes": [reason_code],
        "next_route": next_route,
        "observed_at": None if observed_at is None else str(observed_at),
        "read_only_projection": True,
        "candidate_write_scope": True,
        "authority_negative": True,
        **{field: False for field in AUTH_FIELDS},
    }
    artifact["scope_hash"] = compute_scope_hash(artifact)
    return artifact


def render_files_write_scope(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Render the smallest candidate write scope for the current repository state."""
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be an object")
    task_id, repository, base_sha, branch = _identity(payload)
    requirements, legacy_mode = _requirements(payload)
    excluded_rows = _rule_set(payload, "excluded_paths", ())
    prohibited_rows = _rule_set(payload, "prohibited_targets", DEFAULT_PROHIBITED)

    source_bindings, source_failure = _source_bindings(payload, branch=branch, base_sha=base_sha)
    if source_failure:
        return _artifact(
            task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
            source_bindings=source_bindings, outcome="BLOCKED",
            failure_classification="AGENT_PREPARATION_BLOCKED",
            files_write=[], files_exclude=[], prohibited_targets=[],
            exclusion_reasons={}, reason_code=source_failure,
            next_route="RECOMPUTE_WRITE_SCOPE", observed_at=payload.get("observed_at"),
        )

    for snapshot_key in ("repository_snapshot", "ua_snapshot"):
        snapshot = payload.get(snapshot_key)
        if snapshot is None:
            continue
        if not isinstance(snapshot, Mapping):
            return _artifact(
                task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
                source_bindings=source_bindings, outcome="BLOCKED",
                failure_classification="AGENT_PREPARATION_BLOCKED",
                files_write=[], files_exclude=[], prohibited_targets=[],
                exclusion_reasons={}, reason_code="MALFORMED_INPUT",
                next_route="RECOMPUTE_WRITE_SCOPE", observed_at=payload.get("observed_at"),
            )
        if snapshot.get("base_sha") != base_sha:
            return _artifact(
                task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
                source_bindings=source_bindings, outcome="BLOCKED",
                failure_classification="AGENT_PREPARATION_BLOCKED",
                files_write=[], files_exclude=[], prohibited_targets=[],
                exclusion_reasons={}, reason_code="SCOPE_DRIFT",
                next_route="RECOMPUTE_WRITE_SCOPE", observed_at=payload.get("observed_at"),
            )
        digest = snapshot.get("digest") or snapshot.get("tree_digest")
        if digest is not None and (not isinstance(digest, str) or not SHA256.fullmatch(digest)):
            return _artifact(
                task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
                source_bindings=source_bindings, outcome="BLOCKED",
                failure_classification="AGENT_PREPARATION_BLOCKED",
                files_write=[], files_exclude=[], prohibited_targets=[],
                exclusion_reasons={}, reason_code="MALFORMED_INPUT",
                next_route="RECOMPUTE_WRITE_SCOPE", observed_at=payload.get("observed_at"),
            )

    prior_scope = payload.get("prior_scope")
    prior_scope_hash: str | None = None
    if prior_scope is not None:
        if not isinstance(prior_scope, Mapping) or prior_scope.get("base_sha") != base_sha:
            return _artifact(
                task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
                source_bindings=source_bindings, outcome="BLOCKED",
                failure_classification="AGENT_PREPARATION_BLOCKED",
                files_write=[], files_exclude=[], prohibited_targets=[],
                exclusion_reasons={}, reason_code="SCOPE_DRIFT",
                next_route="RECOMPUTE_WRITE_SCOPE", observed_at=payload.get("observed_at"),
            )
        candidate_hash = prior_scope.get("scope_hash")
        if candidate_hash is not None:
            if not isinstance(candidate_hash, str) or not SHA256.fullmatch(candidate_hash):
                return _artifact(
                    task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
                    source_bindings=source_bindings, outcome="BLOCKED",
                    failure_classification="AGENT_PREPARATION_BLOCKED",
                    files_write=[], files_exclude=[], prohibited_targets=[],
                    exclusion_reasons={}, reason_code="MALFORMED_INPUT",
                    next_route="RECOMPUTE_WRITE_SCOPE", observed_at=payload.get("observed_at"),
                )
            prior_scope_hash = candidate_hash

    allowed_roots_raw = payload.get("allowed_roots")
    allowed_roots = _paths(allowed_roots_raw) if allowed_roots_raw is not None else []

    selected: list[str] = []
    excluded: list[str] = []
    prohibited: list[str] = []
    exclusion_reasons: dict[str, str] = {}

    for requirement in requirements:
        candidates = requirement["candidates"]
        outside_roots = [
            path for path in candidates
            if allowed_roots and not any(_root_allows(path, root) for root in allowed_roots)
        ]
        if outside_roots:
            for path in outside_roots:
                excluded.append(path)
                exclusion_reasons[path] = "Outside verified allowed roots."
            return _artifact(
                task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
                source_bindings=source_bindings, outcome="BLOCKED",
                failure_classification="VALIDATION_FAILED",
                files_write=selected, files_exclude=excluded, prohibited_targets=prohibited,
                exclusion_reasons=exclusion_reasons, reason_code="SCOPE_DRIFT",
                next_route="RECOMPUTE_WRITE_SCOPE", observed_at=payload.get("observed_at"),
            )

        eligible: list[str] = []
        for candidate in candidates:
            prohibited_reason = _is_matched(candidate, prohibited_rows)
            if prohibited_reason is not None:
                prohibited.append(candidate)
                excluded.append(candidate)
                exclusion_reasons[candidate] = prohibited_reason
                continue
            excluded_reason = _is_matched(candidate, excluded_rows)
            if excluded_reason is not None:
                excluded.append(candidate)
                exclusion_reasons[candidate] = excluded_reason
                continue
            eligible.append(candidate)

        if not eligible:
            continue
        if len(eligible) > 1:
            for path in candidates:
                if path not in excluded:
                    excluded.append(path)
                    exclusion_reasons[path] = "Ambiguous candidate write target; clarify intent."
            return _artifact(
                task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
                source_bindings=source_bindings, outcome="BLOCKED",
                failure_classification="VALIDATION_FAILED",
                files_write=selected, files_exclude=excluded, prohibited_targets=prohibited,
                exclusion_reasons=exclusion_reasons, reason_code="MALFORMED_INPUT",
                next_route="CLARIFY_WRITE_SCOPE", observed_at=payload.get("observed_at"),
            )
        selected.append(eligible[0])

    if prohibited and not selected:
        return _artifact(
            task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
            source_bindings=source_bindings, outcome="BLOCKED",
            failure_classification="VALIDATION_FAILED",
            files_write=[], files_exclude=excluded, prohibited_targets=prohibited,
            exclusion_reasons=exclusion_reasons, reason_code="PROHIBITED_ACTION",
            next_route="RESTRICT_WRITE_SCOPE", observed_at=payload.get("observed_at"),
        )

    if not selected:
        if legacy_mode:
            raise ValueError("at least one write-scope path is required")
        return _artifact(
            task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
            source_bindings=source_bindings, outcome="BLOCKED",
            failure_classification="VALIDATION_FAILED",
            files_write=[], files_exclude=excluded, prohibited_targets=prohibited,
            exclusion_reasons=exclusion_reasons, reason_code="SCOPE_DRIFT",
            next_route="RECOMPUTE_WRITE_SCOPE", observed_at=payload.get("observed_at"),
        )

    ready = _artifact(
        task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
        source_bindings=source_bindings, outcome="READY", failure_classification=None,
        files_write=selected, files_exclude=excluded, prohibited_targets=prohibited,
        exclusion_reasons=exclusion_reasons, reason_code="ACCEPTED",
        next_route="READY_FOR_INTAKE_CARD", observed_at=payload.get("observed_at"),
    )
    if prior_scope_hash is not None and prior_scope_hash != ready["scope_hash"]:
        return _artifact(
            task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
            source_bindings=source_bindings, outcome="BLOCKED",
            failure_classification="AGENT_PREPARATION_BLOCKED",
            files_write=selected, files_exclude=excluded, prohibited_targets=prohibited,
            exclusion_reasons=exclusion_reasons, reason_code="SCOPE_DRIFT",
            next_route="RECOMPUTE_WRITE_SCOPE", observed_at=payload.get("observed_at"),
        )
    return ready


__all__ = ["canonical_json", "compute_scope_hash", "digest_payload", "render_files_write_scope"]
