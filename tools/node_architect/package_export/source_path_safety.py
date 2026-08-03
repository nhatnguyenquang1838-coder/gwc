#!/usr/bin/env python3
"""Source Path Safety Check — package_export.source-path-safety-check (M4_DETERMINISTIC).

Proves that every declared source path in a package export instruction is
safe, repository-relative and bound to an expected regular source file before
any export, copy or target evaluation happens.

Design invariants (from SCRUM-231 / F7 family contract):

* Pure evaluator over a pinned repository root. Read-only: it stats and reads
  source bytes to bind a digest, and never writes, copies or publishes.
* Syntax normalization never resolves outside the pinned root; escapes are
  rejected, not silently clamped.
* Required vs optional absence are distinct outcomes: optional absence is an
  explicit skippable result, required absence blocks.
* Unknown path state, permission failure or readback failure never becomes
  safe — everything fails closed.
* Deterministic: the same filesystem snapshot and the same input produce the
  same ordered results and the same semantic digest.
* Target evaluation, copying and consumer mutation are out of scope
  (SCRUM-232 and later nodes).
* A safe result never grants repository, PR, merge, deploy or release
  authority; it is execution-plane evidence only.
"""
from __future__ import annotations

import hashlib
import json
import os
import posixpath
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCHEMA_ID = "gwc.package_export.source_path_safety"
SCHEMA_VERSION = "0.1"

# ---------------------------------------------------------------------------
# Stable reason codes (closed taxonomy — do not extend without a schema bump)
# ---------------------------------------------------------------------------

SOURCE_PATH_SAFE = "SOURCE_PATH_SAFE"
SOURCE_PATH_EMPTY = "SOURCE_PATH_EMPTY"
SOURCE_PATH_ABSOLUTE = "SOURCE_PATH_ABSOLUTE"
SOURCE_PATH_TRAVERSAL = "SOURCE_PATH_TRAVERSAL"
SOURCE_PATH_BACKSLASH = "SOURCE_PATH_BACKSLASH"
SOURCE_PATH_ESCAPES_ROOT = "SOURCE_PATH_ESCAPES_ROOT"
SOURCE_SYMLINK_ESCAPE = "SOURCE_SYMLINK_ESCAPE"
SOURCE_REQUIRED_MISSING = "SOURCE_REQUIRED_MISSING"
SOURCE_OPTIONAL_MISSING = "SOURCE_OPTIONAL_MISSING"
SOURCE_NOT_REGULAR_FILE = "SOURCE_NOT_REGULAR_FILE"
SOURCE_READBACK_FAILED = "SOURCE_READBACK_FAILED"

REASON_CODES: Tuple[str, ...] = (
    SOURCE_PATH_SAFE,
    SOURCE_PATH_EMPTY,
    SOURCE_PATH_ABSOLUTE,
    SOURCE_PATH_TRAVERSAL,
    SOURCE_PATH_BACKSLASH,
    SOURCE_PATH_ESCAPES_ROOT,
    SOURCE_SYMLINK_ESCAPE,
    SOURCE_REQUIRED_MISSING,
    SOURCE_OPTIONAL_MISSING,
    SOURCE_NOT_REGULAR_FILE,
    SOURCE_READBACK_FAILED,
)

_BLOCKING_CODES = frozenset(
    {
        SOURCE_PATH_EMPTY,
        SOURCE_PATH_ABSOLUTE,
        SOURCE_PATH_TRAVERSAL,
        SOURCE_PATH_BACKSLASH,
        SOURCE_PATH_ESCAPES_ROOT,
        SOURCE_SYMLINK_ESCAPE,
        SOURCE_REQUIRED_MISSING,
        SOURCE_NOT_REGULAR_FILE,
        SOURCE_READBACK_FAILED,
    }
)


class Outcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class Disposition(str, Enum):
    ACCEPTED = "ACCEPTED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# Result contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceBinding:
    """Deterministic binding of an accepted source file."""

    canonical_path: str
    source_sha256: str
    byte_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_path": self.canonical_path,
            "source_sha256": self.source_sha256,
            "byte_count": self.byte_count,
        }


@dataclass(frozen=True)
class SourcePathVerdict:
    """One canonical, ordered per-entry verdict."""

    entry_index: int
    entry_id: str
    declared_path: str
    required: bool
    disposition: Disposition
    reason_code: str
    detail: str
    binding: Optional[SourceBinding] = None

    @property
    def blocking(self) -> bool:
        return self.disposition is Disposition.BLOCKED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_index": self.entry_index,
            "entry_id": self.entry_id,
            "declared_path": self.declared_path,
            "required": self.required,
            "disposition": self.disposition.value,
            "reason_code": self.reason_code,
            "detail": self.detail,
            "binding": self.binding.to_dict() if self.binding else None,
        }

    def sort_key(self) -> Tuple[str, int, str]:
        return (self.entry_id, self.entry_index, self.reason_code)


@dataclass(frozen=True)
class SourcePathSafetyResult:
    """Closed, versioned runtime result for source path safety checking."""

    schema_id: str
    schema_version: str
    outcome: Outcome
    repository: Optional[str]
    source_base_sha: Optional[str]
    input_digest: str
    verdicts: List[SourcePathVerdict] = field(default_factory=list)
    authority_granted: bool = False  # never grants authority

    @property
    def accepted(self) -> List[SourcePathVerdict]:
        return [v for v in self.verdicts if v.disposition is Disposition.ACCEPTED]

    @property
    def skipped(self) -> List[SourcePathVerdict]:
        return [v for v in self.verdicts if v.disposition is Disposition.SKIPPED]

    @property
    def blocked(self) -> List[SourcePathVerdict]:
        return [v for v in self.verdicts if v.disposition is Disposition.BLOCKED]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "outcome": self.outcome.value,
            "repository": self.repository,
            "source_base_sha": self.source_base_sha,
            "input_digest": self.input_digest,
            "verdicts": [v.to_dict() for v in self.verdicts],
            "authority_granted": self.authority_granted,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def semantic_digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Digest helpers
# ---------------------------------------------------------------------------


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_input_digest(entries: Sequence[Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(list(entries)).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> Tuple[str, int]:
    h = hashlib.sha256()
    count = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            count += len(chunk)
            h.update(chunk)
    return "sha256:" + h.hexdigest(), count


# ---------------------------------------------------------------------------
# Pure syntax evaluation (no filesystem access)
# ---------------------------------------------------------------------------


def normalize_relative_path(declared: Any) -> Tuple[Optional[str], str, str]:
    """Normalize a declared source path without leaving the pinned root.

    Returns ``(normalized_or_None, reason_code, detail)``.
    """
    if not isinstance(declared, str):
        return None, SOURCE_PATH_EMPTY, "source path must be a string"
    if declared.strip() == "":
        return None, SOURCE_PATH_EMPTY, "source path is empty"
    if "\\" in declared:
        return None, SOURCE_PATH_BACKSLASH, "backslash separators are not accepted"
    if "\x00" in declared:
        return None, SOURCE_PATH_EMPTY, "source path contains a NUL byte"
    if declared.startswith("/") or PurePosixPath(declared).is_absolute():
        return None, SOURCE_PATH_ABSOLUTE, "absolute source paths are not accepted"
    # Windows drive-letter form (e.g. "C:/x") is absolute in intent.
    if len(declared) >= 2 and declared[1] == ":" and declared[0].isalpha():
        return None, SOURCE_PATH_ABSOLUTE, "drive-qualified source paths are not accepted"

    parts = [p for p in declared.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None, SOURCE_PATH_TRAVERSAL, "parent traversal segment is not accepted"
    if not parts:
        return None, SOURCE_PATH_EMPTY, "source path normalizes to an empty path"

    normalized = posixpath.join(*parts)
    # Defensive: normalization must never yield an escape or absolute form.
    if normalized.startswith("/") or normalized.startswith("../"):
        return None, SOURCE_PATH_ESCAPES_ROOT, "normalized source path escapes the repository root"
    return normalized, SOURCE_PATH_SAFE, "normalized"


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Per-entry evaluation
# ---------------------------------------------------------------------------


def evaluate_entry(
    entry: Any,
    index: int,
    repo_root: Path,
    real_root: Path,
) -> SourcePathVerdict:
    entry_id: str
    if isinstance(entry, dict):
        raw_id = entry.get("id")
        entry_id = raw_id if isinstance(raw_id, str) else f"<entry:{index}>"
        declared = entry.get("path")
        required = bool(entry.get("required", True))
    else:
        entry_id = f"<entry:{index}>"
        declared = None
        required = True

    declared_repr = declared if isinstance(declared, str) else ""

    def blocked(code: str, detail: str) -> SourcePathVerdict:
        return SourcePathVerdict(
            entry_index=index,
            entry_id=entry_id,
            declared_path=declared_repr,
            required=required,
            disposition=Disposition.BLOCKED,
            reason_code=code,
            detail=detail,
        )

    normalized, code, detail = normalize_relative_path(declared)
    if normalized is None:
        return blocked(code, detail)

    absolute = repo_root / normalized
    if not _is_within(repo_root, absolute):
        return blocked(SOURCE_PATH_ESCAPES_ROOT, "resolved source path leaves the repository root")

    # Symlink-aware resolution: the *real* path must still be inside the root.
    try:
        exists = absolute.exists() or absolute.is_symlink()
    except OSError as exc:  # pragma: no cover - defensive
        return blocked(SOURCE_READBACK_FAILED, f"path state unavailable: {exc.__class__.__name__}")

    if not exists:
        if required:
            return blocked(SOURCE_REQUIRED_MISSING, "required source file is absent")
        return SourcePathVerdict(
            entry_index=index,
            entry_id=entry_id,
            declared_path=declared_repr,
            required=required,
            disposition=Disposition.SKIPPED,
            reason_code=SOURCE_OPTIONAL_MISSING,
            detail="optional source file is absent; entry is skippable",
        )

    try:
        real_path = absolute.resolve()
    except (OSError, RuntimeError) as exc:
        return blocked(SOURCE_READBACK_FAILED, f"path resolution failed: {exc.__class__.__name__}")

    if not _is_within(real_root, real_path):
        return blocked(SOURCE_SYMLINK_ESCAPE, "resolved link target escapes the repository root")

    try:
        st = os.stat(real_path)
    except OSError as exc:
        return blocked(SOURCE_READBACK_FAILED, f"stat failed: {exc.__class__.__name__}")

    import stat as _stat

    if not _stat.S_ISREG(st.st_mode):
        return blocked(SOURCE_NOT_REGULAR_FILE, "source path is not a regular file")

    try:
        digest, byte_count = _file_digest(real_path)
    except OSError as exc:
        return blocked(SOURCE_READBACK_FAILED, f"readback failed: {exc.__class__.__name__}")

    return SourcePathVerdict(
        entry_index=index,
        entry_id=entry_id,
        declared_path=declared_repr,
        required=required,
        disposition=Disposition.ACCEPTED,
        reason_code=SOURCE_PATH_SAFE,
        detail="source path is repository-relative, regular and readable",
        binding=SourceBinding(
            canonical_path=normalized,
            source_sha256=digest,
            byte_count=byte_count,
        ),
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def check_source_paths(
    entries: Sequence[Any],
    repo_root: os.PathLike | str,
    *,
    repository: Optional[str] = None,
    source_base_sha: Optional[str] = None,
) -> SourcePathSafetyResult:
    """Evaluate every declared source path against the pinned repository root."""
    root = Path(repo_root)
    try:
        real_root = root.resolve()
    except (OSError, RuntimeError):  # pragma: no cover - defensive
        real_root = root

    verdicts = [evaluate_entry(e, i, root, real_root) for i, e in enumerate(entries)]
    verdicts.sort(key=lambda v: v.sort_key())

    outcome = Outcome.FAIL if any(v.blocking for v in verdicts) else Outcome.PASS
    return SourcePathSafetyResult(
        schema_id=SCHEMA_ID,
        schema_version=SCHEMA_VERSION,
        outcome=outcome,
        repository=repository,
        source_base_sha=source_base_sha,
        input_digest=compute_input_digest(entries),
        verdicts=verdicts,
    )
