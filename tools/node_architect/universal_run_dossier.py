#!/usr/bin/env python3
"""R6: Run Dossier evidence, distinct G3/G4/G5 records, target validation,
ClosureReceipt, HandoffReceipt, and durable RunLedger append.

C7 (distinct G3 verification, G4 binding, G5 validation and G6
Closure/HandoffReceipt) per the C1-C15 matrix. Composes E1 kernel digest
primitives and the authority EffectDecisionReceipt; reuses record-envelope +
child-run-materialization-receipt schema shapes.

Pure / transport-neutral: never persists to external stores, never grants
authority, never mutates targets. The RunLedger is a serializable in-memory
facade whose entries round-trip through to_dict/from_dict (durable append).
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from tools.node_architect.universal_run_kernel import UNIVERSAL_PROFILE, UniversalRunKernelError

PROFILE = UNIVERSAL_PROFILE
DISTINCT_GATES = ("G3", "G4", "G5")


class DossierError(ValueError):
    """Deterministic fail-closed dossier error."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise DossierError(code, detail)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_digest(*parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(_canonical_json_bytes(part))
    return "sha256:" + h.hexdigest()


@dataclass(frozen=True)
class RunDossier:
    """Immutable Run Dossier with distinct G3/G4/G5 record buckets (C7)."""

    run_id: str
    g3_records: tuple[dict[str, Any], ...]
    g4_records: tuple[dict[str, Any], ...]
    g5_records: tuple[dict[str, Any], ...]
    dossier_digest: str = field(default_factory=str)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "run-dossier",
            "run_id": self.run_id,
            "g3_records": [copy.deepcopy(r) for r in self.g3_records],
            "g4_records": [copy.deepcopy(r) for r in self.g4_records],
            "g5_records": [copy.deepcopy(r) for r in self.g5_records],
            "dossier_digest": self.dossier_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunDossier":
        return cls(
            run_id=str(data.get("run_id", "")),
            g3_records=tuple(data.get("g3_records", [])),
            g4_records=tuple(data.get("g4_records", [])),
            g5_records=tuple(data.get("g5_records", [])),
            dossier_digest=str(data.get("dossier_digest", "")),
        )

    def _replace_g3(self, records: list[dict[str, Any]]) -> None:
        # Test-only mutation helper to prove digest validation catches tampering.
        object.__setattr__(self, "g3_records", tuple(records))


@dataclass(frozen=True)
class ClosureReceipt:
    """G6 ClosureReceipt: typed, digest-bound (C7)."""

    run_id: str
    gate: str
    closure_reason: str
    receipt_digest: str = field(default_factory=str)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "closure-receipt",
            "run_id": self.run_id,
            "gate": self.gate,
            "closure_reason": self.closure_reason,
            "receipt_digest": self.receipt_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ClosureReceipt":
        return cls(
            run_id=str(data.get("run_id", "")),
            gate=str(data.get("gate", "")),
            closure_reason=str(data.get("closure_reason", "")),
            receipt_digest=str(data.get("receipt_digest", "")),
        )


@dataclass(frozen=True)
class HandoffReceipt:
    """G6 HandoffReceipt: target validation + child acceptance (C7)."""

    run_id: str
    target_validation: dict[str, Any]
    child_acceptance: tuple[dict[str, Any], ...]
    receipt_digest: str = field(default_factory=str)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "handoff-receipt",
            "run_id": self.run_id,
            "target_validation": copy.deepcopy(self.target_validation),
            "child_acceptance": [copy.deepcopy(c) for c in self.child_acceptance],
            "receipt_digest": self.receipt_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HandoffReceipt":
        return cls(
            run_id=str(data.get("run_id", "")),
            target_validation=dict(data.get("target_validation", {}) or {}),
            child_acceptance=tuple(data.get("child_acceptance", [])),
            receipt_digest=str(data.get("receipt_digest", "")),
        )


def create_run_dossier(
    *,
    run_id: str,
    g3_records: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    g4_records: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    g5_records: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> RunDossier:
    """Create an immutable Run Dossier with distinct G3/G4/G5 buckets (C7)."""
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID")
    g3 = tuple(copy.deepcopy(r) for r in (g3_records or []))
    g4 = tuple(copy.deepcopy(r) for r in (g4_records or []))
    g5 = tuple(copy.deepcopy(r) for r in (g5_records or []))
    digest = _sha256_digest(run_id, g3, g4, g5)
    return RunDossier(run_id=run_id, g3_records=g3, g4_records=g4, g5_records=g5, dossier_digest=digest)


def validate_dossier(dossier: RunDossier) -> bool:
    """Verify dossier digest against its canonical records (C7)."""
    try:
        expected = _sha256_digest(dossier.run_id, dossier.g3_records, dossier.g4_records, dossier.g5_records)
        return dossier.dossier_digest == expected
    except Exception:
        return False


def create_closure_receipt(
    *,
    run_id: str,
    gate: str,
    closure_reason: str,
) -> ClosureReceipt:
    """Create a G6 ClosureReceipt (C7). Gate must be G6."""
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID")
    _require(gate == "G6", "CLOSURE_GATE_MUST_BE_G6", str(gate))
    _require(isinstance(closure_reason, str) and closure_reason.strip(), "CLOSURE_REASON_INVALID")
    digest = _sha256_digest("closure", run_id, gate, closure_reason)
    return ClosureReceipt(run_id=run_id, gate=gate, closure_reason=closure_reason, receipt_digest=digest)


def create_handoff_receipt(
    *,
    run_id: str,
    target_validation: dict[str, Any] | None,
    child_acceptance: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> HandoffReceipt:
    """Create a G6 HandoffReceipt (C7): target validation is mandatory."""
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID")
    _require(isinstance(target_validation, dict) and bool(target_validation), "TARGET_VALIDATION_REQUIRED")
    children = tuple(copy.deepcopy(c) for c in (child_acceptance or []))
    digest = _sha256_digest("handoff", run_id, target_validation, children)
    return HandoffReceipt(
        run_id=run_id, target_validation=copy.deepcopy(target_validation),
        child_acceptance=children, receipt_digest=digest,
    )


@dataclass(frozen=True)
class RunLedger:
    """Serializable durable ledger facade (advisory: receipts persisted)."""

    run_id: str
    entries: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "run-ledger",
            "run_id": self.run_id,
            "entries": [copy.deepcopy(e) for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunLedger":
        return cls(
            run_id=str(data.get("run_id", "")),
            entries=tuple(data.get("entries", [])),
        )


def append_receipt_to_ledger(
    ledger: RunLedger,
    receipt: Mapping[str, Any],
) -> RunLedger:
    """Append a receipt entry durably; returns a NEW ledger (immutable append)."""
    _require(isinstance(ledger, RunLedger), "LEDGER_INVALID")
    _require(isinstance(receipt, Mapping) and bool(receipt), "RECEIPT_INVALID")
    return RunLedger(run_id=ledger.run_id, entries=tuple(ledger.entries) + (dict(copy.deepcopy(receipt)),))


__all__ = [
    "ClosureReceipt",
    "DossierError",
    "HandoffReceipt",
    "RunDossier",
    "RunLedger",
    "append_receipt_to_ledger",
    "create_closure_receipt",
    "create_handoff_receipt",
    "create_run_dossier",
    "validate_dossier",
]
