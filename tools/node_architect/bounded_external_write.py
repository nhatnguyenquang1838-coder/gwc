"""Provider-neutral bounded external-write classifier for SCRUM-108."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence


class BoundedWriteState(StrEnum):
    READY_TO_DISPATCH = "ready_to_dispatch"
    FAILED_VALIDATION = "failed_validation"
    RETRYABLE_CONFIRMED_NOT_APPLIED = "retryable_confirmed_not_applied"
    PASS_RECONCILED = "pass_reconciled"
    PASS_SINGLE_EFFECT = "pass_single_effect"
    STALE_CHECKPOINT = "stale_checkpoint"
    AMBIGUOUS_HUMAN_REQUIRED = "ambiguous_human_required"


@dataclass(frozen=True)
class BoundedWriteIntent:
    task_id: str
    repository: str
    scope_hash: str
    idempotency_key: str
    operation: str
    payload_hash: str
    checkpoint_revision: int
    fencing_token: int
    persisted: bool
    lease_owner: str | None = None
    evidence: tuple[str, ...] = ()

    def validate(self) -> list[str]:
        issues = [name + " is required" for name in (
            "task_id", "repository", "scope_hash", "idempotency_key", "operation", "payload_hash"
        ) if not str(getattr(self, name)).strip()]
        if not self.scope_hash.startswith("sha256:") or len(self.scope_hash) != 71:
            issues.append("scope_hash must use sha256:<64 hex> format")
        if self.checkpoint_revision < 0:
            issues.append("checkpoint_revision must be non-negative")
        if self.fencing_token < 0:
            issues.append("fencing_token must be non-negative")
        if not self.persisted:
            issues.append("intent must be durably persisted before dispatch")
        return issues


@dataclass(frozen=True)
class AdapterDispatch:
    status: str
    dispatched: bool
    response_id: str | None = None
    error: str | None = None
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class BoundedWriteReadback:
    observed: bool
    effect_count: int | None
    idempotency_key: str | None
    scope_hash: str | None
    status: str | None = None
    external_reference: str | None = None
    evidence: tuple[str, ...] = ()

    def validate(self) -> list[str]:
        if self.effect_count is not None and self.effect_count < 0:
            return ["effect_count must be non-negative when supplied"]
        return []


@dataclass(frozen=True)
class BoundedWriteEvidence:
    state: BoundedWriteState
    task_id: str
    repository: str
    scope_hash: str
    idempotency_key: str
    checkpoint_revision: int
    fencing_token: int
    mutation_allowed: bool
    repeat_dispatch_allowed: bool
    human_required: bool
    reason: str
    effect_count: int | None = None
    external_reference: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "task_id": self.task_id,
            "repository": self.repository,
            "scope_hash": self.scope_hash,
            "idempotency_key": self.idempotency_key,
            "checkpoint_revision": self.checkpoint_revision,
            "fencing_token": self.fencing_token,
            "mutation_allowed": self.mutation_allowed,
            "repeat_dispatch_allowed": self.repeat_dispatch_allowed,
            "human_required": self.human_required,
            "reason": self.reason,
            "effect_count": self.effect_count,
            "external_reference": self.external_reference,
            "evidence_refs": list(self.evidence_refs),
        }


def classify_bounded_external_write(
    *,
    intent: BoundedWriteIntent,
    dispatch: AdapterDispatch | Mapping[str, Any] | None,
    readback: BoundedWriteReadback | Mapping[str, Any] | None,
    expected_scope_hash: str,
    active_checkpoint_revision: int,
    active_fencing_token: int,
) -> BoundedWriteEvidence:
    """Classify whether a persisted external-write intent may run, pass, retry, or stop."""
    dispatch_obj = _coerce_dispatch(dispatch)
    readback_obj = _coerce_readback(readback)
    evidence_refs = _collect_evidence(intent, dispatch_obj, readback_obj)
    issues = intent.validate()
    if expected_scope_hash != intent.scope_hash:
        issues.append("expected scope hash does not match persisted intent")
    if dispatch_obj.status not in {"not_called", "completed", "timeout", "error"}:
        issues.append("dispatch status must be not_called, completed, timeout, or error")
    if readback_obj is not None:
        issues.extend(readback_obj.validate())
    if issues:
        return _evidence(BoundedWriteState.FAILED_VALIDATION, intent, readback_obj, False, False, False, "; ".join(issues), evidence_refs)
    if intent.checkpoint_revision != active_checkpoint_revision or intent.fencing_token != active_fencing_token:
        return _evidence(BoundedWriteState.STALE_CHECKPOINT, intent, readback_obj, False, False, False, "checkpoint revision or fencing token is stale", evidence_refs)
    if readback_obj is not None and readback_obj.observed and readback_obj.effect_count == 0:
        if dispatch_obj.status == "timeout" or dispatch_obj.dispatched:
            return _evidence(BoundedWriteState.RETRYABLE_CONFIRMED_NOT_APPLIED, intent, readback_obj, True, True, False, "live readback confirms no matching effect was applied", evidence_refs)
        return _evidence(BoundedWriteState.READY_TO_DISPATCH, intent, readback_obj, True, False, False, "intent persisted and no prior effect is present", evidence_refs)
    if readback_obj is not None and readback_obj.observed and readback_obj.effect_count == 1:
        if readback_obj.idempotency_key != intent.idempotency_key:
            return _ambiguous(intent, readback_obj, evidence_refs, "readback idempotency key does not match intent")
        if readback_obj.scope_hash != intent.scope_hash:
            return _ambiguous(intent, readback_obj, evidence_refs, "readback scope hash does not match intent")
        state = BoundedWriteState.PASS_RECONCILED if dispatch_obj.status == "timeout" else BoundedWriteState.PASS_SINGLE_EFFECT
        reason = "timeout reconciled by one matching live effect" if state == BoundedWriteState.PASS_RECONCILED else "one matching live effect observed under idempotency key and scope"
        return _evidence(state, intent, readback_obj, False, False, False, reason, evidence_refs)
    if readback_obj is not None and readback_obj.observed and (readback_obj.effect_count or 0) > 1:
        return _ambiguous(intent, readback_obj, evidence_refs, "multiple live effects observed for bounded write")
    if dispatch_obj.status == "not_called" and not dispatch_obj.dispatched:
        return _evidence(BoundedWriteState.READY_TO_DISPATCH, intent, readback_obj, True, False, False, "persisted intent is ready for first dispatch", evidence_refs)
    return _ambiguous(intent, readback_obj, evidence_refs, "post-dispatch live state is not exact enough to retry or pass")


def _coerce_dispatch(value: AdapterDispatch | Mapping[str, Any] | None) -> AdapterDispatch:
    if value is None:
        return AdapterDispatch("not_called", False)
    if isinstance(value, AdapterDispatch):
        return value
    return AdapterDispatch(str(value.get("status", "not_called")), bool(value.get("dispatched", False)), value.get("response_id"), value.get("error"), tuple(str(x) for x in value.get("evidence", ())))


def _coerce_readback(value: BoundedWriteReadback | Mapping[str, Any] | None) -> BoundedWriteReadback | None:
    if value is None or isinstance(value, BoundedWriteReadback):
        return value
    count = value.get("effect_count")
    return BoundedWriteReadback(bool(value.get("observed", False)), None if count is None else int(count), value.get("idempotency_key"), value.get("scope_hash"), value.get("status"), value.get("external_reference"), tuple(str(x) for x in value.get("evidence", ())))


def _collect_evidence(intent: BoundedWriteIntent, dispatch: AdapterDispatch, readback: BoundedWriteReadback | None) -> tuple[str, ...]:
    refs = list(intent.evidence) + list(dispatch.evidence)
    if readback is not None:
        refs.extend(readback.evidence)
    return tuple(refs)


def _ambiguous(intent: BoundedWriteIntent, readback: BoundedWriteReadback | None, evidence_refs: Sequence[str], reason: str) -> BoundedWriteEvidence:
    return _evidence(BoundedWriteState.AMBIGUOUS_HUMAN_REQUIRED, intent, readback, False, False, True, reason, evidence_refs)


def _evidence(state: BoundedWriteState, intent: BoundedWriteIntent, readback: BoundedWriteReadback | None, mutation_allowed: bool, repeat_dispatch_allowed: bool, human_required: bool, reason: str, evidence_refs: Sequence[str]) -> BoundedWriteEvidence:
    return BoundedWriteEvidence(state, intent.task_id, intent.repository, intent.scope_hash, intent.idempotency_key, intent.checkpoint_revision, intent.fencing_token, mutation_allowed, repeat_dispatch_allowed, human_required, reason, None if readback is None else readback.effect_count, None if readback is None else readback.external_reference, tuple(evidence_refs))


__all__ = [
    "AdapterDispatch",
    "BoundedWriteEvidence",
    "BoundedWriteIntent",
    "BoundedWriteReadback",
    "BoundedWriteState",
    "classify_bounded_external_write",
]
