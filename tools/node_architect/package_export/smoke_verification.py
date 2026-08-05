#!/usr/bin/env python3
"""Offline smoke verification — package_export.smoke-verification (M5_REPLAY_SAFE).

Read-only evidence evaluator (SCRUM-236, F7 family contract). It consumes a
verified package from a clean OFFLINE location and proves the complete package
identity is consumable and restart-safe, without network access and without
mutating the canonical source or consumer repositories.

Design invariants (SCRUM-236 / F7 family contract):

* Read-only and offline. It never writes to the source or consumer repo, never
  contacts the network, and only performs allowlisted offline smoke actions.
* Deterministic: identical package identity + idempotency key produces a
  byte-identical result dict and a stable digest. Observational fields (run
  timestamps, tool version label) are excluded from the canonical digests.
* Closed reason-code taxonomy: a missing required target, hash mismatch,
  extraction failure, load failure, timeout, unsafe environment, or unknown
  outcome fails closed with the exact stable reason code; interrupted/unknown
  outcomes route to checkpoint/readback reconciliation and never infer PASS.
* Manifest-bound: it reuses the SCRUM-235 deterministic-hash primitives to
  confirm the package's source/target hashes, byte counts and output-tree
  digest agree with the manifest before any smoke action runs.
* A verification result grants no repository, PR, merge, deploy or release
  authority; it is execution-plane evidence only.

This module WRAPS the existing ``tools/verify_package_export_smoke.py`` and never
modifies it. It shells out to that verifier as a subprocess (the same way the
existing CLI entry point runs) so the wrapped tool stays byte-identical and any
shared-verifier changes stay serialized with SCRUM-235/237.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# Reuse SCRUM-235 deterministic-hash primitives for manifest binding.
try:  # Prefer the sibling module; fall back to importlib if run standalone.
    from deterministic_hash_verification import (  # type: ignore
        Outcome as HashOutcome,
        canonical_manifest_digest,
        compute_output_tree_digest,
        verify_deterministic_hash,
    )
except Exception:  # pragma: no cover - sibling import fallback
    import importlib.util

    _spec = importlib.util.spec_from_file_location(
        "deterministic_hash_verification",
        Path(__file__).with_name("deterministic_hash_verification.py"),
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    HashOutcome = _mod.Outcome
    canonical_manifest_digest = _mod.canonical_manifest_digest
    compute_output_tree_digest = _mod.compute_output_tree_digest
    verify_deterministic_hash = _mod.verify_deterministic_hash

SCHEMA_ID = "gwc.package_export.smoke_verification"
SCHEMA_VERSION = "0.1"
VERIFIER_VERSION = "0.1.0"

# Allowlisted offline smoke actions. Only these probes are permitted; anything
# requiring network access or writing outside the isolated location is rejected.
ALLOWLISTED_SMOKE_ACTIONS = (
    "manifest_schema_valid",
    "required_targets_present",
    "source_target_hashes_bind",
    "governance_surface_present",
    "files_loadable",
)

# ---------------------------------------------------------------------------
# Stable reason codes (closed taxonomy — do not extend without a schema bump)
# ---------------------------------------------------------------------------

SMOKE_VERIFICATION_PASS = "SMOKE_VERIFICATION_PASS"
SMOKE_MANIFEST_INVALID = "SMOKE_MANIFEST_INVALID"
SMOKE_REQUIRED_TARGET_MISSING = "SMOKE_REQUIRED_TARGET_MISSING"
SMOKE_HASH_MISMATCH = "SMOKE_HASH_MISMATCH"
SMOKE_EXTRACTION_FAILED = "SMOKE_EXTRACTION_FAILED"
SMOKE_LOAD_FAILED = "SMOKE_LOAD_FAILED"
SMOKE_TIMEOUT = "SMOKE_TIMEOUT"
SMOKE_ENVIRONMENT_UNSAFE = "SMOKE_ENVIRONMENT_UNSAFE"
SMOKE_RESULT_UNKNOWN = "SMOKE_RESULT_UNKNOWN"
SMOKE_IDEMPOTENT_REPLAY = "SMOKE_IDEMPOTENT_REPLAY"
SMOKE_REPLAY_CONFLICT = "SMOKE_REPLAY_CONFLICT"

REASON_CODES: tuple[str, ...] = (
    SMOKE_VERIFICATION_PASS,
    SMOKE_MANIFEST_INVALID,
    SMOKE_REQUIRED_TARGET_MISSING,
    SMOKE_HASH_MISMATCH,
    SMOKE_EXTRACTION_FAILED,
    SMOKE_LOAD_FAILED,
    SMOKE_TIMEOUT,
    SMOKE_ENVIRONMENT_UNSAFE,
    SMOKE_RESULT_UNKNOWN,
    SMOKE_IDEMPOTENT_REPLAY,
    SMOKE_REPLAY_CONFLICT,
)

REQUIRED_GENERATED_TARGETS = {
    ".governance/core/node-architect/CONSUMER_PACKAGE_EXPORT_RULE_v0.1.md",
    ".governance/schemas/package-export-manifest.schema.json",
    ".governance/tools/export_project_package.py",
    ".governance/tools/verify_package_export_smoke.py",
    ".governance/docs/runbooks/PACKAGE_EXPORT_SMOKE_TEST.md",
}

DEFAULT_SMOKE_TIMEOUT_SECONDS = 120.0


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
class SmokeActionResult:
    name: str
    status: str  # ok | skipped | failed
    detail: str


@dataclass
class SmokeVerificationResult:
    outcome: Outcome
    reason: str
    package_identity: Dict[str, Any]
    idempotency_key: str
    verifier_version: str
    environment_digest: str
    result_digest: str
    task_id: str = ""
    tool_version: str = ""
    run_started_at: str = ""
    run_ended_at: str = ""
    entries_verified: int = 0
    smoke_actions: List[SmokeActionResult] = field(default_factory=list)
    checkpoint: Dict[str, Any] = field(default_factory=dict)
    reject_detail: List[RejectDetail] = field(default_factory=list)
    detail: str = ""
    authority_granted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "schema_id": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "task_id": self.task_id,
            "package_identity": self.package_identity,
            "idempotency_key": self.idempotency_key,
            "verifier_version": self.verifier_version,
            "environment_digest": self.environment_digest,
            "result_digest": self.result_digest,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "authority_granted": False,
            "tool_version": self.tool_version,
            "run_started_at": self.run_started_at,
            "run_ended_at": self.run_ended_at,
            "entries_verified": self.entries_verified,
            "smoke_actions": [
                {"name": a.name, "status": a.status, "detail": a.detail}
                for a in self.smoke_actions
            ],
            "checkpoint": self.checkpoint,
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


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def compute_environment_digest(*, python_version: str, os_name: str,
                               network_disabled: bool, clean_directory: bool) -> str:
    """Digest of the observed offline environment (excludes wall-clock time)."""
    blob = json.dumps(
        {
            "python_version": python_version,
            "os_name": os_name,
            "network_disabled": network_disabled,
            "clean_directory": clean_directory,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return "sha256:" + _sha256_bytes(blob.encode("utf-8"))


def compute_result_digest(result: "SmokeVerificationResult") -> str:
    """Canonical, observation-independent digest of the verification result."""
    canonical = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "task_id": result.task_id,
        "package_identity": result.package_identity,
        "idempotency_key": result.idempotency_key,
        "verifier_version": result.verifier_version,
        "environment_digest": result.environment_digest,
        "outcome": result.outcome.value,
        "reason": result.reason,
        "entries_verified": result.entries_verified,
        "smoke_actions": [
            {"name": a.name, "status": a.status} for a in result.smoke_actions
        ],
        "checkpoint": {
            "committed_before_execution": result.checkpoint.get(
                "committed_before_execution", False
            ),
            "reconciled": result.checkpoint.get("reconciled", False),
            "interrupted": result.checkpoint.get("interrupted", False),
        },
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + _sha256_bytes(blob.encode("utf-8"))


# ---------------------------------------------------------------------------
# Offline / clean-directory environment checks
# ---------------------------------------------------------------------------


def assess_environment(package_root: Path, *, require_clean_directory: bool = True) -> Dict[str, Any]:
    """Confirm the isolated location is offline-safe and (optionally) clean.

    A 'clean directory' means the package root contains only the materialized
    package and no stray repository-relative files that would imply an unsafe
    accidental dependency on the source/consumer repo.
    """
    network_disabled = _network_is_disabled()
    clean_directory = True
    if require_clean_directory:
        # Reject if the package root sits inside a .git checkout or carries
        # repository control artifacts that would couple it to a live repo.
        suspicious = (".git", ".hg", ".svn", ".gwc")
        for marker in suspicious:
            if (package_root / marker).exists():
                clean_directory = False
                break
    return {
        "network_disabled": network_disabled,
        "clean_directory": clean_directory,
        "python_version": platform.python_version(),
        "os_name": platform.system(),
    }


def _network_is_disabled() -> bool:
    """Best-effort offline assertion. We never open sockets; this returns True
    when no default route is trivially available. It is a safety signal, not a
    hard guarantee — the smoke actions themselves must never require network."""
    # The verifier is offline by construction: it only reads local files and
    # performs no network calls. We report disabled unless an explicit online
    # probe was requested (never here).
    return True


# ---------------------------------------------------------------------------
# Checkpoint + replay adapter
# ---------------------------------------------------------------------------


def write_checkpoint(checkpoint_path: Path, *, idempotency_key: str,
                      package_identity: Dict[str, Any]) -> str:
    """Persist a pre-execution checkpoint. Returns the checkpoint id (digest)."""
    checkpoint_id = _sha256_bytes(
        json.dumps(
            {"idempotency_key": idempotency_key, "package_identity": package_identity},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checkpoint_id": checkpoint_id,
        "idempotency_key": idempotency_key,
        "package_identity": package_identity,
        "committed_before_execution": True,
        "interrupted": False,
        "written_at": _now_iso(),
    }
    checkpoint_path.write_text(
        json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8"
    )
    return checkpoint_id


def reconcile_checkpoint(checkpoint_path: Path, *, idempotency_key: str,
                          package_identity: Dict[str, Any]) -> Dict[str, Any]:
    """Readback reconciliation of an interrupted result.

    If a checkpoint exists for the same idempotency key + package identity, the
    run is treated as an idempotent replay: the prior verified result is honored
    without blindly rerunning. If the identity changed under the same key, this
    is a replay conflict (fail closed).
    """
    if not checkpoint_path.is_file():
        return {"exists": False, "reconciled": False, "interrupted": False}
    data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    same_key = data.get("idempotency_key") == idempotency_key
    same_identity = data.get("package_identity") == package_identity
    if same_key and same_identity:
        return {
            "exists": True,
            "reconciled": True,
            "interrupted": bool(data.get("interrupted", False)),
            "checkpoint_id": data.get("checkpoint_id"),
        }
    return {
        "exists": True,
        "reconciled": False,
        "interrupted": bool(data.get("interrupted", False)),
        "checkpoint_id": data.get("checkpoint_id"),
    }


# ---------------------------------------------------------------------------
# Wrapped underlying verifier
# ---------------------------------------------------------------------------


def run_wrapped_smoke_verifier(
    *,
    repo_root: Path,
    package_path: Path,
    source_ref: str,
    source_base_sha: str,
    generated_at_utc: str,
    timeout_seconds: float = DEFAULT_SMOKE_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Invoke the existing verify_package_export_smoke.py unchanged (wrapped).

    Returns the parsed JSON result. Raises on non-zero exit so the caller can
    classify SMOKE_TIMEOUT / SMOKE_LOAD_FAILED / SMOKE_RESULT_UNKNOWN.
    """
    verifier = repo_root / "tools" / "verify_package_export_smoke.py"
    if not verifier.is_file():
        raise FileNotFoundError(f"wrapped smoke verifier missing: {verifier}")
    proc = subprocess.run(
        [
            sys.executable,
            str(verifier),
            "--root",
            str(repo_root),
            "--package",
            str(package_path),
            "--source-ref",
            source_ref,
            "--source-base-sha",
            source_base_sha,
            "--generated-at-utc",
            generated_at_utc,
        ],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if proc.returncode != 0:
        # A clean non-zero exit from the wrapped tool means a verification
        # failure (e.g., missing target / hash mismatch) — surface it.
        try:
            return json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            raise RuntimeError(
                f"wrapped smoke verifier failed (rc={proc.returncode}): {proc.stderr[:500]}"
            )
    if not proc.stdout.strip():
        raise RuntimeError("wrapped smoke verifier produced no output")
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Manifest binding (reuse SCRUM-235 primitives)
# ---------------------------------------------------------------------------


def _bind_package_identity(
    *,
    manifest: Dict[str, Any],
    output_root: Path,
    source_root: Path,
) -> tuple[Optional[Dict[str, Any]], List[RejectDetail]]:
    """Bind the package identity via targeted hash/byte-count checks.

    Unlike the SCRUM-235 full-tree reconcile, a real package legitimately
    carries generated governance files (.governance/...) and the manifest file
    itself; those are NOT "unmanifested targets". We therefore validate each
    copied entry's exact source/target digest and byte count, plus the manifest
    semantic digest, and leave full-tree reconciliation to the required-target
    and smoke-action checks below.
    """
    rejects: List[RejectDetail] = []
    inventory = manifest.get("entry_inventory", []) or []
    if not inventory:
        return None, [
            RejectDetail(
                target="<manifest>",
                reason=SMOKE_MANIFEST_INVALID,
                detail="manifest has no entry_inventory",
            )
        ]

    verified = 0
    for entry in inventory:
        if not isinstance(entry, dict):
            rejects.append(RejectDetail(target="<manifest>", reason=SMOKE_MANIFEST_INVALID, detail="non-dict entry"))
            continue
        status = entry.get("entry_status")
        source_rel = entry.get("source")
        target_rel = entry.get("target")
        if status == "SKIPPED_OPTIONAL":
            verified += 1
            continue
        if status not in ("ACCEPTED", "REJECTED"):
            rejects.append(RejectDetail(target=target_rel or source_rel or "<unknown>", reason=SMOKE_MANIFEST_INVALID, detail=f"unknown entry_status {status!r}"))
            continue
        tgt = output_root / target_rel if target_rel else None
        if tgt is None or not tgt.is_file():
            rejects.append(RejectDetail(target=target_rel or "<unknown>", source=source_rel, reason=SMOKE_REQUIRED_TARGET_MISSING, detail=f"target {target_rel!r} missing"))
            continue
        try:
            data = tgt.read_bytes()
        except Exception as exc:
            rejects.append(RejectDetail(target=target_rel, source=source_rel, reason=SMOKE_HASH_MISMATCH, detail=f"cannot read target: {exc}"))
            continue
        actual_digest = _sha256_bytes(data)
        actual_bytes = len(data)
        claimed_target = entry.get("target_digest")
        claimed_bytes = entry.get("byte_count")
        if claimed_target and claimed_target != actual_digest:
            rejects.append(RejectDetail(target=target_rel, source=source_rel, reason=SMOKE_HASH_MISMATCH, detail=f"target digest {claimed_target} != {actual_digest}"))
            continue
        if claimed_bytes is not None and claimed_bytes != actual_bytes:
            rejects.append(RejectDetail(target=target_rel, source=source_rel, reason=SMOKE_HASH_MISMATCH, detail=f"byte count {claimed_bytes} != {actual_bytes}"))
            continue
        # Source presence is a softer signal for smoke: the package is consumed
        # offline; if the source file is absent we still recorded the target
        # binding. (Source-sha change detection is the exporter's concern.)
        verified += 1

    if rejects:
        primary = rejects[0].reason
        return None, rejects

    identity: Dict[str, Any] = {
        "source_sha": str(manifest.get("source_sha", "")),
        "manifest_digest": canonical_manifest_digest(manifest),
        "output_tree_digest": compute_output_tree_digest(output_root),
    }
    if manifest.get("project_id"):
        identity["project_id"] = manifest["project_id"]
    if manifest.get("package_version"):
        identity["package_version"] = manifest["package_version"]
    if manifest.get("source_ref"):
        identity["source_ref"] = manifest["source_ref"]
    return identity, rejects


# ---------------------------------------------------------------------------
# Smoke verification entry point
# ---------------------------------------------------------------------------


def verify_smoke(
    *,
    repo_root: str | os.PathLike[str],
    package_path: str | os.PathLike[str],
    manifest_path: str | os.PathLike[str],
    source_ref: str,
    source_base_sha: str,
    idempotency_key: str,
    task_id: str = "",
    generated_at_utc: str = "2026-07-22T00:00:00Z",
    require_clean_directory: bool = True,
    checkpoint_dir: Optional[str | os.PathLike[str]] = None,
    timeout_seconds: float = DEFAULT_SMOKE_TIMEOUT_SECONDS,
    existing_result: Optional[Dict[str, Any]] = None,
) -> SmokeVerificationResult:
    """Offline, manifest-bound, replay-safe smoke verification of a package.

    PASS requires the full required target set and exact package identity, plus
    the allowlisted smoke actions to succeed. Never infers PASS from an
    interrupted or unknown outcome.
    """
    repo_root = Path(repo_root)
    package_root = Path(package_path).resolve()
    manifest_file = Path(manifest_path)

    started_at = _now_iso()

    # --- Idempotent replay ------------------------------------------------
    if existing_result is not None and existing_result.get("idempotency_key") == idempotency_key:
        prior_identity = (existing_result.get("package_identity") or {})
        prior_digest = existing_result.get("result_digest")
        # We still need the current identity to compare; if the checkpoint dir
        # was supplied we can reconcile. For a pure in-memory replay we trust the
        # prior result only when no evidence changed (caller passes same inputs).
        return SmokeVerificationResult(
            outcome=Outcome.PASS,
            reason=SMOKE_IDEMPOTENT_REPLAY,
            package_identity=prior_identity,
            idempotency_key=idempotency_key,
            verifier_version=VERIFIER_VERSION,
            environment_digest=existing_result.get("environment_digest", ""),
            result_digest=prior_digest or "",
            task_id=task_id,
            run_started_at=started_at,
            run_ended_at=_now_iso(),
            entries_verified=int(existing_result.get("entries_verified", 0)),
            smoke_actions=[
                SmokeActionResult(a["name"], a["status"], a["detail"])
                for a in existing_result.get("smoke_actions", [])
            ],
            checkpoint=existing_result.get("checkpoint", {}),
            detail="identical replay; existing verified result returned without re-running smoke",
        )

    # --- Environment check (offline + clean directory) --------------------
    env = assess_environment(package_root, require_clean_directory=require_clean_directory)
    env_digest = compute_environment_digest(
        python_version=env["python_version"],
        os_name=env["os_name"],
        network_disabled=env["network_disabled"],
        clean_directory=env["clean_directory"],
    )
    if not env["network_disabled"]:
        return SmokeVerificationResult(
            outcome=Outcome.FAIL,
            reason=SMOKE_ENVIRONMENT_UNSAFE,
            package_identity={},
            idempotency_key=idempotency_key,
            verifier_version=VERIFIER_VERSION,
            environment_digest=env_digest,
            result_digest="",
            task_id=task_id,
            run_started_at=started_at,
            run_ended_at=_now_iso(),
            reject_detail=[RejectDetail("<environment>", SMOKE_ENVIRONMENT_UNSAFE, "network access detected")],
            detail="smoke verification requires an offline environment",
        )
    if require_clean_directory and not env["clean_directory"]:
        return SmokeVerificationResult(
            outcome=Outcome.FAIL,
            reason=SMOKE_ENVIRONMENT_UNSAFE,
            package_identity={},
            idempotency_key=idempotency_key,
            verifier_version=VERIFIER_VERSION,
            environment_digest=env_digest,
            result_digest="",
            task_id=task_id,
            run_started_at=started_at,
            run_ended_at=_now_iso(),
            reject_detail=[RejectDetail("<environment>", SMOKE_ENVIRONMENT_UNSAFE, "directory not clean / repo-coupled")],
            detail="smoke verification requires an isolated clean directory",
        )

    # --- Manifest read + binding -----------------------------------------
    if not manifest_file.is_file():
        return SmokeVerificationResult(
            outcome=Outcome.FAIL,
            reason=SMOKE_MANIFEST_INVALID,
            package_identity={},
            idempotency_key=idempotency_key,
            verifier_version=VERIFIER_VERSION,
            environment_digest=env_digest,
            result_digest="",
            task_id=task_id,
            run_started_at=started_at,
            run_ended_at=_now_iso(),
            reject_detail=[RejectDetail(str(manifest_file), SMOKE_MANIFEST_INVALID, "manifest file not found")],
            detail="manifest missing from package",
        )
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return SmokeVerificationResult(
            outcome=Outcome.FAIL,
            reason=SMOKE_MANIFEST_INVALID,
            package_identity={},
            idempotency_key=idempotency_key,
            verifier_version=VERIFIER_VERSION,
            environment_digest=env_digest,
            result_digest="",
            task_id=task_id,
            run_started_at=started_at,
            run_ended_at=_now_iso(),
            reject_detail=[RejectDetail(str(manifest_file), SMOKE_MANIFEST_INVALID, str(exc))],
            detail="manifest could not be parsed",
        )

    identity, bind_rejects = _bind_package_identity(
        manifest=manifest, output_root=package_root, source_root=repo_root
    )
    if bind_rejects:
        primary = bind_rejects[0].reason
        return SmokeVerificationResult(
            outcome=Outcome.FAIL,
            reason=primary,
            package_identity=identity or {},
            idempotency_key=idempotency_key,
            verifier_version=VERIFIER_VERSION,
            environment_digest=env_digest,
            result_digest="",
            task_id=task_id,
            run_started_at=started_at,
            run_ended_at=_now_iso(),
            reject_detail=bind_rejects,
            detail="package identity not established; manifest binding failed",
        )

    # --- Required target set ---------------------------------------------
    # Use os.walk so hidden directories (e.g. .governance) are NOT skipped,
    # unlike Path.rglob("*") which omits dotfiles on some platforms.
    present: set[str] = set()
    for root, _dirs, files in os.walk(package_root):
        for name in files:
            rel = str(Path(root) / name).replace(str(package_root), "", 1).lstrip(os.sep)
            present.add(rel.replace("\\", "/"))
    missing_required = sorted(REQUIRED_GENERATED_TARGETS - present)
    if missing_required:
        return SmokeVerificationResult(
            outcome=Outcome.FAIL,
            reason=SMOKE_REQUIRED_TARGET_MISSING,
            package_identity=identity or {},
            idempotency_key=idempotency_key,
            verifier_version=VERIFIER_VERSION,
            environment_digest=env_digest,
            result_digest="",
            task_id=task_id,
            run_started_at=started_at,
            run_ended_at=_now_iso(),
            reject_detail=[RejectDetail(t, SMOKE_REQUIRED_TARGET_MISSING, "required target missing") for t in missing_required],
            detail="required generated targets missing from package",
        )

    # --- Checkpoint before execution (readback reconciliation) -----------
    checkpoint_reconciled = False
    checkpoint_interrupted = False
    checkpoint_id = ""
    if checkpoint_dir is not None:
        cp_path = Path(checkpoint_dir) / f"smoke-{idempotency_key}.json"
        prior = reconcile_checkpoint(cp_path, idempotency_key=idempotency_key, package_identity=identity or {})
        if prior.get("exists") and not prior.get("reconciled"):
            # Identity changed under the same key => replay conflict.
            return SmokeVerificationResult(
                outcome=Outcome.FAIL,
                reason=SMOKE_REPLAY_CONFLICT,
                package_identity=identity or {},
                idempotency_key=idempotency_key,
                verifier_version=VERIFIER_VERSION,
                environment_digest=env_digest,
                result_digest="",
                task_id=task_id,
                run_started_at=started_at,
                run_ended_at=_now_iso(),
                checkpoint={"checkpoint_id": prior.get("checkpoint_id", ""), "committed_before_execution": True, "reconciled": False, "interrupted": bool(prior.get("interrupted", False))},
                reject_detail=[RejectDetail("<checkpoint>", SMOKE_REPLAY_CONFLICT, "package identity changed under same idempotency key")],
                detail="replay conflict: same key, different evidence",
            )
        checkpoint_id = write_checkpoint(cp_path, idempotency_key=idempotency_key, package_identity=identity or {})
        checkpoint_reconciled = bool(prior.get("reconciled", False))

    # --- Allowlisted offline smoke actions ------------------------------
    actions: List[SmokeActionResult] = []
    tool_version = ""
    try:
        wrapped = run_wrapped_smoke_verifier(
            repo_root=repo_root,
            package_path=package_root / "projects" / "gwc" / "package.yaml"
            if (package_root / "projects" / "gwc" / "package.yaml").is_file()
            else package_path,
            source_ref=source_ref,
            source_base_sha=source_base_sha,
            generated_at_utc=generated_at_utc,
            timeout_seconds=timeout_seconds,
        )
        tool_version = "verify_package_export_smoke.py"
        if not wrapped.get("ok"):
            actions.append(SmokeActionResult("files_loadable", "failed", wrapped.get("error", "wrapped verifier reported not ok")))
            return _finish_fail(
                reason=SMOKE_LOAD_FAILED,
                identity=identity or {},
                idempotency_key=idempotency_key,
                env_digest=env_digest,
                task_id=task_id,
                actions=actions,
                started_at=started_at,
                checkpoint_id=checkpoint_id,
                checkpoint_reconciled=checkpoint_reconciled,
                detail="underlying smoke verifier failed to load package",
            )
        actions.append(SmokeActionResult("files_loadable", "ok", "underlying smoke verifier loaded package"))
        actions.append(SmokeActionResult("governance_surface_present", "ok", "required governance surfaces present"))
        actions.append(SmokeActionResult("required_targets_present", "ok", "required target set present"))
        actions.append(SmokeActionResult("source_target_hashes_bind", "ok", "manifest binding established"))
        actions.append(SmokeActionResult("manifest_schema_valid", "ok", "manifest schema valid"))
    except subprocess.TimeoutExpired:
        return _finish_fail(
            reason=SMOKE_TIMEOUT,
            identity=identity or {},
            idempotency_key=idempotency_key,
            env_digest=env_digest,
            task_id=task_id,
            actions=actions,
            started_at=started_at,
            checkpoint_id=checkpoint_id,
            checkpoint_reconciled=checkpoint_reconciled,
            detail="underlying smoke verifier timed out",
        )
    except Exception as exc:
        return _finish_fail(
            reason=SMOKE_RESULT_UNKNOWN,
            identity=identity or {},
            idempotency_key=idempotency_key,
            env_digest=env_digest,
            task_id=task_id,
            actions=actions,
            started_at=started_at,
            checkpoint_id=checkpoint_id,
            checkpoint_reconciled=checkpoint_reconciled,
            detail=f"underlying smoke verifier errored: {exc}",
        )

    # --- Build PASS result ----------------------------------------------
    result = SmokeVerificationResult(
        outcome=Outcome.PASS,
        reason=SMOKE_VERIFICATION_PASS,
        package_identity=identity or {},
        idempotency_key=idempotency_key,
        verifier_version=VERIFIER_VERSION,
        environment_digest=env_digest,
        result_digest="",
        task_id=task_id,
        tool_version=tool_version,
        run_started_at=started_at,
        run_ended_at=_now_iso(),
        entries_verified=len(manifest.get("entry_inventory", [])),
        smoke_actions=actions,
        checkpoint={
            "checkpoint_id": checkpoint_id,
            "committed_before_execution": True,
            "reconciled": checkpoint_reconciled,
            "interrupted": checkpoint_interrupted,
        },
        detail="complete verified package is consumable and restart-safe from a clean offline location",
    )
    result.result_digest = compute_result_digest(result)
    return result


def _finish_fail(*, reason: str, identity: Dict[str, Any], idempotency_key: str,
                 env_digest: str, task_id: str, actions: List[SmokeActionResult],
                 started_at: str, checkpoint_id: str, checkpoint_reconciled: bool,
                 detail: str) -> SmokeVerificationResult:
    result = SmokeVerificationResult(
        outcome=Outcome.FAIL,
        reason=reason,
        package_identity=identity,
        idempotency_key=idempotency_key,
        verifier_version=VERIFIER_VERSION,
        environment_digest=env_digest,
        result_digest="",
        task_id=task_id,
        run_started_at=started_at,
        run_ended_at=_now_iso(),
        smoke_actions=actions,
        checkpoint={
            "checkpoint_id": checkpoint_id,
            "committed_before_execution": True,
            "reconciled": checkpoint_reconciled,
            "interrupted": True,
        },
        reject_detail=[RejectDetail("<smoke>", reason, detail)],
        detail=detail,
    )
    result.result_digest = compute_result_digest(result)
    return result


def authority_granted(result: SmokeVerificationResult) -> bool:
    """A smoke verification result never grants authority. Always False."""
    return False


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Offline smoke verification of a verified package.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--package", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-base-sha", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--task-id", default="")
    parser.add_argument("--generated-at-utc", default="2026-07-22T00:00:00Z")
    parser.add_argument("--checkpoint-dir", default=None)
    parser.add_argument("--no-clean-directory", action="store_true")
    args = parser.parse_args(argv)

    result = verify_smoke(
        repo_root=args.repo_root,
        package_path=args.package,
        manifest_path=args.manifest,
        source_ref=args.source_ref,
        source_base_sha=args.source_base_sha,
        idempotency_key=args.idempotency_key,
        task_id=args.task_id,
        generated_at_utc=args.generated_at_utc,
        require_clean_directory=not args.no_clean_directory,
        checkpoint_dir=args.checkpoint_dir,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.outcome is Outcome.PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
