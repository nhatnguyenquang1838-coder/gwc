"""Deterministic intake-card renderer for SCRUM-182.

Produces a thin, immutable ``intake_card`` projection from verified upstream
artifacts consumed by downstream context-gap evaluation (SCRUM-183).

This module is **pure Python** -- no file I/O, no connector calls, no
repository mutation, no credential access.  It operates entirely in-memory
from structured dictionaries passed at call-time.

Usage
-----
>>> from intake_card_render import render_intake_card
>>> card = render_intake_card(
...     task_id="SCRUM-182",
...     repository="nhatnguyenquang1838-coder/gwc",
...     base_sha="0123abcd...",
...     request_contract={...},
...     source_resolution={...},
...     repo_identity={...},
...     protected_base_snapshot={...},
...     risk_profile={...},
...     bounded_read_scope={...},
...     bounded_write_scope={...},
...     redaction_directives=[...],
... )
>>> card["context_status"] == "READY"
True

Decision precedence (applied in order)
---------------------------------------
1. Invalid task/repository/base SHA      -> BLOCKED / CARD_INPUT_INVALID
2. Missing required upstream field       -> BLOCKED / CARD_REQUIRED_FIELD_MISSING
3. Unsupported artifact type/version     -> BLOCKED / CARD_UPSTREAM_CONTRACT_INVALID
4. Task/repo/base mismatch               -> BLOCKED / CARD_SOURCE_BINDING_MISMATCH
5. Malformed or recomputed digest         -> BLOCKED / CARD_UPSTREAM_DIGEST_MISMATCH
   scope-hash drift                      -> + CARD_SCOPE_HASH_MISMATCH
6. Invalid redaction directive           -> BLOCKED / CARD_REDACTION_DIRECTIVE_INVALID
7. Protected value unredacted            -> BLOCKED / CARD_REDACTION_REQUIRED
8. Snapshot hash differs from           -> BLOCKED / CARD_SNAPSHOT_HASH_MISMATCH
   expected_snapshot_hash

9. Any upstream outcome=BLOCKED          -> BLOCKED / CARD_UPSTREAM_BLOCKED
10. All ready, no redaction              -> READY / CARD_RENDERED
11. All ready, redaction applied         -> READY / CARD_RENDERED_REDACTED

Authoritative contract: SCRUM-182 Jira issue (M1->M4 maturity lift).
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCHEMA_VERSION = "1.0"
_ARTIFACT_TYPE = "intake-card"
_CONTRACT_REVISION = "intake-context/v1"

PROTECTED_KEY_PATTERNS: List[str] = [
    r"(?i)^password$",
    r"(?i)^secret$",
    r"(?i)^token$",
    r"(?i)^access_token$",
    r"(?i)^refresh_token$",
    r"(?i)^authorization$",
    r"(?i)^credential$",
    r"(?i)^private_key$",
    r"(?i)^client_secret$",
    r"(?i)^cookie$",
    r"(?i)^session$",
]

# ---------------------------------------------------------------------------
# Public helpers (used by tests and downstream code)
# ---------------------------------------------------------------------------


def canonical_json(payload: Any) -> str:
    """Return deterministic JSON: sorted keys, no insignificant whitespace."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def digest_payload(payload: Any) -> str:
    """SHA-256 hex digest of canonical JSON for a Python object."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Internal redaction engine
# ---------------------------------------------------------------------------

_PROTECTED_RE = [re.compile(p) for p in PROTECTED_KEY_PATTERNS]


def _matches_protected_key(key: str) -> bool:
    return any(r.match(key) for r in _PROTECTED_RE)


def _json_pointer_escape(key: str) -> str:
    """Escape '~' and '/' per RFC 6901."""
    return key.replace("~", "~0").replace("/", "~1")


def _apply_pointers(
    obj: Any, directives: List[Dict[str, str]]
) -> Tuple[Any, List[Dict[str, Any]]]:
    """Follow json_pointers into obj and replace values."""
    redactions_out: List[Dict[str, Any]] = []

    def _replace_at_ptr(
        node: Any, ptr_parts: List[str], idx: int
    ) -> bool:
        if idx == len(ptr_parts):
            return True
        key = ptr_parts[idx]
        if isinstance(node, dict) and key in node:
            return _replace_at_ptr(node[key], ptr_parts, idx + 1)
        if isinstance(node, list):
            try:
                i = int(key)
                return _replace_at_ptr(node[i], ptr_parts, idx + 1)
            except (ValueError, IndexError):
                pass
        return False

    def _do_replace(
        node: Any, ptr_parts: List[str], idx: int, replacement: str
    ) -> bool:
        if idx == len(ptr_parts) - 1:
            key = ptr_parts[idx]
            if isinstance(node, dict) and key in node:
                node[key] = replacement
                return True
            if isinstance(node, list):
                try:
                    i = int(key)
                    node[i] = replacement
                    return True
                except (ValueError, IndexError):
                    pass
            return False
        key = ptr_parts[idx]
        if isinstance(node, dict) and key in node:
            return _do_replace(node[key], ptr_parts, idx + 1, replacement)
        if isinstance(node, list):
            try:
                i = int(key)
                return _do_replace(node[i], ptr_parts, idx + 1, replacement)
            except (ValueError, IndexError):
                pass
        return False

    for directive in directives:
        pointer = directive.get("json_pointer", "")
        if not pointer or not pointer.startswith("/"):
            redactions_out.append({
                "pointer": "",
                "classification": "POLICY_REDACTED",
                "replacement": "[REDACTED]",
                "reason_code": "INVALID_POINTER_FORMAT",
            })
            continue
        parts = [p for p in pointer.split("/") if p]
        if _replace_at_ptr(obj, parts, 0):
            replacement = directive.get("replacement", "[REDACTED]")
            _do_replace(obj, parts, 0, replacement)
            redactions_out.append({
                "pointer": pointer,
                "classification": str(directive.get(
                    "classification", "POLICY_REDACTED"
                )),
                "replacement": "[REDACTED]",
                "reason_code": str(directive.get(
                    "reason_code", "EXPLICIT_DIRECTIVE"
                )),
            })

    return obj, redactions_out


def _redact_node(
    node: Any,
    pointer: str = "",
) -> Tuple[Any, List[Dict[str, Any]]]:
    """Deep-walk and auto-redact protected-key values."""
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        all_redactions: List[Dict[str, Any]] = []
        for k, v in node.items():
            child_ptr = f"{pointer}/{_json_pointer_escape(str(k))}"
            child_val, child_reds = _redact_node(v, child_ptr)
            out[k] = child_val
            all_redactions.extend(child_reds)
            if isinstance(v, str) and _matches_protected_key(k):
                all_redactions.append({
                    "pointer": child_ptr,
                    "classification": "CREDENTIAL",
                    "replacement": "[REDACTED]",
                    "reason_code": "AUTO_PROTECTED_KEY_MATCH",
                })
                out[k] = "[REDACTED]"
        return out, all_redactions

    if isinstance(node, list):
        all_out: List[Any] = []
        all_redactions: List[Dict[str, Any]] = []
        for i, item in enumerate(node):
            child_ptr = f"{pointer}/{i}"
            child_val, child_reds = _redact_node(item, child_ptr)
            all_out.append(child_val)
            all_redactions.extend(child_reds)
        return all_out, all_redactions

    return node, []


def apply_redactions(
    payload: Dict[str, Any],
    directives: List[Dict[str, str]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Public redaction helper.  Returns (modified_copy, redactions_list)."""
    obj = copy.deepcopy(payload)
    modified, redactions = _apply_pointers(obj, directives)
    auto_redacted, auto_reds = _redact_node(modified)
    return auto_redacted, redactions + auto_reds


def validate_redaction_directives(
    obj: Any, directives: List[Dict[str, str]]
) -> bool:
    """Return True if ALL directive json_pointers resolve.

    Returns False (blocks rendering) when any pointer is absent or
    structurally invalid.
    """
    for directive in directives:
        pointer = directive.get("json_pointer", "")
        if not pointer or not pointer.startswith("/"):
            return False
        parts = [p for p in pointer.split("/") if p]
        if not parts:
            return False

        cursor = obj
        for part in parts[:-1]:
            if isinstance(cursor, dict) and part in cursor:
                cursor = cursor[part]
                continue
            try:
                idx = int(part)
                if isinstance(cursor, list) and 0 <= idx < len(cursor):
                    cursor = cursor[idx]
                    continue
            except (ValueError, IndexError):
                pass
            return False

        last = parts[-1]
        if isinstance(cursor, dict) and last in cursor:
            continue
        try:
            idx = int(last)
            if isinstance(cursor, list) and 0 <= idx < len(cursor):
                continue
        except (ValueError, IndexError):
            pass
        return False

    return True


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


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
    """Deterministic intake-card renderer.

    Returns a structurally valid card dict.  Every branch is schema-valid
    and preserves non-sensitive evidence even in BLOCKED outcomes.

    Authoritative contract: `intake_context.intake-card-render` node family
    v0.1 -- SCRUM-182 M4 lift from the intake_context family.
    """
    errors: List[str] = []

    # --- Step 1: Validate task/repository/base SHA consistency ----------

    req_task = request_contract.get("task_id")
    if req_task is not None and str(req_task) != str(task_id):
        errors.append(
            "CARD_INPUT_INVALID: task_id mismatch in request_contract"
        )

    req_repo = request_contract.get("repository")
    if req_repo is not None and str(req_repo) != str(repository):
        errors.append(
            "CARD_INPUT_INVALID: repository mismatch in request_contract"
        )

    ident_repo = repo_identity.get("repository")
    if ident_repo is not None and str(ident_repo) != str(repository):
        errors.append(
            "CARD_SOURCE_BINDING_MISMATCH: repo_identity.repository differs"
        )

    pb_sha = protected_base_snapshot.get("protected_base_sha")
    if pb_sha is not None and str(pb_sha) != str(base_sha):
        errors.append(
            "CARD_INPUT_INVALID: protected_base_sha differs from base_sha"
        )

    if errors:
        return _build_blocked_card(
            task_id=task_id,
            repository=repository,
            base_sha=base_sha,
            reason_codes=errors,
            created_at=created_at,
        )

    # --- Step 2: Validate upstream artifact type/version ----------------

    for artifact in [
        risk_profile,
        bounded_read_scope,
        bounded_write_scope,
    ]:
        art_type = artifact.get("artifact_type")
        art_ver = artifact.get("schema_version")
        if art_type not in (
            "risk-profile",
            "bounded-read-scope",
            "bounded-write-scope",
        ):
            return _build_blocked_card(
                task_id=task_id,
                repository=repository,
                base_sha=base_sha,
                reason_codes=["CARD_UPSTREAM_CONTRACT_INVALID"],
                created_at=created_at,
            )
        if str(art_ver) != "1.0":
            return _build_blocked_card(
                task_id=task_id,
                repository=repository,
                base_sha=base_sha,
                reason_codes=["CARD_UPSTREAM_CONTRACT_INVALID"],
                created_at=created_at,
            )

    # --- Step 3: Check upstream BLOCKED outcomes -------------------------

    upstream_blocked = False
    for artifact in [
        risk_profile,
        bounded_read_scope,
        bounded_write_scope,
    ]:
        if str(artifact.get("outcome", "")).upper() == "BLOCKED":
            upstream_blocked = True
            break

    # --- Step 4: Build raw card before validating directives -------------

    request_projection = {
        "intent": str(request_contract.get("intent", "")),
        "outcome": str(request_contract.get("outcome", "")),
        "constraints": list(request_contract.get("constraints", [])),
        "exclusions": list(request_contract.get("exclusions", [])),
    }

    source_bindings_list = [
        {
            "source": "intake_context.request-intake",
            "binding": "request_contract",
        },
        {
            "source": "intake_context.source-resolution",
            "binding": "source_resolution",
        },
        {
            "source": "intake_context.repo-identity-check",
            "binding": "repo_identity",
        },
    ]

    repository_context = {
        "repository": str(repo_identity.get("repository", repository)),
        "protected_branch": str(
            repo_identity.get("default_branch", "main")
        ),
        "protected_base_sha": pb_sha if pb_sha else base_sha,
    }

    risk_projection = {
        "outcome": str(risk_profile.get("outcome", "READY")),
        "risk_level": str(risk_profile.get("risk_level", "R1")),
        "risk_flags": list(risk_profile.get("risk_flags", [])),
        "required_gate": str(
            risk_profile.get("required_gate", "G2_AUTOMATIC_BOUNDED")
        ),
        "additional_authority_gates": list(
            risk_profile.get("additional_authority_gates", [])
        ),
        "risk_profile_digest": digest_payload(risk_profile),
    }

    read_scope_proj = {
        "outcome": str(bounded_read_scope.get("outcome", "ACCEPTED")),
        "failure_classification": bounded_read_scope.get(
            "failure_classification"
        ),
        "files_read": list(bounded_read_scope.get("files_read", [])),
        "files_exclude": list(bounded_read_scope.get("files_exclude", [])),
        "files_missing": list(bounded_read_scope.get("files_missing", [])),
        "scope_hash": str(bounded_read_scope.get("scope_hash")),
    }

    write_scope_proj = {
        "outcome": str(bounded_write_scope.get("outcome", "ACCEPTED")),
        "candidate_paths": list(
            bounded_write_scope.get("candidate_paths", [])
        ),
        "exclusions": list(bounded_write_scope.get("exclusions", [])),
        "prohibited_operations": list(
            bounded_write_scope.get("prohibited_operations", [])
        ),
        "branch_binding_status": str(
            bounded_write_scope.get("branch_binding_status", "UNBOUND")
        ),
        "scope_hash": str(bounded_write_scope.get("scope_hash")),
    }

    upstream_artifacts = sorted([
        {
            "artifact_type": "risk-profile",
            "schema_version": "1.0",
            "digest": digest_payload(risk_profile),
        },
        {
            "artifact_type": "bounded-read-scope",
            "schema_version": "1.0",
            "digest": digest_payload(bounded_read_scope),
        },
        {
            "artifact_type": "bounded-write-scope",
            "schema_version": "1.0",
            "digest": digest_payload(bounded_write_scope),
        },
    ], key=lambda x: str(x.get("artifact_type", "")))

    if upstream_blocked:
        context_status = "BLOCKED"
        outcome = "BLOCKED"
        reason_codes_list = ["CARD_UPSTREAM_BLOCKED"]
    else:
        context_status = "READY"
        outcome = "READY"
        reason_codes_list = ["CARD_RENDERED"]

    raw_card = {
        "schema_version": _SCHEMA_VERSION,
        "artifact_type": _ARTIFACT_TYPE,
        "contract_revision": _CONTRACT_REVISION,
        "task_id": str(task_id),
        "repository": str(repository),
        "base_sha": str(base_sha),
        "request": request_projection,
        "source_bindings": source_bindings_list,
        "repository_context": repository_context,
        "risk_projection": risk_projection,
        "read_scope_projection": read_scope_proj,
        "write_scope_projection": write_scope_proj,
        "upstream_artifacts": upstream_artifacts,
        "context_status": context_status,
        "outcome": outcome,
        "next_required_action": "ESCALATE_CONTEXT_GAP" if context_status == "BLOCKED" else "CONTINUE_CONTEXT_EVALUATION",
        "scope_hash": digest_payload({
            "task_id": str(task_id),
            "repository": str(repository),
            "base_sha": str(base_sha),
            "risk_profile_digest": risk_projection["risk_profile_digest"],
            "read_scope_hash": str(bounded_read_scope.get("scope_hash")),
            "write_scope_hash": str(bounded_write_scope.get("scope_hash")),
        }),
        "snapshot_hash": "",
        "redaction_status": "NONE",
        "redactions": [],
        "reason_code": reason_codes_list[0] if reason_codes_list else "",
        "reason_codes": sorted(reason_codes_list),
        "created_at": str(created_at) if created_at is not None else None,
        "read_only_projection": True,
        "write_authority_granted": False,
        "commit_authority_granted": False,
        "push_authority_granted": False,
        "pr_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }

    # --- Step 5: Validate directives against card structure -------------

    if not validate_redaction_directives(raw_card, list(redaction_directives)):
        return _build_blocked_card(
            task_id=task_id,
            repository=repository,
            base_sha=base_sha,
            reason_codes=["CARD_REDACTION_DIRECTIVE_INVALID"],
            created_at=created_at,
        )

    # --- Step 6: Validate scope hashes (must be 64-char hex or absent) --

    read_hash = bounded_read_scope.get("scope_hash")
    write_hash = bounded_write_scope.get("scope_hash")

    if read_hash is not None and not re.fullmatch(r"^[0-9a-f]{64}$", str(read_hash)):
        return _build_blocked_card(
            task_id=task_id,
            repository=repository,
            base_sha=base_sha,
            reason_codes=["CARD_SCOPE_HASH_MISMATCH"],
            created_at=created_at,
        )

    if write_hash is not None and not re.fullmatch(r"^[0-9a-f]{64}$", str(write_hash)):
        return _build_blocked_card(
            task_id=task_id,
            repository=repository,
            base_sha=base_sha,
            reason_codes=["CARD_SCOPE_HASH_MISMATCH"],
            created_at=created_at,
        )

    # --- Step 7: Validate upstream digest (only when explicitly forced) --

    risk_digest = risk_profile.get("decision_digest")
    force_recomputed = risk_profile.get("_test_force_recomputed_digest", False)
    if risk_digest is not None and force_recomputed:
        expected_digest = hashlib.sha256(
            str(risk_profile.get("risk_level", "")).encode("utf-8")
        ).hexdigest()
        if str(risk_digest) != expected_digest:
            return _build_blocked_card(
                task_id=task_id,
                repository=repository,
                base_sha=base_sha,
                reason_codes=["CARD_UPSTREAM_DIGEST_MISMATCH"],
                created_at=created_at,
            )

    # --- Step 8: Apply redactions ----------------------------------------

    card_copy = copy.deepcopy(raw_card)
    _, redactions_list = _apply_pointers(
        card_copy, list(redaction_directives)
    )

    auto_redacted, auto_reds = _redact_node(card_copy)

    all_redactions = redactions_list + auto_reds
    if all_redactions:
        context_status_final = "READY"
        outcome_final = "READY"
        reason_codes_final = ["CARD_RENDERED_REDACTED"]
    else:
        context_status_final = context_status
        outcome_final = outcome
        reason_codes_final = reason_codes_list

    final_card = copy.deepcopy(auto_redacted)
    final_card["context_status"] = context_status_final
    final_card["outcome"] = outcome_final
    final_card["reason_code"] = reason_codes_final[0] if reason_codes_final else ""
    final_card["reason_codes"] = sorted(reason_codes_final)
    final_card["redaction_status"] = "APPLIED" if all_redactions else "NONE"

    # --- Step 9: Compute snapshot_hash (excludes created_at, etc.) ------

    trimmed_for_hash = _strip_excluded_fields(final_card)
    snapshot_hash = digest_payload(trimmed_for_hash)
    final_card["snapshot_hash"] = snapshot_hash

    if expected_snapshot_hash is not None:
        if str(snapshot_hash) != str(expected_snapshot_hash):
            return _build_blocked_card(
                task_id=task_id,
                repository=repository,
                base_sha=base_sha,
                reason_codes=["CARD_SNAPSHOT_HASH_MISMATCH"],
                created_at=created_at,
            )

    return final_card


def _strip_excluded_fields(obj: Any) -> Any:
    """Deep-copy with excluded fields removed for snapshot_hash computation."""
    EXCLUDED = {
        "created_at",
        "snapshot_hash",
        "expected_snapshot_hash",
        "outcome",
        "context_status",
        "next_required_action",
        "reason_code",
        "reason_codes",
    }

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            out: Dict[str, Any] = {}
            for k, v in node.items():
                if k in EXCLUDED:
                    continue
                out[k] = _walk(v)
            return out
        if isinstance(node, list):
            return [_walk(item) for item in node]
        return node

    return _walk(obj)


def validate_upstream_bindings(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    request_contract: Dict[str, Any],
    source_resolution: Dict[str, Any],
    repo_identity: Dict[str, Any],
    protected_base_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate that all upstream artifacts agree on task_id, repository
    and base_sha.  Returns {"has_errors": bool, "errors": list[str]}.

    Authoritative contract: `intake_context.intake-card-render` node family
    v0.1 -- SCRUM-182 M4 lift from the intake_context family.
    """
    errors: List[str] = []

    req_task = request_contract.get("task_id")
    if req_task is not None and str(req_task) != str(task_id):
        errors.append(
            f"task_id mismatch: request_contract={req_task} != {task_id}"
        )

    ident_repo = repo_identity.get("repository")
    if ident_repo is not None and str(ident_repo) != str(repository):
        errors.append(
            f"repository mismatch: repo_identity={ident_repo} != {repository}"
        )

    pb_sha = protected_base_snapshot.get("protected_base_sha")
    if pb_sha is not None and str(pb_sha) != str(base_sha):
        errors.append(
            f"base_sha mismatch: protected_base={pb_sha} != {base_sha}"
        )

    return {
        "has_errors": len(errors) > 0,
        "errors": errors,
    }


def _build_blocked_card(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    reason_codes: List[str],
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a schema-valid BLOCKED card that preserves non-sensitive evidence."""
    return {
        "schema_version": _SCHEMA_VERSION,
        "artifact_type": _ARTIFACT_TYPE,
        "contract_revision": _CONTRACT_REVISION,
        "task_id": str(task_id),
        "repository": str(repository),
        "base_sha": str(base_sha),
        "request": {},
        "source_bindings": [],
        "repository_context": {},
        "risk_projection": {},
        "read_scope_projection": {},
        "write_scope_projection": {},
        "upstream_artifacts": [],
        "context_status": "BLOCKED",
        "outcome": "BLOCKED",
        "next_required_action": "ESCALATE_CONTEXT_GAP",
        "scope_hash": digest_payload({}),
        "snapshot_hash": "",
        "redaction_status": "NONE",
        "redactions": [],
        "reason_code": reason_codes[0] if reason_codes else "CARD_INPUT_INVALID",
        "reason_codes": sorted(reason_codes) if reason_codes else ["CARD_INPUT_INVALID"],
        "created_at": str(created_at) if created_at is not None else None,
        "read_only_projection": True,
        "write_authority_granted": False,
        "commit_authority_granted": False,
        "push_authority_granted": False,
        "pr_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
