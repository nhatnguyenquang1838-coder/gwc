#!/usr/bin/env python3
"""Deterministic, read-only repository read-scope evaluator.

SCRUM-303 upgrades the historical path-list renderer into the runtime contract
already consumed by ``intake_card_render``. It derives the smallest verified
read set, records explicit exclusions, fails closed on ambiguous/missing/out-of-
root evidence, invalidates stale scope after repository/UA drift, and never
grants write/commit/push/PR/merge/deploy/production authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "bounded-read-scope"
NODE_ID = "intake_context.files-read-scope"
CONTRACT_REVISION = "files-read-scope/v2"
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
        raise ValueError("read-scope path must be a non-empty trimmed string")
    if value.startswith("/") or "\\" in value or ":" in value:
        raise ValueError(f"unsafe read-scope path: {value}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe read-scope path: {value}")
    return value


def _paths(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("read-scope path collection must be a list")
    return sorted({_path(item) for item in values})


def _root_allows(path: str, root: str) -> bool:
    root = root.rstrip("/")
    return path == root or path.startswith(root + "/")


def _is_excluded(path: str, rows: list[dict[str, str]]) -> str | None:
    for row in rows:
        candidate = row["path"]
        if row["match"] == "exact" and path == candidate:
            return row["reason"]
        if row["match"] == "prefix" and _root_allows(path, candidate):
            return row["reason"]
    return None


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


def _requirements(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    supplied = payload.get("read_requirements")
    if supplied is not None:
        if not isinstance(supplied, list) or not supplied:
            raise ValueError("read_requirements must be a non-empty list")
        rows: list[dict[str, Any]] = []
        ids: set[str] = set()
        for row in supplied:
            if not isinstance(row, Mapping):
                raise ValueError("read requirement must be an object")
            requirement_id = row.get("requirement_id")
            candidates = row.get("candidates")
            reason = row.get("reason")
            if not isinstance(requirement_id, str) or not requirement_id or requirement_id in ids:
                raise ValueError("read requirement ids must be unique non-empty strings")
            if not isinstance(reason, str) or not reason:
                raise ValueError("read requirement reason is required")
            normalized_candidates = _paths(candidates)
            if not normalized_candidates:
                raise ValueError("read requirement candidates must not be empty")
            ids.add(requirement_id)
            rows.append({
                "requirement_id": requirement_id,
                "candidates": normalized_candidates,
                "reason": reason,
            })
        return sorted(rows, key=lambda row: row["requirement_id"]), False

    raw = payload.get("files_read")
    if raw is None:
        raw = list(payload.get("governance_reads", [])) + list(payload.get("task_reads", []))
    files = _paths(raw)
    if not files:
        raise ValueError("at least one read-scope path is required")
    return ([
        {
            "requirement_id": f"legacy-{index:03d}",
            "candidates": [path],
            "reason": "Explicit caller read requirement.",
        }
        for index, path in enumerate(files, start=1)
    ], True)


def _exclusions(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    supplied = payload.get("excluded_paths", [])
    if not isinstance(supplied, list):
        raise ValueError("excluded_paths must be a list")
    rows: list[dict[str, str]] = []
    for row in supplied:
        if not isinstance(row, Mapping):
            raise ValueError("excluded path rule must be an object")
        path = _path(row.get("path"))
        reason = row.get("reason")
        match = row.get("match", "exact")
        if not isinstance(reason, str) or not reason or match not in {"exact", "prefix"}:
            raise ValueError("excluded path rule requires reason and exact|prefix match")
        rows.append({"path": path, "reason": reason, "match": str(match)})
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
    files_read: list[str],
    files_exclude: list[str],
    files_missing: list[str],
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
        "files_read": sorted(set(files_read)),
        "files_exclude": sorted(set(files_exclude)),
        "files_missing": sorted(set(files_missing)),
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        "constraints": [
            "Read scope must be derived from verified governance and task-specific inputs only.",
            "Read scope must remain read-only and fail closed on missing evidence.",
            "Read paths must stay within the verified repository boundary and allowed roots.",
        ],
        "exclusions": [
            "Write paths and destructive side effects.",
            "Merge, deploy, release, credential, migration, and production-data operations.",
        ],
        "entry_guards": ["G0_CONTEXT", "read_only authority_boundary"],
        "reason_code": reason_code,
        "reason_codes": [reason_code],
        "next_route": next_route,
        "observed_at": None if observed_at is None else str(observed_at),
        "read_only_projection": True,
        **{field: False for field in AUTH_FIELDS},
    }
    artifact["scope_hash"] = compute_scope_hash(artifact)
    return artifact


def render_files_read_scope(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Render the smallest verified read scope for the current repository state."""
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be an object")
    task_id, repository, base_sha, branch = _identity(payload)
    requirements, legacy_mode = _requirements(payload)
    exclusion_rows = _exclusions(payload)

    source_bindings, source_failure = _source_bindings(payload, branch=branch, base_sha=base_sha)
    if source_failure:
        return _artifact(
            task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
            source_bindings=source_bindings, outcome="BLOCKED",
            failure_classification="AGENT_PREPARATION_BLOCKED",
            files_read=[], files_exclude=[], files_missing=[],
            exclusion_reasons={}, reason_code=source_failure,
            next_route="RECOMPUTE_READ_SCOPE", observed_at=payload.get("observed_at"),
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
                files_read=[], files_exclude=[], files_missing=[],
                exclusion_reasons={}, reason_code="MALFORMED_INPUT",
                next_route="RECOMPUTE_READ_SCOPE", observed_at=payload.get("observed_at"),
            )
        if snapshot.get("base_sha") != base_sha:
            return _artifact(
                task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
                source_bindings=source_bindings, outcome="BLOCKED",
                failure_classification="AGENT_PREPARATION_BLOCKED",
                files_read=[], files_exclude=[], files_missing=[],
                exclusion_reasons={}, reason_code="SCOPE_DRIFT",
                next_route="RECOMPUTE_READ_SCOPE", observed_at=payload.get("observed_at"),
            )
        digest = snapshot.get("digest") or snapshot.get("tree_digest")
        if digest is not None and (not isinstance(digest, str) or not SHA256.fullmatch(digest)):
            return _artifact(
                task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
                source_bindings=source_bindings, outcome="BLOCKED",
                failure_classification="AGENT_PREPARATION_BLOCKED",
                files_read=[], files_exclude=[], files_missing=[],
                exclusion_reasons={}, reason_code="MALFORMED_INPUT",
                next_route="RECOMPUTE_READ_SCOPE", observed_at=payload.get("observed_at"),
            )

    prior_scope = payload.get("prior_scope")
    prior_scope_hash: str | None = None
    if prior_scope is not None:
        if not isinstance(prior_scope, Mapping) or prior_scope.get("base_sha") != base_sha:
            return _artifact(
                task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
                source_bindings=source_bindings, outcome="BLOCKED",
                failure_classification="AGENT_PREPARATION_BLOCKED",
                files_read=[], files_exclude=[], files_missing=[],
                exclusion_reasons={}, reason_code="SCOPE_DRIFT",
                next_route="RECOMPUTE_READ_SCOPE", observed_at=payload.get("observed_at"),
            )
        candidate_hash = prior_scope.get("scope_hash")
        if candidate_hash is not None:
            if not isinstance(candidate_hash, str) or not SHA256.fullmatch(candidate_hash):
                return _artifact(
                    task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
                    source_bindings=source_bindings, outcome="BLOCKED",
                    failure_classification="AGENT_PREPARATION_BLOCKED",
                    files_read=[], files_exclude=[], files_missing=[],
                    exclusion_reasons={}, reason_code="MALFORMED_INPUT",
                    next_route="RECOMPUTE_READ_SCOPE", observed_at=payload.get("observed_at"),
                )
            prior_scope_hash = candidate_hash

    allowed_roots_raw = payload.get("allowed_roots")
    allowed_roots = _paths(allowed_roots_raw) if allowed_roots_raw is not None else []
    repository_paths_raw = payload.get("repository_paths")
    repository_paths = set(_paths(repository_paths_raw)) if repository_paths_raw is not None else None

    selected: list[str] = []
    excluded: list[str] = []
    missing: list[str] = []
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
                failure_classification="AGENT_PREPARATION_BLOCKED",
                files_read=selected, files_exclude=excluded, files_missing=missing,
                exclusion_reasons=exclusion_reasons, reason_code="SCOPE_DRIFT",
                next_route="RECOMPUTE_READ_SCOPE", observed_at=payload.get("observed_at"),
            )

        eligible: list[str] = []
        for candidate in candidates:
            reason = _is_excluded(candidate, exclusion_rows)
            if reason is not None:
                excluded.append(candidate)
                exclusion_reasons[candidate] = reason
            else:
                eligible.append(candidate)

        if not eligible:
            return _artifact(
                task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
                source_bindings=source_bindings, outcome="BLOCKED",
                failure_classification="AGENT_PREPARATION_BLOCKED",
                files_read=selected, files_exclude=excluded, files_missing=missing,
                exclusion_reasons=exclusion_reasons, reason_code="SCOPE_DRIFT",
                next_route="RECOMPUTE_READ_SCOPE", observed_at=payload.get("observed_at"),
            )

        available = eligible if repository_paths is None else [path for path in eligible if path in repository_paths]
        if len(available) > 1:
            return _artifact(
                task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
                source_bindings=source_bindings, outcome="BLOCKED",
                failure_classification="AGENT_PREPARATION_BLOCKED",
                files_read=selected, files_exclude=excluded, files_missing=missing,
                exclusion_reasons=exclusion_reasons, reason_code="MALFORMED_INPUT",
                next_route="CLARIFY_READ_SCOPE", observed_at=payload.get("observed_at"),
            )
        if not available:
            missing.extend(eligible)
            continue
        selected.append(available[0])

    if missing:
        return _artifact(
            task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
            source_bindings=source_bindings, outcome="BLOCKED",
            failure_classification="REPOSITORY_EVIDENCE_MISSING",
            files_read=selected, files_exclude=excluded, files_missing=missing,
            exclusion_reasons=exclusion_reasons, reason_code="MISSING_EVIDENCE",
            next_route="REFRESH_REPOSITORY_EVIDENCE", observed_at=payload.get("observed_at"),
        )

    if not selected:
        if legacy_mode:
            raise ValueError("at least one read-scope path is required")
        return _artifact(
            task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
            source_bindings=source_bindings, outcome="BLOCKED",
            failure_classification="REPOSITORY_EVIDENCE_MISSING",
            files_read=[], files_exclude=excluded, files_missing=[],
            exclusion_reasons=exclusion_reasons, reason_code="MISSING_EVIDENCE",
            next_route="REFRESH_REPOSITORY_EVIDENCE", observed_at=payload.get("observed_at"),
        )

    ready = _artifact(
        task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
        source_bindings=source_bindings, outcome="READY", failure_classification=None,
        files_read=selected, files_exclude=excluded, files_missing=[],
        exclusion_reasons=exclusion_reasons, reason_code="ACCEPTED",
        next_route="READY_FOR_INTAKE_CARD", observed_at=payload.get("observed_at"),
    )
    if prior_scope_hash is not None and prior_scope_hash != ready["scope_hash"]:
        return _artifact(
            task_id=task_id, repository=repository, base_sha=base_sha, branch=branch,
            source_bindings=source_bindings, outcome="BLOCKED",
            failure_classification="AGENT_PREPARATION_BLOCKED",
            files_read=selected, files_exclude=excluded, files_missing=[],
            exclusion_reasons=exclusion_reasons, reason_code="SCOPE_DRIFT",
            next_route="RECOMPUTE_READ_SCOPE", observed_at=payload.get("observed_at"),
        )
    return ready


__all__ = ["canonical_json", "compute_scope_hash", "digest_payload", "render_files_read_scope"]
