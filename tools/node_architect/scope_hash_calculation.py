"""Canonical gate scope identity for SCRUM-187 (MAT-F2-N04).

Implements ``calculate_gate_scope_identity``: a deterministic, closed evaluator
that canonicalizes the exact semantic boundary of a proposed gate action and
emits a stable ``scope_hash``.

This node identifies scope only. It never grants authority, never validates
human approval, and never executes a connector call. The semantic scope hash
is independent of timestamps, actor identity, connector observations, evidence
readback, and the ``scope_hash`` field itself.

Design decision (F2 compatibility): the canonical action vocabulary is the
closed set of lifecycle-policy action IDs — the gate minimum actions defined by
``tools/validate_gate_action.py`` plus the FastLane envelope action IDs defined
by ``schemas/fastlane/fastlane-envelope.schema.json``. Anything outside this
union fails closed with ``SCOPE_UNKNOWN_SEMANTIC``; it is never ignored.

Failure mode: invalid scope returns an artifact with ``outcome: BLOCKED`` and
the applicable ``reason_codes`` (never raises). A valid scope returns
``outcome: READY`` with a stable ``scope_hash``.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Sequence

# --- Closed canonical vocabularies (lifecycle-policy action IDs) -----------

# Gate minimum actions from tools/validate_gate_action.py (GATE_MINIMUM_ACTIONS).
_GATE_MINIMUM_ACTIONS: frozenset[str] = frozenset({
    "read_repository", "inspect_connector", "inspect_task",
    "materialize_g1_artifacts", "run_read_only_validation",
    "create_guarded_branch_or_worktree", "modify_approved_files",
    "run_sandboxed_validation", "stage", "create_commit", "push_working_branch",
    "open_or_update_draft_pr", "mark_pr_ready_for_review", "run_independent_review",
    "merge_approved_pr",
    "verify_post_merge_ci", "deploy_approved_release", "reload_approved_runtime",
    "production_data_read", "production_data_write", "production_config_change",
    "credential_rotation", "migration",
})

# FastLane envelope action IDs (schemas/fastlane/fastlane-envelope.schema.json).
_FASTLANE_ACTIONS: frozenset[str] = frozenset({
    "create_guarded_branch",
    "modify_scoped_files",
    "open_or_update_draft_pr",
    "readback_branch_pr_diff_ci",
})

CANONICAL_ACTIONS: frozenset[str] = _GATE_MINIMUM_ACTIONS | _FASTLANE_ACTIONS

# Branch-write actions require a ``working_branch`` binding.
_BRANCH_WRITE_ACTIONS: frozenset[str] = frozenset({
    "create_guarded_branch_or_worktree",
    "create_guarded_branch",
    "modify_approved_files",
    "modify_scoped_files",
    "run_sandboxed_validation",
    "stage",
    "create_commit",
    "push_working_branch",
})

# PR-head / merge actions require both ``working_branch`` and ``head_sha``.
_HEAD_BINDING_ACTIONS: frozenset[str] = frozenset({
    "open_or_update_draft_pr",
    "mark_pr_ready_for_review",
    "run_independent_review",
    "merge_approved_pr",
})

# Read-only / no-repository-write actions permit an empty authorized_paths set.
_READ_ONLY_ACTIONS: frozenset[str] = frozenset({
    "read_repository",
    "inspect_connector",
    "inspect_task",
    "materialize_g1_artifacts",
    "run_read_only_validation",
    "run_independent_review",
    "verify_post_merge_ci",
    "readback_branch_pr_diff_ci",
})

# Closed set of allowed additional_binding keys.
BINDING_KEYS: frozenset[str] = frozenset({
    "pr_number",
    "merge_sha",
    "release",
    "environment",
    "evidence_digest",
})

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
_NUL_RE = re.compile(r"\x00")

# Canonical reason-code precedence (earliest wins as primary classification).
_REASON_PRECEDENCE: list[str] = [
    "SCOPE_INPUT_INVALID",
    "SCOPE_PATH_INVALID",
    "SCOPE_PATH_OVERBROAD",
    "SCOPE_ACTION_CONFLICT",
    "SCOPE_BINDING_REQUIRED",
    "SCOPE_UNKNOWN_SEMANTIC",
    "SCOPE_WRITE_SET_EMPTY",
]


def _normalize_paths(paths: Sequence[str]) -> tuple[list[str], list[str]]:
    """Normalize repository paths; return (normalized, reason_codes).

    Rule 3: paths use ``/``, strip leading ``./``, reject absolute/drive/
    traversal/NUL paths and unbounded root wildcards.
    """
    reasons: list[str] = []
    out: list[str] = []
    for raw in paths:
        if not isinstance(raw, str):
            reasons.append("SCOPE_PATH_INVALID")
            continue
        # Normalize only the leading ./ prefix; do NOT strip mid-string or
        # greedily replace, which would corrupt ../ (traversal) into .secrets.
        p = raw.replace("\\", "/")
        while p.startswith("./"):
            p = p[2:]
        p = p.replace("//", "/")
        parts = p.split("/")
        if _NUL_RE.search(p) or p.startswith("/") or ".." in parts or ":\\" in raw:
            reasons.append("SCOPE_PATH_INVALID")
            continue
        if p in ("", "*", "**", "/*", "/**"):
            reasons.append("SCOPE_PATH_OVERBROAD")
            continue
        if p not in out:  # dedup while preserving first-seen order
            out.append(p)
    return out, reasons


def _normalize_bindings(bindings: Sequence[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    out: list[dict[str, str]] = []
    reasons: list[str] = []
    for b in bindings:
        if not isinstance(b, dict) or "key" not in b or "value" not in b:
            reasons.append("SCOPE_UNKNOWN_SEMANTIC")
            continue
        if b["key"] not in BINDING_KEYS:
            reasons.append("SCOPE_UNKNOWN_SEMANTIC")
            continue
        if not isinstance(b["value"], str) or not b["value"].strip():
            reasons.append("SCOPE_UNKNOWN_SEMANTIC")
            continue
        out.append({"key": b["key"], "value": b["value"]})
    return out, reasons


def _canonical_json_bytes(model: dict[str, Any]) -> bytes:
    """UTF-8 JSON with sorted keys and no insignificant whitespace."""
    return json.dumps(
        model, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def calculate_gate_scope_identity(
    *,
    task_id: str,
    repository: str,
    base_ref: str,
    base_sha: str,
    working_branch: str | None,
    head_sha: str | None,
    risk_class: str,
    authorized_paths: list[str],
    authorized_actions: list[str],
    excluded_actions: list[str],
    additional_bindings: list[dict[str, str]],
    calculated_at: str | None = None,
) -> dict[str, object]:
    """Compute the canonical gate scope identity for a proposed gate action.

    Returns a ``gate-scope-identity`` artifact. ``outcome`` is ``READY`` only
    when the semantic scope is valid; otherwise ``BLOCKED`` with the applicable
    ``reason_codes``. ``authority_granted`` is always ``False``. Invalid scope
    is reported, never raised.
    """
    reasons: list[str] = []

    # --- Rule 1: malformed identity / SHA / input -------------------------
    if not isinstance(task_id, str) or not task_id.strip():
        reasons.append("SCOPE_INPUT_INVALID")
    if not isinstance(repository, str) or not _REPO_RE.match(repository):
        reasons.append("SCOPE_INPUT_INVALID")
    if not isinstance(base_ref, str) or not base_ref.strip():
        reasons.append("SCOPE_INPUT_INVALID")
    if not isinstance(base_sha, str) or not _SHA_RE.match(base_sha):
        reasons.append("SCOPE_INPUT_INVALID")
    if risk_class not in ("R0", "R1", "R2", "R3"):
        reasons.append("SCOPE_INPUT_INVALID")
    if working_branch is not None and (not isinstance(working_branch, str) or not working_branch.strip()):
        reasons.append("SCOPE_INPUT_INVALID")
    if head_sha is not None and (not isinstance(head_sha, str) or not _SHA_RE.match(head_sha)):
        reasons.append("SCOPE_INPUT_INVALID")
    if not isinstance(authorized_paths, list) or not isinstance(authorized_actions, list) \
            or not isinstance(excluded_actions, list) or not isinstance(additional_bindings, list):
        reasons.append("SCOPE_INPUT_INVALID")

    # --- Rule 3: path normalization (invalid / overbroad) -----------------
    norm_paths, path_reasons = _normalize_paths(authorized_paths or [])
    reasons.extend(path_reasons)

    # --- Rule 4: canonical action vocabulary (closed) ---------------------
    norm_actions = sorted({a for a in authorized_actions if isinstance(a, str)})
    norm_excluded = sorted({a for a in excluded_actions if isinstance(a, str)})
    for a in norm_actions:
        if a not in CANONICAL_ACTIONS:
            reasons.append("SCOPE_UNKNOWN_SEMANTIC")
            break

    # --- Rule 6: authorized/excluded conflict ----------------------------
    if set(norm_actions) & set(norm_excluded):
        reasons.append("SCOPE_ACTION_CONFLICT")

    # --- Rule 8: gate-specific binding requirements ----------------------
    if set(norm_actions) & _HEAD_BINDING_ACTIONS:
        if not working_branch or not head_sha:
            reasons.append("SCOPE_BINDING_REQUIRED")
    elif set(norm_actions) & _BRANCH_WRITE_ACTIONS:
        if not working_branch:
            reasons.append("SCOPE_BINDING_REQUIRED")

    # --- Rule 9: closed additional bindings ------------------------------
    norm_bindings, bind_reasons = _normalize_bindings(additional_bindings or [])
    reasons.extend(bind_reasons)

    # --- Rule 7: empty write scope for a write action --------------------
    write_intent = bool(set(norm_actions) - _READ_ONLY_ACTIONS)
    if write_intent and not norm_paths:
        reasons.append("SCOPE_WRITE_SET_EMPTY")

    # Surface all detected reasons (deduped, precedence-ordered).
    sorted_reasons = sorted(
        set(reasons),
        key=lambda r: _REASON_PRECEDENCE.index(r) if r in _REASON_PRECEDENCE else len(_REASON_PRECEDENCE),
    )
    if not sorted_reasons:
        sorted_reasons = ["SCOPE_HASH_CALCULATED"]
    outcome = "BLOCKED" if sorted_reasons != ["SCOPE_HASH_CALCULATED"] else "READY"

    # --- Canonical semantic model (timestamp/identity/expiry excluded) ----
    semantic = {
        "task_id": task_id,
        "repository": repository,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "working_branch": working_branch,
        "head_sha": head_sha,
        "risk_class": risk_class,
        "authorized_paths": norm_paths,
        "authorized_actions": norm_actions,
        "excluded_actions": norm_excluded,
        "additional_bindings": norm_bindings,
    }
    scope_hash = "sha256:" + hashlib.sha256(_canonical_json_bytes(semantic)).hexdigest()

    return {
        "schema_version": "1.0",
        "artifact_type": "gate-scope-identity",
        "task_id": task_id,
        "repository": repository,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "working_branch": working_branch,
        "head_sha": head_sha,
        "risk_class": risk_class,
        "authorized_paths": norm_paths,
        "authorized_actions": norm_actions,
        "excluded_actions": norm_excluded,
        "additional_bindings": norm_bindings,
        "outcome": outcome,
        "reason_codes": sorted_reasons,
        "calculated_at": calculated_at,
        # Fail closed at the payload boundary: callers must not be able to
        # mistake a BLOCKED evaluation's diagnostic digest for an approval
        # binding.  The digest is an implementation detail only when READY.
        "scope_hash": scope_hash if outcome == "READY" else None,
        "approval_request_digest": None,
        "authority_granted": False,
    }
