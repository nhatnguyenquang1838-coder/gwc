#!/usr/bin/env python3
"""Export Manifest Generation — package_export.export-manifest-generation (M5_EVIDENCE).

Generates deterministic export evidence: for every accepted package entry it
records source identity, entry status, byte counts and SHA-256 values
(source + target where available).

Design invariants (SCRUM-234 / F7 family contract):

* Pure evidence generator. It reads source bytes to compute digests and may
  optionally cross-check against the upstream tree-build evidence
  (SCRUM-233, ``governance-tree-build``); it never writes package content.
* Closed reason-code taxonomy: unknown states are rejected, never ignored.
* Deterministic: identical inputs (plan + source snapshot + optional upstream
  evidence) produce byte-identical manifest content and stable manifest digest.
  Observational fields (generation time, run ids) are deliberately excluded.
* Consumes upstream ``entry_inventory`` only for cross-validation; it does not
  re-derive authority of any kind.
* A generated manifest grants no repository, PR, merge, deploy or release
  authority; it is execution-plane evidence only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_ID = "gwc.package_export.export_manifest_generation"
SCHEMA_VERSION = "0.1"

# ---------------------------------------------------------------------------
# Stable reason codes (closed taxonomy — do not extend without a schema bump)
# ---------------------------------------------------------------------------

MANIFEST_GENERATED = "MANIFEST_GENERATED"
MANIFEST_SOURCE_MISSING = "MANIFEST_SOURCE_MISSING"
MANIFEST_ENTRY_INVALID = "MANIFEST_ENTRY_INVALID"
MANIFEST_DIGEST_MISMATCH = "MANIFEST_DIGEST_MISMATCH"
MANIFEST_IDEMPOTENT_REPLAY = "MANIFEST_IDEMPOTENT_REPLAY"

REASON_CODES: Tuple[str, ...] = (
    MANIFEST_GENERATED,
    MANIFEST_SOURCE_MISSING,
    MANIFEST_ENTRY_INVALID,
    MANIFEST_DIGEST_MISMATCH,
    MANIFEST_IDEMPOTENT_REPLAY,
)

ENTRY_STATUS_ACCEPTED = "ACCEPTED"
ENTRY_STATUS_MISSING = "MISSING"
ENTRY_STATUS_REJECTED = "REJECTED"


class Outcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class ManifestPlanEntry:
    """One accepted package entry to record evidence for.

    Mirrors the upstream plan shape (SCRUM-233) without importing it, keeping
    this node independently testable and authority-free.
    """

    source: str
    target: str
    required: bool = True


@dataclass
class EntryEvidence:
    """Deterministic evidence record for a single entry."""

    source: str
    target: str
    entry_status: str
    source_digest: Optional[str]
    target_digest: Optional[str]
    byte_count: Optional[int]
    reason: str
    detail: str = ""


@dataclass
class ExportManifestResult:
    outcome: Outcome
    reason: str
    idempotency_key: str
    manifest_digest: str
    plan_digest: str
    entries: List[EntryEvidence] = field(default_factory=list)
    manifest: Optional[Dict[str, Any]] = None
    detail: str = ""

    @property
    def generated(self) -> bool:
        return self.outcome == Outcome.PASS and self.reason in (
            MANIFEST_GENERATED,
            MANIFEST_IDEMPOTENT_REPLAY,
        )


# ---------------------------------------------------------------------------
# Deterministic digests
# ---------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_plan_digest(plan: List[ManifestPlanEntry]) -> str:
    """Canonical, order-independent semantic digest of the accepted plan."""
    canonical = [
        {
            "source": e.source,
            "target": e.target,
            "required": bool(e.required),
        }
        for e in plan
    ]
    canonical.sort(key=lambda d: (d["target"], d["source"]))
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(blob.encode("utf-8"))


def compute_manifest_digest(manifest: Dict[str, Any]) -> str:
    """Deterministic digest of the manifest content (excludes its own digest)."""
    blob = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_bytes(blob.encode("utf-8"))


def _build_manifest_dict(
    *,
    task_id: str,
    source_sha: str,
    package_version: str,
    idempotency_key: str,
    plan_digest: str,
    entries: List[EntryEvidence],
    outcome: Outcome,
    reason: str,
) -> Dict[str, Any]:
    manifest = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "source_sha": source_sha,
        "package_version": package_version,
        "idempotency_key": idempotency_key,
        "plan_digest": plan_digest,
        "entry_inventory": [
            {
                "source": e.source,
                "target": e.target,
                "entry_status": e.entry_status,
                "source_digest": e.source_digest,
                "target_digest": e.target_digest,
                "byte_count": e.byte_count,
                "reason": e.reason,
                "detail": e.detail,
            }
            for e in entries
        ],
        "outcome": outcome.value,
        "reason": reason,
    }
    manifest["manifest_digest"] = "sha256:" + compute_manifest_digest(manifest)
    return manifest


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def _upstream_by_target(tree_build_evidence: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not tree_build_evidence:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for inv in tree_build_evidence.get("entry_inventory", []) or []:
        if isinstance(inv, dict) and "target" in inv:
            out[inv["target"]] = inv
    return out


def generate_export_manifest(
    plan: List[ManifestPlanEntry],
    source_root: str | os.PathLike[str],
    *,
    idempotency_key: str,
    task_id: str = "",
    source_sha: str = "",
    package_version: str = "",
    tree_build_evidence: Optional[Dict[str, Any]] = None,
    cross_check: bool = False,
    existing_manifest: Optional[Dict[str, Any]] = None,
) -> ExportManifestResult:
    """Generate the deterministic export manifest for an accepted plan.

    Reads each source file to compute its byte count and SHA-256. When
    ``tree_build_evidence`` is provided, the upstream target digest is recorded
    per entry; if ``cross_check`` is True a mismatch between the recomputed
    source digest and the upstream source digest fails with
    ``MANIFEST_DIGEST_MISMATCH``.

    A result is only ``MANIFEST_GENERATED`` when every required source exists
    and (when cross-checked) digests agree. The manifest dict is embedded in
    the result and is byte-deterministic for identical inputs.
    """
    source_root = Path(source_root)
    plan_digest = compute_plan_digest(plan)

    # --- Idempotent replay (before any read that matters) ------------------
    if existing_manifest is not None:
        if existing_manifest.get("idempotency_key") == idempotency_key:
            if existing_manifest.get("plan_digest") == plan_digest:
                entries = [
                    EntryEvidence(
                        source=e["source"],
                        target=e["target"],
                        entry_status=e.get("entry_status", ENTRY_STATUS_ACCEPTED),
                        source_digest=e.get("source_digest"),
                        target_digest=e.get("target_digest"),
                        byte_count=e.get("byte_count"),
                        reason=e.get("reason", MANIFEST_GENERATED),
                        detail=e.get("detail", ""),
                    )
                    for e in existing_manifest.get("entry_inventory", [])
                ]
                return ExportManifestResult(
                    outcome=Outcome.PASS,
                    reason=MANIFEST_IDEMPOTENT_REPLAY,
                    idempotency_key=idempotency_key,
                    manifest_digest=existing_manifest.get("manifest_digest", ""),
                    plan_digest=plan_digest,
                    entries=entries,
                    manifest=existing_manifest,
                    detail="identical replay; existing manifest returned",
                )
            return ExportManifestResult(
                outcome=Outcome.FAIL,
                reason=MANIFEST_DIGEST_MISMATCH,
                idempotency_key=idempotency_key,
                manifest_digest="",
                plan_digest=plan_digest,
                detail="same idempotency key with a different plan digest",
            )

    upstream = _upstream_by_target(tree_build_evidence)
    entries: List[EntryEvidence] = []

    for entry in sorted(plan, key=lambda e: (e.target, e.source)):
        src = source_root / entry.source
        if not src.is_file():
            if entry.required:
                entries.append(
                    EntryEvidence(
                        source=entry.source,
                        target=entry.target,
                        entry_status=ENTRY_STATUS_MISSING,
                        source_digest=None,
                        target_digest=None,
                        byte_count=None,
                        reason=MANIFEST_SOURCE_MISSING,
                        detail="required source missing at manifest time",
                    )
                )
                manifest = _build_manifest_dict(
                    task_id=task_id,
                    source_sha=source_sha,
                    package_version=package_version,
                    idempotency_key=idempotency_key,
                    plan_digest=plan_digest,
                    entries=entries,
                    outcome=Outcome.FAIL,
                    reason=MANIFEST_SOURCE_MISSING,
                )
                return ExportManifestResult(
                    outcome=Outcome.FAIL,
                    reason=MANIFEST_SOURCE_MISSING,
                    idempotency_key=idempotency_key,
                    manifest_digest="sha256:" + manifest["manifest_digest"].split("sha256:")[1],
                    plan_digest=plan_digest,
                    entries=entries,
                    manifest=manifest,
                    detail=f"required source {entry.source!r} missing",
                )
            # Optional missing entries are recorded as skipped evidence.
            entries.append(
                EntryEvidence(
                    source=entry.source,
                    target=entry.target,
                    entry_status=ENTRY_STATUS_MISSING,
                    source_digest=None,
                    target_digest=upstream.get(entry.target, {}).get("target_digest"),
                    byte_count=None,
                    reason=MANIFEST_SOURCE_MISSING,
                    detail="optional source missing; recorded as skipped",
                )
            )
            continue

        data = src.read_bytes()
        source_digest = _sha256_bytes(data)
        up = upstream.get(entry.target, {})
        target_digest = up.get("target_digest")
        up_source = up.get("source_digest")

        if cross_check and up_source and up_source != source_digest:
            entries.append(
                EntryEvidence(
                    source=entry.source,
                    target=entry.target,
                    entry_status=ENTRY_STATUS_REJECTED,
                    source_digest=source_digest,
                    target_digest=target_digest,
                    byte_count=len(data),
                    reason=MANIFEST_DIGEST_MISMATCH,
                    detail="source digest diverges from upstream tree-build evidence",
                )
            )
            manifest = _build_manifest_dict(
                task_id=task_id,
                source_sha=source_sha,
                package_version=package_version,
                idempotency_key=idempotency_key,
                plan_digest=plan_digest,
                entries=entries,
                outcome=Outcome.FAIL,
                reason=MANIFEST_DIGEST_MISMATCH,
            )
            return ExportManifestResult(
                outcome=Outcome.FAIL,
                reason=MANIFEST_DIGEST_MISMATCH,
                idempotency_key=idempotency_key,
                manifest_digest="sha256:" + manifest["manifest_digest"].split("sha256:")[1],
                plan_digest=plan_digest,
                entries=entries,
                manifest=manifest,
                detail=f"source {entry.source!r} digest mismatch vs upstream",
            )

        entries.append(
            EntryEvidence(
                source=entry.source,
                target=entry.target,
                entry_status=ENTRY_STATUS_ACCEPTED,
                source_digest=source_digest,
                target_digest=target_digest,
                byte_count=len(data),
                reason=MANIFEST_GENERATED,
                detail="source read; digest recorded",
            )
        )

    manifest = _build_manifest_dict(
        task_id=task_id,
        source_sha=source_sha,
        package_version=package_version,
        idempotency_key=idempotency_key,
        plan_digest=plan_digest,
        entries=entries,
        outcome=Outcome.PASS,
        reason=MANIFEST_GENERATED,
    )
    return ExportManifestResult(
        outcome=Outcome.PASS,
        reason=MANIFEST_GENERATED,
        idempotency_key=idempotency_key,
        manifest_digest=manifest["manifest_digest"],
        plan_digest=plan_digest,
        entries=entries,
        manifest=manifest,
        detail="export manifest generated deterministically",
    )


def authority_granted(result: ExportManifestResult) -> bool:
    """A generated manifest never grants authority. Always False by contract."""
    return False
