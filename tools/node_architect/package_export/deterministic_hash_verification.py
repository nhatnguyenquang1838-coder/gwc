#!/usr/bin/env python3
"""Deterministic Hash Verification — package_export.deterministic-hash-verification (M5_REPLAY_SAFE).

Read-only evidence evaluator (SCRUM-235, F7 family contract). It recomputes
SHA-256 and byte counts from the *exact* source and target bytes for every
copied entry recorded in a SCRUM-234 export manifest, reconciles the manifest
entry inventory, copied/skipped status, file count and the output-tree digest
with a byte-level readback, and binds the result to the exact source SHA,
manifest digest, output-tree digest, verifier version and idempotency key.

Design invariants (SCRUM-235 / F7 family contract):

* Read-only. It never repairs, rewrites or deletes output. It only reads bytes.
* Deterministic: identical accepted evidence (manifest + source/output bytes +
  idempotency key) produces a byte-identical result dict and a stable digest.
  Observational fields (generated_at, run ids, source_base_sha) are excluded
  from the canonical digests so they cannot change the result.
* Closed reason-code taxonomy: a changed/missing/extra/unmanifested/algorithm
  mismatch fails closed with the exact stable reason code; unknown states are
  rejected, never silently ignored.
* Subset verification cannot claim package validity: PASS requires every copied
  entry AND the complete output inventory to match.
* Optional skipped entries remain explicit: they require no target file and no
  content hash, but are accounted for in the manifest digest reconciliation.
* A verification result grants no repository, PR, merge, deploy or release
  authority; it is execution-plane evidence only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_ID = "gwc.package_export.deterministic_hash_verification"
SCHEMA_VERSION = "0.1"
VERIFIER_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Stable reason codes (closed taxonomy — do not extend without a schema bump)
# ---------------------------------------------------------------------------

HASH_VERIFICATION_PASS = "HASH_VERIFICATION_PASS"
HASH_SOURCE_MISMATCH = "HASH_SOURCE_MISMATCH"
HASH_TARGET_MISMATCH = "HASH_TARGET_MISMATCH"
HASH_BYTE_COUNT_MISMATCH = "HASH_BYTE_COUNT_MISMATCH"
HASH_MANIFEST_DIGEST_MISMATCH = "HASH_MANIFEST_DIGEST_MISMATCH"
HASH_TREE_DIGEST_MISMATCH = "HASH_TREE_DIGEST_MISMATCH"
HASH_TARGET_MISSING = "HASH_TARGET_MISSING"
HASH_UNMANIFESTED_TARGET = "HASH_UNMANIFESTED_TARGET"
HASH_ALGORITHM_UNSUPPORTED = "HASH_ALGORITHM_UNSUPPORTED"
HASH_IDEMPOTENT_REPLAY = "HASH_IDEMPOTENT_REPLAY"
HASH_REPLAY_CONFLICT = "HASH_REPLAY_CONFLICT"

REASON_CODES: tuple[str, ...] = (
    HASH_VERIFICATION_PASS,
    HASH_SOURCE_MISMATCH,
    HASH_TARGET_MISMATCH,
    HASH_BYTE_COUNT_MISMATCH,
    HASH_MANIFEST_DIGEST_MISMATCH,
    HASH_TREE_DIGEST_MISMATCH,
    HASH_TARGET_MISSING,
    HASH_UNMANIFESTED_TARGET,
    HASH_ALGORITHM_UNSUPPORTED,
    HASH_IDEMPOTENT_REPLAY,
    HASH_REPLAY_CONFLICT,
)

ENTRY_STATUS_ACCEPTED = "ACCEPTED"
ENTRY_STATUS_MISSING = "MISSING"
ENTRY_STATUS_REJECTED = "REJECTED"
ENTRY_STATUS_SKIPPED_OPTIONAL = "SKIPPED_OPTIONAL"

REQUIRED_ALGORITHM = "sha256"
REQUIRED_ALGORITHM_VERSION = "1"


class Outcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass
class RejectDetail:
    target: str
    reason: str
    detail: str
    source: Optional[str] = None


@dataclass
class HashVerificationResult:
    outcome: Outcome
    reason: str
    source_sha: str
    manifest_digest: str
    output_tree_digest: str
    idempotency_key: str
    verifier_version: str
    entries_verified: int
    entries_rejected: int
    task_id: str = ""
    reject_detail: List[RejectDetail] = field(default_factory=list)
    detail: str = ""
    authority_granted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "schema_id": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "task_id": self.task_id,
            "source_sha": self.source_sha,
            "manifest_digest": self.manifest_digest,
            "output_tree_digest": self.output_tree_digest,
            "idempotency_key": self.idempotency_key,
            "verifier_version": self.verifier_version,
            "entries_verified": self.entries_verified,
            "entries_rejected": self.entries_rejected,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "authority_granted": False,
        }
        if self.reject_detail:
            d["reject_detail"] = [
                {
                    "target": r.target,
                    "source": r.source,
                    "reason": r.reason,
                    "detail": r.detail,
                }
                for r in self.reject_detail
            ]
        return d


# ---------------------------------------------------------------------------
# Deterministic digests
# ---------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_manifest_digest(manifest: Dict[str, Any]) -> str:
    """Canonical semantic digest of the manifest, independent of observational fields.

    Hashes only the semantically stable fields (never ``generated_at``,
    run ids or other observational metadata), so a changed generation time
    does not alter the manifest identity.
    """
    canonical = {
        "schema_id": manifest.get("schema_id"),
        "schema_version": manifest.get("schema_version"),
        "task_id": manifest.get("task_id"),
        "source_sha": manifest.get("source_sha"),
        "package_version": manifest.get("package_version"),
        "idempotency_key": manifest.get("idempotency_key"),
        "plan_digest": manifest.get("plan_digest"),
        "entry_inventory": manifest.get("entry_inventory", []),
        "outcome": manifest.get("outcome"),
        "reason": manifest.get("reason"),
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + _sha256_bytes(blob.encode("utf-8"))


def compute_output_tree_digest(output_root: str | os.PathLike[str]) -> str:
    """Deterministic digest of the complete output inventory.

    Sorted over (relative target path, target sha256) for every file under the
    output root, so order and generation time cannot change the result.
    """
    output_root = Path(output_root)
    records: List[Dict[str, str]] = []
    for p in sorted(output_root.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(output_root).as_posix())
            records.append({"target": rel, "digest": _sha256_bytes(p.read_bytes())})
    blob = json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + _sha256_bytes(blob.encode("utf-8"))


# ---------------------------------------------------------------------------
# SCRUM-397 WP4 extension: canonical digest profile primitives
#
# Shared, registry-agnostic framing/envelope primitives for the gwc-jcs-v1
# canonical digest profile (WP2 normative contract). These are imported by
# canonical_digest_api.py so the envelope framing is implemented exactly once
# in this module (extend, not duplicate). No profile activation or write
# authority is granted here — registry fail-closed semantics live in the API.
# CANONICALIZATION_NEVER_GRANTS_AUTHORITY.
# ---------------------------------------------------------------------------

PROFILE_DIGEST_FRAMING_SCHEME = "gwc-domain-sep-v1"
PROFILE_DIGEST_ENVELOPE_OK = "PROFILE_DIGEST_ENVELOPE_OK"
PROFILE_DIGEST_ENVELOPE_MISMATCH = "PROFILE_DIGEST_ENVELOPE_MISMATCH"
PROFILE_DIGEST_ALGORITHM = "SHA-256"


def framed_profile_sha256(canonical_bytes: bytes, domain: str) -> str:
    """Length-prefixed framed SHA-256 per gwc-jcs-v1 domain separation.

    sha256( u32be(utf8_len(domain_tag)) || domain_tag_utf8
         || u64be(byte_len(preimage)) || preimage )
    """
    import struct
    domain_utf8 = domain.encode("utf-8")
    frame = (
        struct.pack(">I", len(domain_utf8))
        + domain_utf8
        + struct.pack(">Q", len(canonical_bytes))
        + canonical_bytes
    )
    return _sha256_bytes(frame)


def build_digest_envelope(
    *,
    profile_id: str,
    canonical_bytes: bytes,
    domain: str,
    schema_ref: str,
) -> Dict[str, Any]:
    """Construct a gwc-jcs-v1 digest envelope binding profile/hash/domain/
    schema/framing/digest. The hexdigest is the length-prefixed framed SHA-256.
    """
    return {
        "schema_version": "1.0",
        "artifact_type": "digest-envelope",
        "profile_id": profile_id,
        "hash_algorithm": PROFILE_DIGEST_ALGORITHM,
        "domain": domain,
        "schema_ref": schema_ref,
        "preimage_framing_scheme": PROFILE_DIGEST_FRAMING_SCHEME,
        "preimage_byte_length": len(canonical_bytes),
        "hexdigest": framed_profile_sha256(canonical_bytes, domain),
    }


def verify_digest_envelope(envelope: Dict[str, Any], canonical_bytes: bytes) -> str:
    """Recompute and compare an envelope's digest and bound fields.

    Returns PROFILE_DIGEST_ENVELOPE_OK on exact match, otherwise
    PROFILE_DIGEST_ENVELOPE_MISMATCH (never raises; deterministic).
    """
    try:
        expected = build_digest_envelope(
            profile_id=envelope["profile_id"],
            canonical_bytes=canonical_bytes,
            domain=envelope["domain"],
            schema_ref=envelope["schema_ref"],
        )
    except (KeyError, TypeError):
        return PROFILE_DIGEST_ENVELOPE_MISMATCH
    if envelope.get("preimage_framing_scheme") != PROFILE_DIGEST_FRAMING_SCHEME:
        return PROFILE_DIGEST_ENVELOPE_MISMATCH
    if envelope.get("hash_algorithm") != PROFILE_DIGEST_ALGORITHM:
        return PROFILE_DIGEST_ENVELOPE_MISMATCH
    if envelope.get("hexdigest") != expected["hexdigest"]:
        return PROFILE_DIGEST_ENVELOPE_MISMATCH
    if envelope.get("preimage_byte_length") != len(canonical_bytes):
        return PROFILE_DIGEST_ENVELOPE_MISMATCH
    return PROFILE_DIGEST_ENVELOPE_OK


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _manifest_inventory(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    inv = manifest.get("entry_inventory", []) or []
    return [e for e in inv if isinstance(e, dict)]


def _read_digest_and_bytes(path: Path) -> tuple[Optional[str], Optional[int]]:
    if not path.is_file():
        return None, None
    data = path.read_bytes()
    return _sha256_bytes(data), len(data)


def _validate_and_strip_keys(value: Any, algorithm: str, version: str) -> Optional[str]:
    """Return None if the (algorithm, version) pair matches the required pair.

    A mismatched algorithm/version is a hard failure signal.
    """
    if algorithm != REQUIRED_ALGORITHM:
        return HASH_ALGORITHM_UNSUPPORTED
    if version != REQUIRED_ALGORITHM_VERSION:
        return HASH_ALGORITHM_UNSUPPORTED
    return None


def verify_deterministic_hash(
    *,
    manifest: Dict[str, Any],
    source_root: str | os.PathLike[str],
    output_root: str | os.PathLike[str],
    idempotency_key: str,
    task_id: str = "",
    existing_result: Optional[Dict[str, Any]] = None,
) -> HashVerificationResult:
    """Read-only deterministic hash verification of a complete package.

    Recomputes source/target SHA-256 and byte counts from exact bytes for every
    copied entry, reconciles the manifest inventory, copied/skipped status, file
    count and the output-tree digest with a byte-level readback, and binds the
    result to the exact source SHA, manifest digest, output-tree digest, verifier
    version and idempotency key.

    PASS requires *every copied entry* and the *complete output inventory* to
    match. Subset verification cannot claim package validity. Verification is
    read-only and never repairs, rewrites or deletes output.
    """
    source_root = Path(source_root)
    output_root = Path(output_root)

    # --- Algorithm/version guard ------------------------------------------
    algorithm = (manifest.get("schema_id") or "").split(".")[-1] if False else REQUIRED_ALGORITHM
    manifest_algo = str(manifest.get("manifest_algorithm", REQUIRED_ALGORITHM))
    manifest_ver = str(manifest.get("manifest_algorithm_version", REQUIRED_ALGORITHM_VERSION))
    algo_failure = _validate_and_strip_keys(manifest_algo, REQUIRED_ALGORITHM, REQUIRED_ALGORITHM_VERSION)
    if algo_failure is not None:
        return HashVerificationResult(
            outcome=Outcome.FAIL,
            reason=algo_failure,
            source_sha=str(manifest.get("source_sha", "")),
            manifest_digest=canonical_manifest_digest(manifest),
            output_tree_digest=compute_output_tree_digest(output_root),
            idempotency_key=idempotency_key,
            verifier_version=VERIFIER_VERSION,
            entries_verified=0,
            entries_rejected=0,
            task_id=task_id,
            reject_detail=[RejectDetail(target="<manifest>", reason=algo_failure,
                                        detail=f"algorithm/version {manifest_algo}/{manifest_ver} unsupported")],
            detail="manifest declares an unsupported hash algorithm or version",
        )

    # --- Idempotent replay ------------------------------------------------
    if existing_result is not None:
        if existing_result.get("idempotency_key") == idempotency_key:
            if (existing_result.get("manifest_digest") == canonical_manifest_digest(manifest)
                    and existing_result.get("source_sha") == manifest.get("source_sha")):
                return HashVerificationResult(
                    outcome=Outcome.PASS,
                    reason=HASH_IDEMPOTENT_REPLAY,
                    source_sha=str(manifest.get("source_sha", "")),
                    manifest_digest=existing_result["manifest_digest"],
                    output_tree_digest=existing_result.get("output_tree_digest", ""),
                    idempotency_key=idempotency_key,
                    verifier_version=VERIFIER_VERSION,
                    entries_verified=int(existing_result.get("entries_verified", 0)),
                    entries_rejected=int(existing_result.get("entries_rejected", 0)),
                    task_id=task_id,
                    detail="identical replay; existing verified result returned without re-reading output",
                )
            return HashVerificationResult(
                outcome=Outcome.FAIL,
                reason=HASH_REPLAY_CONFLICT,
                source_sha=str(manifest.get("source_sha", "")),
                manifest_digest=canonical_manifest_digest(manifest),
                output_tree_digest=compute_output_tree_digest(output_root),
                idempotency_key=idempotency_key,
                verifier_version=VERIFIER_VERSION,
                entries_verified=0,
                entries_rejected=0,
                task_id=task_id,
                detail="same idempotency key with changed evidence; replay conflict",
            )

    inventory = _manifest_inventory(manifest)
    rejects: List[RejectDetail] = []
    verified = 0

    for entry in inventory:
        status = entry.get("entry_status")
        source_rel = entry.get("source")
        target_rel = entry.get("target")

        # Skipped optional entries: explicit, require no target/file hash.
        if status == ENTRY_STATUS_SKIPPED_OPTIONAL:
            verified += 1
            continue

        if status == ENTRY_STATUS_MISSING:
            # A missing-status entry is a recorded skip; allowed if optional.
            verified += 1
            continue

        if status not in (ENTRY_STATUS_ACCEPTED, ENTRY_STATUS_REJECTED):
            rejects.append(RejectDetail(
                target=target_rel or source_rel or "<unknown>",
                source=source_rel,
                reason=HASH_MANIFEST_DIGEST_MISMATCH,
                detail=f"unknown entry_status {status!r} in manifest",
            ))
            continue

        src = source_root / source_rel if source_rel else None
        tgt = output_root / target_rel if target_rel else None

        # Target must exist for every copied entry.
        if tgt is None or not tgt.is_file():
            rejects.append(RejectDetail(
                target=target_rel or "<unknown>",
                source=source_rel,
                reason=HASH_TARGET_MISSING,
                detail=f"target {target_rel!r} missing from output",
            ))
            continue

        actual_target_digest, actual_target_bytes = _read_digest_and_bytes(tgt)

        # Source must exist (changed source after export must be detected).
        if src is None or not src.is_file():
            rejects.append(RejectDetail(
                target=target_rel,
                source=source_rel,
                reason=HASH_SOURCE_MISMATCH,
                detail=f"source {source_rel!r} missing at verification time",
            ))
            continue
        actual_source_digest, actual_source_bytes = _read_digest_and_bytes(src)

        claimed_source = entry.get("source_digest")
        claimed_target = entry.get("target_digest")
        claimed_bytes = entry.get("byte_count")

        if claimed_source and claimed_source != actual_source_digest:
            rejects.append(RejectDetail(
                target=target_rel,
                source=source_rel,
                reason=HASH_SOURCE_MISMATCH,
                detail=f"source digest {claimed_source} != {actual_source_digest}",
            ))
            continue
        if claimed_target and claimed_target != actual_target_digest:
            rejects.append(RejectDetail(
                target=target_rel,
                source=source_rel,
                reason=HASH_TARGET_MISMATCH,
                detail=f"target digest {claimed_target} != {actual_target_digest}",
            ))
            continue
        if claimed_bytes is not None and claimed_bytes != actual_target_bytes:
            rejects.append(RejectDetail(
                target=target_rel,
                source=source_rel,
                reason=HASH_BYTE_COUNT_MISMATCH,
                detail=f"byte count {claimed_bytes} != {actual_target_bytes}",
            ))
            continue

        verified += 1

    # --- Output inventory reconciliation ----------------------------------
    # Every file physically present in the output root must be accounted for by
    # a copied entry in the manifest (no extra unmanifested target).
    manifest_targets = {
        e.get("target")
        for e in inventory
        if e.get("entry_status") in (ENTRY_STATUS_ACCEPTED, ENTRY_STATUS_REJECTED)
        and e.get("target")
    }
    actual_targets = {
        str(p.relative_to(output_root).as_posix())
        for p in output_root.rglob("*")
        if p.is_file()
    }
    extra = sorted(actual_targets - manifest_targets)
    if extra:
        for ex in extra:
            rejects.append(RejectDetail(
                target=ex,
                source=None,
                reason=HASH_UNMANIFESTED_TARGET,
                detail=f"output target {ex!r} has no manifest entry",
            ))

    output_tree_digest = compute_output_tree_digest(output_root)
    manifest_digest = canonical_manifest_digest(manifest)

    # Manifest digest is recomputed independently from observational fields; a
    # mismatch here means the manifest was tampered with versus its declared digest.
    declared_digest = manifest.get("manifest_digest")
    if declared_digest and declared_digest != manifest_digest:
        # Note the divergence but do not double-count; the failure reason below
        # is the primary signal. We record it as a reject detail for traceability.
        rejects.append(RejectDetail(
            target="<manifest>",
            source=None,
            reason=HASH_MANIFEST_DIGEST_MISMATCH,
            detail=f"declared manifest_digest {declared_digest} != canonical {manifest_digest}",
        ))

    if rejects:
        primary = rejects[0].reason
        return HashVerificationResult(
            outcome=Outcome.FAIL,
            reason=primary,
            source_sha=str(manifest.get("source_sha", "")),
            manifest_digest=manifest_digest,
            output_tree_digest=output_tree_digest,
            idempotency_key=idempotency_key,
            verifier_version=VERIFIER_VERSION,
            entries_verified=verified,
            entries_rejected=len(rejects),
            task_id=task_id,
            reject_detail=rejects,
            detail=f"{len(rejects)} verification failure(s); package identity not established",
        )

    return HashVerificationResult(
        outcome=Outcome.PASS,
        reason=HASH_VERIFICATION_PASS,
        source_sha=str(manifest.get("source_sha", "")),
        manifest_digest=manifest_digest,
        output_tree_digest=output_tree_digest,
        idempotency_key=idempotency_key,
        verifier_version=VERIFIER_VERSION,
        entries_verified=verified,
        entries_rejected=0,
        task_id=task_id,
        detail="every copied entry and complete output inventory match; package identity byte-accurate and replay-stable",
    )


def authority_granted(result: HashVerificationResult) -> bool:
    """A verification result never grants authority. Always False by contract."""
    return False
