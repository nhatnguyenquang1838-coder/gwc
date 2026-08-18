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

NA81-F7 delta (SCRUM-356)
-------------------------
The SCRUM-233 builder only copied files flat. SCRUM-356 requires the tree
builder to be *topology aware*: it must construct a deterministic governance /
instruction tree from validated entries with a stable canonical order and
per-entry provenance, and it must block cycles, duplicate entries, missing
parents and ambiguous ordering. This delta adds that capability, fail-closed
and backward compatible:

* ``PlanEntry`` gains ``parent`` (instruction-tree parent target) and
  ``order`` (sibling ordering key). Entries without a parent are roots;
  ``order`` is optional.
* Pre-build topology validation (before any staging write):
  - ``TREE_DUPLICATE_ENTRY`` — two entries share the same ``(source, target)``.
  - ``TREE_MISSING_PARENT`` — an entry references a parent not in the plan.
  - ``TREE_CYCLE_DETECTED`` — the parent graph contains a cycle.
  - ``TREE_AMBIGUOUS_ORDER`` — two siblings share an explicit ``order``.
* Canonical ordering: entries are copied in topological order (parents before
  children), siblings ordered by ``order`` then target — fully deterministic.
* Per-entry provenance: each inventory row now carries ``parent``, ``order``,
  ``depth`` (root distance), ``tree_path`` (root->node path) and ``index``
  (canonical position).
* Legacy flat plans (no parent / no order) keep the exact prior behaviour.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import os
import shutil
from collections import defaultdict
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
# NA81-F7 topology reason codes (SCRUM-356)
TREE_DUPLICATE_ENTRY = "TREE_DUPLICATE_ENTRY"
TREE_MISSING_PARENT = "TREE_MISSING_PARENT"
TREE_CYCLE_DETECTED = "TREE_CYCLE_DETECTED"
TREE_AMBIGUOUS_ORDER = "TREE_AMBIGUOUS_ORDER"

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
    TREE_DUPLICATE_ENTRY,
    TREE_MISSING_PARENT,
    TREE_CYCLE_DETECTED,
    TREE_AMBIGUOUS_ORDER,
)


class Outcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class PlanEntry:
    """One accepted source/target pair from the upstream (M4) plan.

    ``source_digest`` is the digest recorded at planning time. If the source has
    changed since planning, the build fails `TREE_STALE_SOURCE` rather than
    silently exporting drifted bytes.

    NA81-F7: ``parent`` is the instruction-tree parent target (``None`` for a
    root); ``order`` is the optional sibling ordering key.
    """

    source: str
    target: str
    required: bool = True
    source_digest: Optional[str] = None
    parent: Optional[str] = None
    order: Optional[int] = None


@dataclass
class EntryResult:
    target: str
    source: str
    outcome: Outcome
    reason: str
    source_digest: Optional[str] = None
    target_digest: Optional[str] = None
    byte_count: Optional[int] = None
    parent: Optional[str] = None
    order: Optional[int] = None
    depth: int = 0
    tree_path: str = ""
    index: int = -1
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
            "parent": e.parent or "",
            "order": e.order if e.order is not None else -1,
        }
        for e in entries
    ]
    canonical.sort(
        key=lambda d: (
            d["target"],
            d["source"],
            d["parent"],
            d["order"],
        )
    )
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(blob.encode("utf-8"))


def compute_tree_digest(results: List[EntryResult]) -> str:
    """Semantic digest of the produced tree: topology + content digests."""
    canonical = sorted(
        (
            r.target,
            r.parent or "",
            r.order if r.order is not None else -1,
            r.depth,
            r.tree_path or "",
            r.target_digest or "",
            r.byte_count if r.byte_count is not None else -1,
        )
        for r in results
        if r.outcome == Outcome.PASS and r.target_digest is not None
    )
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(blob.encode("utf-8"))


# ---------------------------------------------------------------------------
# Topology validation (NA81-F7)
# ---------------------------------------------------------------------------


@dataclass
class TopoResult:
    ok: bool
    ordered: List[PlanEntry] = field(default_factory=list)
    depth: Dict[str, int] = field(default_factory=dict)
    tree_path: Dict[str, str] = field(default_factory=dict)
    reason: str = ""
    detail: str = ""


def _topologize(entries: List[PlanEntry]) -> TopoResult:
    """Validate the instruction-tree topology and produce a canonical order.

    Returns ``ok=True`` with a deterministically ordered entry list, or
    ``ok=False`` with a closed reason code describing the blocking defect.
    Runs entirely in-memory: it never writes to the filesystem.
    """
    by_id = {e.target: e for e in entries}

    # --- Duplicate entry (same source AND target) -------------------------
    seen_pair: Dict[Tuple[str, str], str] = {}
    for e in entries:
        key = (e.source, e.target)
        if key in seen_pair:
            return TopoResult(
                ok=False,
                reason=TREE_DUPLICATE_ENTRY,
                detail=f"duplicate entry {e.source!r} -> {e.target!r}",
            )
        seen_pair[key] = e.target

    # --- Missing parent ----------------------------------------------------
    for e in entries:
        if e.parent is not None and e.parent not in by_id:
            return TopoResult(
                ok=False,
                reason=TREE_MISSING_PARENT,
                detail=f"entry {e.target!r} references missing parent {e.parent!r}",
            )

    # --- Cycle detection (DFS colouring) -----------------------------------
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {e.target: WHITE for e in entries}

    def _dfs(target: str) -> bool:
        color[target] = GRAY
        parent = by_id[target].parent
        if parent is not None:
            if color.get(parent) == GRAY:
                return True
            if color.get(parent) == WHITE and _dfs(parent):
                return True
        color[target] = BLACK
        return False

    for e in entries:
        if color[e.target] == WHITE and _dfs(e.target):
            return TopoResult(
                ok=False,
                reason=TREE_CYCLE_DETECTED,
                detail=f"cycle detected involving {e.target!r}",
            )

    # --- Ambiguous ordering (two siblings share an explicit order) ---------
    groups: Dict[Optional[str], List[PlanEntry]] = defaultdict(list)
    for e in entries:
        groups[e.parent].append(e)
    for parent, group in groups.items():
        seen_orders: Dict[int, str] = {}
        for e in group:
            if e.order is None:
                continue
            if e.order in seen_orders:
                return TopoResult(
                    ok=False,
                    reason=TREE_AMBIGUOUS_ORDER,
                    detail=f"ambiguous order {e.order} under parent {parent!r}",
                )
            seen_orders[e.order] = e.target

    # --- Kahn topological sort (deterministic sibling order) --------------
    children: Dict[str, List[str]] = defaultdict(list)
    indeg: Dict[str, int] = {e.target: 0 for e in entries}
    for e in entries:
        if e.parent is not None:
            children[e.parent].append(e.target)
            indeg[e.target] += 1

    def _sort_key(t: str) -> Tuple[int, str]:
        o = by_id[t].order
        return (o if o is not None else -1, t)

    heap: List[Tuple[int, str]] = []
    for e in entries:
        if indeg[e.target] == 0:
            o = e.order
            heapq.heappush(heap, (o if o is not None else -1, e.target))

    ordered: List[PlanEntry] = []
    depth: Dict[str, int] = {}
    while heap:
        _, target = heapq.heappop(heap)
        e = by_id[target]
        d = 0 if e.parent is None else depth[e.parent] + 1
        depth[target] = d
        ordered.append(e)
        for child in sorted(children[target], key=_sort_key):
            indeg[child] -= 1
            if indeg[child] == 0:
                co = by_id[child].order
                heapq.heappush(heap, (co if co is not None else -1, child))

    # --- Tree path provenance (root -> node) -------------------------------
    tree_path: Dict[str, str] = {}
    for e in ordered:
        tree_path[e.target] = (
            e.target if e.parent is None else tree_path[e.parent] + "/" + e.target
        )

    return TopoResult(ok=True, ordered=ordered, depth=depth, tree_path=tree_path)


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

    NA81-F7: entries are validated for instruction-tree topology before any
    write (cycle / duplicate / missing-parent / ambiguous-order block the
    build fail-closed) and copied in a canonical deterministic order with
    per-entry provenance recorded in the completion evidence.
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

    # --- Topology validation (before any staging write) --------------------
    topo = _topologize(entries)
    if not topo.ok:
        return BuildResult(
            outcome=Outcome.FAIL,
            reason=topo.reason,
            idempotency_key=idempotency_key,
            plan_digest=plan_digest,
            detail=topo.detail,
        )
    ordered_entries = topo.ordered
    depth_map = topo.depth
    tree_path_map = topo.tree_path

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

    # --- Stage in canonical topological order ------------------------------
    for entry in ordered_entries:
        if entry.target in seen_targets:
            idx = len(results)
            results.append(
                EntryResult(
                    target=entry.target,
                    source=entry.source,
                    outcome=Outcome.FAIL,
                    reason=TREE_TARGET_COLLISION,
                    parent=entry.parent,
                    order=entry.order,
                    index=idx,
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
                idx = len(results)
                results.append(
                    EntryResult(
                        target=entry.target,
                        source=entry.source,
                        outcome=Outcome.FAIL,
                        reason=TREE_REQUIRED_SOURCE_MISSING,
                        parent=entry.parent,
                        order=entry.order,
                        index=idx,
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
            idx = len(results)
            results.append(
                EntryResult(
                    target=entry.target,
                    source=entry.source,
                    outcome=Outcome.FAIL,
                    reason=TREE_STALE_SOURCE,
                    source_digest=digest,
                    parent=entry.parent,
                    order=entry.order,
                    index=idx,
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
            idx = len(results)
            results.append(
                EntryResult(
                    target=entry.target,
                    source=entry.source,
                    outcome=Outcome.FAIL,
                    reason=TREE_COPY_MISMATCH,
                    source_digest=digest,
                    target_digest=_sha256_bytes(staged),
                    byte_count=len(staged),
                    parent=entry.parent,
                    order=entry.order,
                    index=idx,
                    detail="staged bytes differ from source bytes",
                )
            )
            return _fail(TREE_COPY_MISMATCH, f"copy mismatch for {entry.target!r}", results)

        seen_targets[entry.target] = entry.source
        idx = len(results)
        results.append(
            EntryResult(
                target=entry.target,
                source=entry.source,
                outcome=Outcome.PASS,
                reason=TREE_BUILD_STAGED,
                source_digest=digest,
                target_digest=_sha256_bytes(staged),
                byte_count=len(staged),
                parent=entry.parent,
                order=entry.order,
                depth=depth_map.get(entry.target, 0),
                tree_path=tree_path_map.get(entry.target, entry.target),
                index=idx,
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
                "parent": r.parent,
                "order": r.order,
                "depth": r.depth,
                "tree_path": r.tree_path,
                "index": r.index,
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
