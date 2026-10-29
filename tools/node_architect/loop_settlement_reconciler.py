#!/usr/bin/env python3
"""SCRUM-842 exactly-once native LoopManager settlement reconciler.

The graph (frozen SCRUM-841) emits a data-only ``native_loop_settlement_request``
with a stable idempotency key (``{operation_id}:M7:settlement``). The Hermes
host owns the actual native LoopManager settlement call; this reconciler is the
host-side at-most-once invocation guard. A durable pre-effect intent plus a
serialized ledger prevents blind retries; ambiguous outcomes require independent
native readback. This alone is not a transaction with the scheduler and does not
prove end-to-end exactly-once semantics.

Hermes core is out of scope: the native settlement function is injected by the
caller (the harness passes the live LoopManager settlement adapter). No Hermes
core module is imported or modified.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping

SETTLEMENT_LEDGER_SCHEMA_VERSION = "1.0"
SETTLEMENT_LEDGER_ARTIFACT_TYPE = "runtime-settlement-ledger"


class SettlementReconcilerError(ValueError):
    """A settlement request is missing required identity or failed closed."""


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _empty_ledger() -> dict[str, Any]:
    return {
        "schema_version": SETTLEMENT_LEDGER_SCHEMA_VERSION,
        "artifact_type": SETTLEMENT_LEDGER_ARTIFACT_TYPE,
        "settlements": {},
    }


def _load_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_ledger()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SettlementReconcilerError("SETTLEMENT_LEDGER_CORRUPT") from exc
    if not isinstance(payload, dict):
        raise SettlementReconcilerError("SETTLEMENT_LEDGER_CORRUPT")
    payload.setdefault("schema_version", SETTLEMENT_LEDGER_SCHEMA_VERSION)
    payload.setdefault("artifact_type", SETTLEMENT_LEDGER_ARTIFACT_TYPE)
    payload.setdefault("settlements", {})
    if payload.get("artifact_type") != SETTLEMENT_LEDGER_ARTIFACT_TYPE or not isinstance(payload["settlements"], dict):
        raise SettlementReconcilerError("SETTLEMENT_LEDGER_CORRUPT")
    return payload


def _write_ledger(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, str(path))
        directory_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _require_idempotency_key(settlement_request: Mapping[str, Any]) -> str:
    key = settlement_request.get("idempotency_key")
    if not isinstance(key, str) or not key:
        raise SettlementReconcilerError("SETTLEMENT_IDEMPOTENCY_KEY_MISSING")
    return key


def _is_verified(native_result: Any) -> bool:
    return (
        isinstance(native_result, Mapping)
        and native_result.get("status") == "VERIFIED"
        and native_result.get("settled") is True
    )


class LoopSettlementReconciler:
    """Durable exactly-once guard for native LoopManager settlement invocations.

    The ledger is a single JSON file (atomic replace). One entry per idempotency
    key; a settled key is never re-invoked, even after a fresh reconciler boot
    over the same ledger file.
    """

    def __init__(self, ledger_path: Path | str) -> None:
        self.ledger_path = Path(ledger_path)

    def is_settled(self, settlement_request: Mapping[str, Any]) -> bool:
        key = _require_idempotency_key(settlement_request)
        ledger = _load_ledger(self.ledger_path)
        entry = ledger["settlements"].get(key)
        return isinstance(entry, Mapping) and entry.get("settled") is True

    def receipt_for(self, settlement_request: Mapping[str, Any]) -> dict[str, Any] | None:
        key = _require_idempotency_key(settlement_request)
        entry = _load_ledger(self.ledger_path)["settlements"].get(key)
        if not isinstance(entry, Mapping):
            return None
        return {"idempotency_key": key, **{k: v for k, v in entry.items() if k != "idempotency_key"}}

    def settle_exactly_once(
        self,
        settlement_request: Mapping[str, Any],
        native_settlement: Callable[[Mapping[str, Any]], Any],
    ) -> dict[str, Any]:
        """Serialize cross-process claims; ambiguous intent requires readback."""
        import fcntl
        _require_idempotency_key(settlement_request)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger_path.with_suffix(self.ledger_path.suffix + ".lock").open("a+") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise SettlementReconcilerError("SETTLEMENT_BUSY") from exc
            try:
                return self._settle_locked(settlement_request, native_settlement)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _settle_locked(
        self,
        settlement_request: Mapping[str, Any],
        native_settlement: Callable[[Mapping[str, Any]], Any],
    ) -> dict[str, Any]:
        """Invoke the native LoopManager settlement at most once per key.

        Returns ``{"outcome": "SETTLED", "invoked": True, "receipt": ...}`` on
        first settlement and ``{"outcome": "ALREADY_SETTLED", "invoked": False,
        "receipt": ...}`` on replay. An unverified native result raises and is
        never recorded, so a legitimate retry remains possible (nothing was
        settled).
        """
        key = _require_idempotency_key(settlement_request)
        if not callable(native_settlement):
            raise SettlementReconcilerError("SETTLEMENT_NATIVE_INVOKER_MISSING")

        ledger = _load_ledger(self.ledger_path)
        existing = ledger["settlements"].get(key)
        if isinstance(existing, Mapping) and existing.get("settled") is True:
            return {
                "outcome": "ALREADY_SETTLED",
                "invoked": False,
                "settled": True,
                "idempotency_key": key,
                "receipt": dict(existing),
            }

        if isinstance(existing, Mapping) and existing.get("settled") is not True:
            raise SettlementReconcilerError("SETTLEMENT_UNKNOWN_OUTCOME_REQUIRES_READBACK")
        # Persist intent before the callback. A crash/exception after this point
        # is ambiguous, never permission to repeat the native effect.
        ledger["settlements"][key] = {
            "settled": False,
            "state": "INTENT_RECORDED",
            "request_digest": _digest(dict(settlement_request)),
        }
        _write_ledger(self.ledger_path, ledger)
        native_result = native_settlement(dict(settlement_request))
        if not _is_verified(native_result):
            raise SettlementReconcilerError("SETTLEMENT_NATIVE_RESULT_UNVERIFIED")

        now = native_result.get("settled_at") or _now_iso()
        receipt = {
            "idempotency_key": key,
            "settled": True,
            "settled_at": now,
            "native_receipt": _canonical_json(native_result),
            "receipt_digest": _digest({"key": key, "native": native_result}),
        }
        ledger["settlements"][key] = receipt
        _write_ledger(self.ledger_path, ledger)
        return {
            "outcome": "SETTLED",
            "invoked": True,
            "settled": True,
            "idempotency_key": key,
            "receipt": dict(receipt),
        }


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = ["LoopSettlementReconciler", "SettlementReconcilerError"]