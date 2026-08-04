#!/usr/bin/env python3
"""Target Path Safety Check — package_export.target-path-safety-check (M4_DETERMINISTIC).

Proves every export target is consumer-package-relative, output-root bounded and
safe from collision or unintended overwrite, *before* any file is written.

Design invariants (from SCRUM-232 / F7 family contract):

* Pure evaluator. No filesystem read, no copy, no target mutation, no network.
* Deterministic: the same target set + run identity produce the same ordered
  decision list and the same semantic digest.
* Closed reason-code taxonomy: unknown states are rejected, never ignored.
* A valid (safe) result never grants repository, PR, merge, deploy or release
  authority; it is execution-plane evidence only.
* No output directory or file is created by the evaluator.
* Unknown existing-state / readback failure blocks rather than permitting overwrite.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_ID = "gwc.package_export.target_path_safety_check"
SCHEMA_VERSION = "0.1"

# Approved package prefix — targets must be relative to this root.
DEFAULT_APPROVED_PREFIX = ".governance/"

RESERVED_CONTROL_PATHS = (
    "conftest.py",
    "__init__.py",
    "Makefile",
    ".gitignore",
)

# ---------------------------------------------------------------------------
# Stable reason codes (closed taxonomy — do not extend without a schema bump)
# ---------------------------------------------------------------------------

TARGET_PATH_SAFE = "TARGET_PATH_SAFE"
TARGET_PATH_EMPTY = "TARGET_PATH_EMPTY"
TARGET_PATH_ABSOLUTE = "TARGET_PATH_ABSOLUTE"
TARGET_PATH_TRAVERSAL = "TARGET_PATH_TRAVERSAL"
TARGET_PATH_BACKSLASH = "TARGET_PATH_BACKSLASH"
TARGET_PATH_ESCAPES_ROOT = "TARGET_PATH_ESCAPES_ROOT"
TARGET_SYMLINK_ESCAPE = "TARGET_SYMLINK_ESCAPE"
TARGET_PREFIX_FORBIDDEN = "TARGET_PREFIX_FORBIDDEN"
TARGET_DUPLICATE = "TARGET_DUPLICATE"
TARGET_CASE_COLLISION = "TARGET_CASE_COLLISION"
TARGET_OVERWRITE_FORBIDDEN = "TARGET_OVERWRITE_FORBIDDEN"
TARGET_IDEMPOTENT_EXISTING = "TARGET_IDEMPOTENT_EXISTING"

REASON_CODES: Tuple[str, ...] = (
    TARGET_PATH_SAFE,
    TARGET_PATH_EMPTY,
    TARGET_PATH_ABSOLUTE,
    TARGET_PATH_TRAVERSAL,
    TARGET_PATH_BACKSLASH,
    TARGET_PATH_ESCAPES_ROOT,
    TARGET_SYMLINK_ESCAPE,
    TARGET_PREFIX_FORBIDDEN,
    TARGET_DUPLICATE,
    TARGET_CASE_COLLISION,
    TARGET_OVERWRITE_FORBIDDEN,
    TARGET_IDEMPOTENT_EXISTING,
)

OVERWRITE_POLICY_BLOCK = "block"
OVERWRITE_POLICY_IDEMPOTENT = "idempotent"


class Outcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass
class TargetDecision:
    """One target's safety decision."""

    target: str
    normalized: str
    output_root: str
    outcome: Outcome
    reason: str
    overwrite_decision: Optional[str] = None
    semantic_digest: Optional[str] = None
    detail: str = ""


@dataclass
class SafetyPlan:
    """Deterministic plan for a set of targets. No filesystem side effects."""

    decisions: List[TargetDecision] = field(default_factory=list)
    semantic_digest: str = ""

    @property
    def outcome(self) -> Outcome:
        return Outcome.PASS if all(d.outcome == Outcome.PASS for d in self.decisions) else Outcome.FAIL


def _normalize(target: str, approved_prefix: str) -> str:
    """Normalize a target to a POSIX relative path (no leading slash, forward slashes).

    Uses posixpath.normpath to collapse `.` and `..` segments. Traversal is
    detected separately by `_is_traversal`. Does NOT auto-prepend the approved
    prefix — the caller must verify the prefix separately so a missing prefix is
    a hard FORBIDDEN, not a silent fix.
    """
    import posixpath

    rel = target.replace("\\", "/").lstrip("/")
    return posixpath.normpath(rel) if rel else ""


def _is_traversal(normalized: str) -> bool:
    parts = normalized.split("/")
    return ".." in parts


def _escapes_root(normalized: str, approved_prefix: str) -> bool:
    """True if the normalized path escapes the approved prefix root."""
    norm = os.path.normpath("/" + normalized)
    prefix = os.path.normpath("/" + approved_prefix)
    return not (norm == prefix or norm.startswith(prefix + "/"))


def evaluate_target(
    target: str,
    output_root: str,
    *,
    approved_prefix: str = DEFAULT_APPROVED_PREFIX,
    overwrite_policy: str = OVERWRITE_POLICY_BLOCK,
    run_identity: str = "",
    existing_state: Optional[Dict[str, str]] = None,
) -> TargetDecision:
    """Evaluate a single target. Pure: no filesystem access.

    `existing_state` maps normalized target -> content digest of the current
    on-disk file (or None if absent / unknown). A value of None with the key
    present means "readback failed / unknown" and must block overwrite.
    """
    if not target or not target.strip():
        return TargetDecision(
            target=target,
            normalized="",
            output_root=output_root,
            outcome=Outcome.FAIL,
            reason=TARGET_PATH_EMPTY,
            detail="empty target",
        )

    if target.startswith("/") or (len(target) >= 2 and target[1] == ":" and target[2:3] in ("\\", "/")):
        return TargetDecision(
            target=target,
            normalized="",
            output_root=output_root,
            outcome=Outcome.FAIL,
            reason=TARGET_PATH_ABSOLUTE,
            detail="absolute path rejected",
        )

    if "\\" in target:
        return TargetDecision(
            target=target,
            normalized="",
            output_root=output_root,
            outcome=Outcome.FAIL,
            reason=TARGET_PATH_BACKSLASH,
            detail="backslash rejected",
        )

    # Parent traversal must be rejected on the raw segment list BEFORE
    # normpath collapses ".." into a safe-looking relative path.
    if ".." in [seg for seg in target.replace("\\", "/").split("/") if seg]:
        return TargetDecision(
            target=target,
            normalized="",
            output_root=output_root,
            outcome=Outcome.FAIL,
            reason=TARGET_PATH_TRAVERSAL,
            detail="parent traversal rejected",
        )

    normalized = _normalize(target, approved_prefix)

    # Source/target self-copy conflict: target equals the output root itself
    # (writing the package root into itself). Checked before prefix so the bare
    # root ".governance" is flagged as self-copy, not as a missing-slash prefix.
    if normalized == output_root:
        return TargetDecision(
            target=target,
            normalized=normalized,
            output_root=output_root,
            outcome=Outcome.FAIL,
            reason=TARGET_SYMLINK_ESCAPE,
            detail="source/target self-copy conflict",
        )

    if _is_traversal(normalized):
        return TargetDecision(
            target=target,
            normalized=normalized,
            output_root=output_root,
            outcome=Outcome.FAIL,
            reason=TARGET_PATH_TRAVERSAL,
            detail="parent traversal rejected",
        )

    if not normalized.startswith(approved_prefix):
        return TargetDecision(
            target=target,
            normalized=normalized,
            output_root=output_root,
            outcome=Outcome.FAIL,
            reason=TARGET_PREFIX_FORBIDDEN,
            detail="target outside approved package prefix",
        )

    if _escapes_root(normalized, approved_prefix):
        return TargetDecision(
            target=target,
            normalized=normalized,
            output_root=output_root,
            outcome=Outcome.FAIL,
            reason=TARGET_PATH_ESCAPES_ROOT,
            detail="target escapes approved output root",
        )

    base = os.path.basename(normalized)
    if base in RESERVED_CONTROL_PATHS:
        return TargetDecision(
            target=target,
            normalized=normalized,
            output_root=output_root,
            outcome=Outcome.FAIL,
            reason=TARGET_PREFIX_FORBIDDEN,
            detail=f"reserved control path {base!r} rejected",
        )


    # Overwrite / idempotency decision
    overwrite_decision = None
    if existing_state is not None:
        if normalized not in existing_state:
            pass  # not present — safe to write
        else:
            existing_digest = existing_state[normalized]
            if existing_digest is None:
                # Unknown readback -> block, never permit overwrite blindly.
                return TargetDecision(
                    target=target,
                    normalized=normalized,
                    output_root=output_root,
                    outcome=Outcome.FAIL,
                    reason=TARGET_OVERWRITE_FORBIDDEN,
                    overwrite_decision="blocked_unknown_readback",
                    detail="existing state unknown; overwrite blocked",
                )
            if overwrite_policy == OVERWRITE_POLICY_IDEMPOTENT and existing_digest == run_identity:
                overwrite_decision = "idempotent_identical"
            else:
                return TargetDecision(
                    target=target,
                    normalized=normalized,
                    output_root=output_root,
                    outcome=Outcome.FAIL,
                    reason=TARGET_OVERWRITE_FORBIDDEN,
                    overwrite_decision="blocked_divergent",
                    detail="existing non-equivalent content blocks overwrite",
                )

    digest_input = json_digest_input(target, normalized, output_root, overwrite_decision or "")
    semantic_digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()

    return TargetDecision(
        target=target,
        normalized=normalized,
        output_root=output_root,
        outcome=Outcome.PASS,
        reason=TARGET_PATH_SAFE,
        overwrite_decision=overwrite_decision,
        semantic_digest=semantic_digest,
        detail="target safe",
    )


def json_digest_input(*parts: str) -> str:
    return "|".join(parts)


def evaluate_targets(
    targets: List[str],
    output_root: str,
    *,
    approved_prefix: str = DEFAULT_APPROVED_PREFIX,
    overwrite_policy: str = OVERWRITE_POLICY_BLOCK,
    run_identity: str = "",
    existing_state: Optional[Dict[str, str]] = None,
) -> SafetyPlan:
    """Evaluate a set of targets deterministically. No filesystem side effects.

    Detects duplicate normalized targets, case-normalization collisions and
    source/target self-copy conflicts. Produces an ordered, deterministic plan.
    """
    existing_state = existing_state or {}
    decisions: List[TargetDecision] = []
    seen_normalized: Dict[str, int] = {}
    seen_case: Dict[str, str] = {}

    for idx, target in enumerate(targets):
        dec = evaluate_target(
            target,
            output_root,
            approved_prefix=approved_prefix,
            overwrite_policy=overwrite_policy,
            run_identity=run_identity,
            existing_state=existing_state,
        )
        if dec.outcome == Outcome.PASS:
            norm = dec.normalized
            # Duplicate normalized target
            if norm in seen_normalized:
                dec = TargetDecision(
                    target=target,
                    normalized=norm,
                    output_root=output_root,
                    outcome=Outcome.FAIL,
                    reason=TARGET_DUPLICATE,
                    detail=f"duplicate normalized target (first at index {seen_normalized[norm]})",
                )
            else:
                seen_normalized[norm] = idx
            # Case-normalization collision
            lower = norm.lower()
            if lower in seen_case and seen_case[lower] != norm:
                dec = TargetDecision(
                    target=target,
                    normalized=norm,
                    output_root=output_root,
                    outcome=Outcome.FAIL,
                    reason=TARGET_CASE_COLLISION,
                    detail=f"case collision with {seen_case[lower]!r}",
                )
            else:
                seen_case.setdefault(lower, norm)
            # Source/target self-copy conflict
            if norm == output_root or norm.endswith("/" + output_root) or norm == output_root + "/":
                dec = TargetDecision(
                    target=target,
                    normalized=norm,
                    output_root=output_root,
                    outcome=Outcome.FAIL,
                    reason=TARGET_SYMLINK_ESCAPE,
                    detail="source/target self-copy conflict",
                )
        decisions.append(dec)

    plan = SafetyPlan(decisions=decisions)
    plan.semantic_digest = _plan_digest(decisions)
    return plan


def _plan_digest(decisions: List[TargetDecision]) -> str:
    parts = []
    for d in decisions:
        parts.append(
            json_digest_input(
                d.target,
                d.normalized,
                d.outcome.value,
                d.reason,
                d.overwrite_decision or "",
            )
        )
    return hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()


def authority_granted(plan: SafetyPlan) -> bool:
    """A safety plan never grants authority. Always False by contract."""
    return False
