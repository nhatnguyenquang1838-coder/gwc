"""Audited human-takeover packet builder for ambiguous runtime state."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable, Mapping


class TakeoverDecision(StrEnum):
    REOBSERVE_EXACT_STATE = "reobserve_exact_state"
    ACCEPT_SINGLE_OBSERVED_EFFECT = "accept_single_observed_effect"
    RETRY_CONFIRMED_NOT_APPLIED = "retry_confirmed_not_applied"
    RESUME_WITH_NEW_FENCE = "resume_with_new_fence"
    ABORT = "abort"


@dataclass(frozen=True)
class HumanTakeoverPacket:
    packet_version: str
    task_id: str
    run_id: str
    repository: str
    base_sha: str
    scope_hash: str
    graph_revision: str
    node_id: str
    scenario_id: str
    boundary: str
    checkpoint_revision: int
    fencing_token: int
    lease_owner: str | None
    idempotency_key: str | None
    pending_action: str
    attempts: tuple[Mapping[str, Any], ...]
    missing_facts: tuple[str, ...]
    evidence: tuple[str, ...]
    allowed_decisions: tuple[TakeoverDecision, ...]
    prohibited_actions: tuple[str, ...]
    generated_at_utc: str

    def validate(self) -> None:
        required = {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "repository": self.repository,
            "base_sha": self.base_sha,
            "scope_hash": self.scope_hash,
            "graph_revision": self.graph_revision,
            "node_id": self.node_id,
            "scenario_id": self.scenario_id,
            "boundary": self.boundary,
            "pending_action": self.pending_action,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError("missing takeover fields: " + ", ".join(missing))
        if len(self.base_sha) != 40:
            raise ValueError("base_sha must be exact 40-character SHA")
        if not self.scope_hash.startswith("sha256:") or len(self.scope_hash) != 71:
            raise ValueError("scope_hash must use sha256:<64 hex>")
        if self.checkpoint_revision < 0 or self.fencing_token < 0:
            raise ValueError("checkpoint revision and fencing token must be non-negative")
        if not self.missing_facts:
            raise ValueError("ambiguous state must identify missing facts")
        if not self.evidence:
            raise ValueError("takeover packet requires evidence")
        if not self.allowed_decisions:
            raise ValueError("takeover packet requires bounded decisions")
        if "blind_repeat_dispatch" not in self.prohibited_actions:
            raise ValueError("blind repeat dispatch must be prohibited")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "packet_version": self.packet_version,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "repository": self.repository,
            "base_sha": self.base_sha,
            "scope_hash": self.scope_hash,
            "graph_revision": self.graph_revision,
            "node_id": self.node_id,
            "scenario_id": self.scenario_id,
            "boundary": self.boundary,
            "checkpoint_revision": self.checkpoint_revision,
            "fencing_token": self.fencing_token,
            "lease_owner": self.lease_owner,
            "idempotency_key": self.idempotency_key,
            "pending_action": self.pending_action,
            "attempts": [dict(item) for item in self.attempts],
            "missing_facts": list(self.missing_facts),
            "evidence": list(self.evidence),
            "allowed_decisions": [item.value for item in self.allowed_decisions],
            "prohibited_actions": list(self.prohibited_actions),
            "generated_at_utc": self.generated_at_utc,
        }


def build_human_takeover_packet(
    *,
    task_id: str,
    run_id: str,
    repository: str,
    base_sha: str,
    scope_hash: str,
    graph_revision: str,
    node_id: str,
    scenario_id: str,
    boundary: str,
    checkpoint_revision: int,
    fencing_token: int,
    lease_owner: str | None,
    idempotency_key: str | None,
    pending_action: str,
    attempts: Iterable[Mapping[str, Any]],
    missing_facts: Iterable[str],
    evidence: Iterable[str],
    allowed_decisions: Iterable[TakeoverDecision | str],
) -> HumanTakeoverPacket:
    decisions = tuple(
        item if isinstance(item, TakeoverDecision) else TakeoverDecision(item)
        for item in allowed_decisions
    )
    packet = HumanTakeoverPacket(
        "human-takeover-packet/v1",
        task_id,
        run_id,
        repository,
        base_sha,
        scope_hash,
        graph_revision,
        node_id,
        scenario_id,
        boundary,
        checkpoint_revision,
        fencing_token,
        lease_owner,
        idempotency_key,
        pending_action,
        tuple(dict(item) for item in attempts),
        tuple(str(item) for item in missing_facts),
        tuple(str(item) for item in evidence),
        decisions,
        (
            "blind_repeat_dispatch",
            "overwrite_active_lease",
            "skip_live_readback",
            "change_scope_binding",
            "emit_false_pass",
        ),
        datetime.now(timezone.utc).isoformat(),
    )
    packet.validate()
    return packet
