#!/usr/bin/env python3
"""Governance Tree Build — package_export.governance-tree-build (M5_REPLAY_SAFE).

Builds the generated `.governance/` tree from an accepted source/target plan
using run-scoped staging, byte-exact readback and replay semantics.

Design invariants (SCRUM-233 / F7 family contract):

* Staging-first: every file is written into a run-scoped staging tree and is
  promoted to the final output tree only after full readback verification.
* No final-complete result exists until every copied file has been read back
  and matches the expected source bytes and byte count.
* Partial output, divergent existing content, stale source readback or
  promotion failure never produce `TREE_BUILD_COMPLETE`.
* Replay: same idempotency key + same plan digest returns the equivalent
  existing tree (`TREE_IDEMPOTENT_REPLAY`); same key + different digest fails
  `TREE_REPLAY_CONFLICT`.
* Deterministic: same canonical plan + same source snapshot produce the same
  semantic tree digest.
* Closed reason-code taxonomy: unknown states are rejected, never ignored.
* A complete build grants no repository, PR, merge, deploy or release
  authority; it is execution-plane evidence only.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_ID = "gwc.package_export.governance_tree_build"
SCHEMA_VERSION = "0.1"

COMPLETION_MARKER = "completion.json"
STAGING_DIRNAME = ".staging"

# ---------------------------------------------------------------------------
# Stable reason codes (closed taxonomy — do not extend without a schema bump)
# ---------------------------------------------------------------------------

TREE_BUILD_COMPLETE = "TREE_BUILD_COMPLETE"
TREE_BUILD_STAGED = "TREE_BUILD_STAGED"
TREE_REQUIRED_SOURCE_MISSING = "TREE_REQUIRED_SOURCE_MISSING"
TREE_COPY_MISMATCH = "TREE_COPY_MISMATCH"
TREE_TARGET_COLLISION = "TREE_TARGET_COLLISION"
TREE_PARTIAL_OUTPUT = "TREE_PARTIAL_OUTPUT"
TREE_READBACK_MISMATCH = "TREE_READBACK_MISMATCH"
TREE_STALE_SOURCE = "TREE_STALE_SOURCE"
TREE_IDEMPOTENT_REPLAY = "TREE_IDEMPOTENT_REPLAY"
TREE_REPLAY_CONFLICT = "TREE_REPLAY_CONFLICT"

REASON_CODES: Tuple[str, ...] = (
    TREE_BUILD_COMPLETE,
    TREE_BUILD_STAGED,
    TREE_REQUIRED_SOURCE_MISSING,
    TREE_COPY_MISMATCH,
    TREE_TARGET_COLLISION,
    TREE_PARTIAL_OUTPUT,
    TREE_READBACK_MISMATCH,
    TREE_STALE_SOURCE,
    TREE_IDEMPOTENT_REPLAY,
    TREE_REPLAY_CONFLICT,
)


class Outcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class PlanEntry:
    """One accepted source/target pair from the upstream (M4) plan.

    `source_digest` is the digest recorded at planning time. If the source has
    changed since planning, the build fails `TREE_STALE_SOURCE` rather than
    silently exporting drifted bytes.
    """

    source: str
    target: str
    required: bool = True
    source_digest: Optional[str] = None


@dataclass
class EntryResult:
    target: str
    source: str
    outcome: Outcome
    reason: str
    source_digest: Optional[str] = None
    target_digest: Optional[str] = None
    byte_count: Optional[int] = None
    detail: str = ""


@dataclass
class BuildResult:
    outcome: Outcome
    reason: str
    idempotency_key: str
    plan_digest: str
    entries: List[EntryResult] = field(default_factory=list)
    tree_digest: Optional[str] = None
    completion_evidence: Optional[Dict[str, Any]] = None
    detail: str = ""

    @property
    def complete(self) -> bool:
        return self.outcome == Outcome.PASS and self.reason in (
            TREE_BUILD_COMPLETE,
            TREE_IDEMPOTENT_REPLAY,
        )


# ---------------------------------------------------------------------------
# Deterministic digests
# ---------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_plan_digest(entries: List[PlanEntry]) -> str:
    """Canonical, order-independent semantic digest of the accepted plan."""
    canonical = [
        {
            "source": e.source,
            "target": e.target,
            "required": bool(e.required),
            "source_digest": e.source_digest or "",
        }
        for e in entries
    ]
    canonical.sort(key=lambda d: (d["target"], d["source"]))
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(blob.encode("utf-8"))


def compute_tree_digest(results: List[EntryResult]) -> str:
    """Semantic digest of the produced tree: target path + content digest."""
    canonical = sorted(
        (r.target, r.target_digest or "", r.byte_count if r.byte_count is not None else -1)
        for r in results
        if r.outcome == Outcome.PASS and r.target_digest is not None
    )
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(blob.encode("utf-8"))


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def _read_completion(output_root: Path) -> Optional[Dict[str, Any]]:
    marker = output_root / COMPLETION_MARKER
    if not marker.is_file():
        return None
    try:
        return json.loads(marker.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def build_governance_tree(
    entries: List[PlanEntry],
    source_root: str | os.PathLike[str],
    output_root: str | os.PathLike[str],
    *,
    idempotency_key: str,
    task_id: str = "",
    source_sha: str = "",
    package_version: str = "",
    staging_root: Optional[str | os.PathLike[str]] = None,
    promote: bool = True,
) -> BuildResult:
    """Build the governance tree with staging, readback and replay semantics.

    Returns a `BuildResult`. A result is only `TREE_BUILD_COMPLETE` when every
    entry was copied, read back byte-exact from the FINAL output tree and the
    completion marker was written.
    """
    source_root = Path(source_root)
    output_root = Path(output_root)
    plan_digest = compute_plan_digest(entries)

    # --- Replay check (before any write) -----------------------------------
    existing = _read_completion(output_root)
    if existing is not None:
        if existing.get("idempotency_key") == idempotency_key:
            if existing.get("plan_digest") == plan_digest:
                return BuildResult(
                    outcome=Outcome.PASS,
                    reason=TREE_IDEMPOTENT_REPLAY,
                    idempotency_key=idempotency_key,
                    plan_digest=plan_digest,
                    tree_digest=existing.get("tree_digest"),
                    completion_evidence=existing,
                    detail="identical replay; existing complete tree returned",
                )
            return BuildResult(
                outcome=Outcome.FAIL,
                reason=TREE_REPLAY_CONFLICT,
                idempotency_key=idempotency_key,
                plan_digest=plan_digest,
                tree_digest=existing.get("tree_digest"),
                completion_evidence=existing,
                detail="same idempotency key with a different plan digest",
            )

    staging = Path(staging_root) if staging_root else output_root.parent / (
        output_root.name + STAGING_DIRNAME + "-" + idempotency_key
    )
    # Run-scoped staging is always rebuilt: a leftover partial staging tree
    # from a crashed run must never be promoted.
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    results: List[EntryResult] = []
    seen_targets: Dict[str, str] = {}

    def _fail(reason: str, detail: str, partial: List[EntryResult]) -> BuildResult:
        # Failed/partial staging is isolated and discarded; it can never
        # masquerade as a valid package.
        shutil.rmtree(staging, ignore_errors=True)
        return BuildResult(
            outcome=Outcome.FAIL,
            reason=reason,
            idempotency_key=idempotency_key,
            plan_digest=plan_digest,
            entries=partial,
            detail=detail,
        )

    # --- Stage in canonical entry order ------------------------------------
    for entry in sorted(entries, key=lambda e: (e.target, e.source)):
        if entry.target in seen_targets:
            results.append(
                EntryResult(
                    target=entry.target,
                    source=entry.source,
                    outcome=Outcome.FAIL,
                    reason=TREE_TARGET_COLLISION,
                    detail=f"target already produced by {seen_targets[entry.target]!r}",
                )
            )
            return _fail(
                TREE_TARGET_COLLISION,
                f"duplicate target {entry.target!r}",
                results,
            )

        src = source_root / entry.source
        if not src.is_file():
            if entry.required:
                results.append(
                    EntryResult(
                        target=entry.target,
                        source=entry.source,
                        outcome=Outcome.FAIL,
                        reason=TREE_REQUIRED_SOURCE_MISSING,
                        detail="required source missing at build time",
                    )
                )
                return _fail(
                    TREE_REQUIRED_SOURCE_MISSING,
                    f"required source {entry.source!r} missing",
                    results,
                )
            # Optional missing entries are skipped per the accepted decision.
            continue

        data = src.read_bytes()
        digest = _sha256_bytes(data)

        if entry.source_digest and entry.source_digest != digest:
            results.append(
                EntryResult(
                    target=entry.target,
                    source=entry.source,
                    outcome=Outcome.FAIL,
                    reason=TREE_STALE_SOURCE,
                    source_digest=digest,
                    detail="source changed since planning",
                )
            )
            return _fail(
                TREE_STALE_SOURCE,
                f"source {entry.source!r} drifted since planning",
                results,
            )

        dest = staging / entry.target
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

        # Immediate staging readback: copy must be byte-exact.
        staged = dest.read_bytes()
        if staged != data or len(staged) != len(data):
            results.append(
                EntryResult(
                    target=entry.target,
                    source=entry.source,
                    outcome=Outcome.FAIL,
                    reason=TREE_COPY_MISMATCH,
                    source_digest=digest,
                    target_digest=_sha256_bytes(staged),
                    byte_count=len(staged),
                    detail="staged bytes differ from source bytes",
                )
            )
            return _fail(TREE_COPY_MISMATCH, f"copy mismatch for {entry.target!r}", results)

        seen_targets[entry.target] = entry.source
        results.append(
            EntryResult(
                target=entry.target,
                source=entry.source,
                outcome=Outcome.PASS,
                reason=TREE_BUILD_STAGED,
                source_digest=digest,
                target_digest=_sha256_bytes(staged),
                byte_count=len(staged),
                detail="staged",
            )
        )

    if not promote:
        return BuildResult(
            outcome=Outcome.PASS,
            reason=TREE_BUILD_STAGED,
            idempotency_key=idempotency_key,
            plan_digest=plan_digest,
            entries=results,
            tree_digest=compute_tree_digest(results),
            detail="staging complete; promotion not requested",
        )

    # --- Promote staging -> final output tree ------------------------------
    try:
        if output_root.exists():
            shutil.rmtree(output_root)
        output_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(output_root))
    except OSError as exc:  # pragma: no cover - environment dependent
        return _fail(TREE_PARTIAL_OUTPUT, f"promotion failed: {exc}", results)

    # --- Final readback from the promoted tree -----------------------------
    for r in results:
        final = output_root / r.target
        if not final.is_file():
            shutil.rmtree(output_root, ignore_errors=True)
            return BuildResult(
                outcome=Outcome.FAIL,
                reason=TREE_PARTIAL_OUTPUT,
                idempotency_key=idempotency_key,
                plan_digest=plan_digest,
                entries=results,
                detail=f"promoted tree missing {r.target!r}",
            )
        actual = _sha256_bytes(final.read_bytes())
        if actual != r.target_digest:
            shutil.rmtree(output_root, ignore_errors=True)
            return BuildResult(
                outcome=Outcome.FAIL,
                reason=TREE_READBACK_MISMATCH,
                idempotency_key=idempotency_key,
                plan_digest=plan_digest,
                entries=results,
                detail=f"readback digest mismatch for {r.target!r}",
            )
        r.reason = TREE_BUILD_COMPLETE

    tree_digest = compute_tree_digest(results)
    evidence: Dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "source_sha": source_sha,
        "package_version": package_version,
        "plan_digest": plan_digest,
        "idempotency_key": idempotency_key,
        "tree_digest": tree_digest,
        "entry_inventory": [
            {
                "target": r.target,
                "source": r.source,
                "source_digest": r.source_digest,
                "target_digest": r.target_digest,
                "byte_count": r.byte_count,
            }
            for r in results
        ],
        "outcome": Outcome.PASS.value,
        "reason": TREE_BUILD_COMPLETE,
    }
    (output_root / COMPLETION_MARKER).write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    return BuildResult(
        outcome=Outcome.PASS,
        reason=TREE_BUILD_COMPLETE,
        idempotency_key=idempotency_key,
        plan_digest=plan_digest,
        entries=results,
        tree_digest=tree_digest,
        completion_evidence=evidence,
        detail="tree built, readback-verified and marked complete",
    )


def authority_granted(result: BuildResult) -> bool:
    """A completed tree build never grants authority. Always False by contract."""
    return False
