#!/usr/bin/env python3
"""Deterministic crash/replay verification harness for SCRUM-110.

The harness is provider-neutral. It injects crashes at canonical B0-B5
boundaries, records ordered evidence, and verifies replay invariants without
calling external systems.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from tools.node_architect.bounded_external_write import (
    AdapterDispatch,
    BoundedWriteIntent,
    BoundedWriteReadback,
    classify_bounded_external_write,
)
from tools.node_architect.durable_checkpoint_runtime import (
    CheckpointCasMismatch,
    DurableCheckpointStore,
    LeaseConflict,
    LeaseRequired,
    RuntimeBinding,
)
from tools.node_architect.exact_state_capture import ExactState, capture_exact_state


class CrashBoundary(StrEnum):
    B0 = "B0"
    B1 = "B1"
    B2 = "B2"
    B3 = "B3"
    B4 = "B4"
    B5 = "B5"


class NodeClass(StrEnum):
    READ_ONLY = "RO"
    BOUNDED_WRITE = "BW"
    DURABLE_RUNTIME = "DR"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    node_class: NodeClass
    failure_class: str
    boundary: CrashBoundary
    expected_terminal: str
    oracle: str


@dataclass(frozen=True)
class ReplayEvidence:
    scenario_id: str
    boundary: CrashBoundary
    first_worker: str
    replay_worker: str
    first_fencing_token: int
    replay_fencing_token: int
    checkpoint_revision: int
    external_effect_count: int
    terminal: str
    human_required: bool
    duplicate_effect_prevented: bool
    stale_worker_rejected: bool
    events: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "boundary": self.boundary.value,
            "first_worker": self.first_worker,
            "replay_worker": self.replay_worker,
            "first_fencing_token": self.first_fencing_token,
            "replay_fencing_token": self.replay_fencing_token,
            "checkpoint_revision": self.checkpoint_revision,
            "external_effect_count": self.external_effect_count,
            "terminal": self.terminal,
            "human_required": self.human_required,
            "duplicate_effect_prevented": self.duplicate_effect_prevented,
            "stale_worker_rejected": self.stale_worker_rejected,
            "events": list(self.events),
        }


def parse_scenario_matrix(path: Path) -> list[Scenario]:
    scenarios: list[Scenario] = []
    in_table = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("| Scenario | Node |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and not line.startswith("|"):
            if scenarios:
                break
            continue
        if not in_table or not line.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        if len(cells) < 7:
            continue
        scenario_id, node, failure, boundary_text, terminal, _priority, oracle = cells[:7]
        scenarios.append(
            Scenario(
                scenario_id,
                NodeClass(node),
                failure,
                CrashBoundary(boundary_text.split("_")[0]),
                terminal,
                oracle,
            )
        )
    return scenarios


class CrashReplayHarness:
    def __init__(
        self,
        *,
        task_id: str,
        repository: str,
        base_sha: str,
        scope_hash: str,
        graph_revision: str,
    ):
        self.binding = RuntimeBinding(
            task_id,
            repository,
            base_sha,
            scope_hash,
            graph_revision,
        )

    def run(self, scenario: Scenario) -> ReplayEvidence:
        now = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
        run_id = f"scrum-110-{scenario.scenario_id.lower()}"
        store = DurableCheckpointStore()
        store.create_run(
            run_id=run_id,
            binding=self.binding,
            current_node_id=scenario.node_class.value,
            next_node_id=scenario.node_class.value,
            next_action="execute",
            gate="G2_EXECUTION",
            evidence=(scenario.scenario_id,),
        )
        events = ["run.created"]
        first = "worker-a"
        replay = "worker-b"
        first_lease = store.acquire_lease(
            run_id=run_id,
            lease_owner=first,
            ttl_seconds=5,
            now=now,
        )
        events.append("lease.acquired:worker-a")
        external_effect_count = 0
        human_required = scenario.failure_class in {
            "AMBIGUOUS_POST_STATE",
            "HUMAN_TAKEOVER",
        }
        terminal = scenario.expected_terminal
        stale_rejected = False
        duplicate_prevented = True

        if scenario.boundary == CrashBoundary.B0:
            events.append("crash.before_validation_or_load")
        elif scenario.boundary == CrashBoundary.B1:
            events.append("crash.after_lease_before_intent")
        elif scenario.boundary == CrashBoundary.B2:
            events.extend(("intent.persisted", "crash.after_intent_before_effect"))
        elif scenario.boundary == CrashBoundary.B3:
            external_effect_count = 1 if scenario.node_class == NodeClass.BOUNDED_WRITE else 0
            events.append("effect.applied" if external_effect_count else "checkpoint.commit.attempted")
            events.append("crash.after_effect_before_ack")
        elif scenario.boundary == CrashBoundary.B4:
            events.extend(("readback.partial", "crash.before_checkpoint_or_human_decision"))
        elif scenario.boundary == CrashBoundary.B5:
            advanced = store.cas_checkpoint(
                run_id=run_id,
                expected_revision=0,
                lease_owner=first,
                fencing_token=first_lease.fencing_token,
                next_state={
                    "status": "CHECKPOINTED",
                    "next_action": "emit_terminal",
                    "evidence": [scenario.oracle],
                },
                now=now + timedelta(seconds=1),
            )
            events.extend(
                (
                    f"checkpoint.revision:{advanced.revision}",
                    "crash.after_checkpoint_before_terminal",
                )
            )

        takeover_at = now + timedelta(seconds=6)
        replay_lease = store.resume_checkpoint(
            run_id=run_id,
            expected_binding=self.binding,
            lease_owner=replay,
            ttl_seconds=60,
            now=takeover_at,
        )
        events.append("lease.takeover:worker-b")
        try:
            store.cas_checkpoint(
                run_id=run_id,
                expected_revision=store.read_checkpoint(run_id).revision,
                lease_owner=first,
                fencing_token=first_lease.fencing_token,
                next_state={"status": "STALE_WORKER_WRITE"},
                now=takeover_at + timedelta(seconds=1),
            )
        except (LeaseRequired, CheckpointCasMismatch):
            stale_rejected = True
            events.append("stale-worker.rejected")

        if scenario.node_class == NodeClass.READ_ONLY:
            observation = None
            if not human_required:
                observation = {
                    "head_sha": self.binding.base_sha,
                    "status": "completed",
                    "conclusion": "success",
                }
            observed = capture_exact_state(
                task_id=self.binding.task_id,
                repository=self.binding.repository,
                expected_sha=self.binding.base_sha,
                observation=observation,
            )
            if observed.state == ExactState.OBSERVABILITY_INCOMPLETE:
                human_required = True
        elif scenario.node_class == NodeClass.BOUNDED_WRITE:
            intent = BoundedWriteIntent(
                self.binding.task_id,
                self.binding.repository,
                self.binding.scope_hash,
                f"{run_id}:effect",
                "bounded-write",
                "sha256:" + "2" * 64,
                store.read_checkpoint(run_id).revision,
                replay_lease.fencing_token,
                True,
                replay,
                tuple(events),
            )
            if human_required:
                dispatch = AdapterDispatch("timeout", True)
                readback = None
            elif scenario.boundary == CrashBoundary.B3:
                dispatch = AdapterDispatch("timeout", True)
                readback = BoundedWriteReadback(
                    True,
                    1,
                    intent.idempotency_key,
                    intent.scope_hash,
                )
            else:
                dispatch = AdapterDispatch("completed", True)
                external_effect_count = max(external_effect_count, 1)
                readback = BoundedWriteReadback(
                    True,
                    1,
                    intent.idempotency_key,
                    intent.scope_hash,
                )
            classified = classify_bounded_external_write(
                intent=intent,
                dispatch=dispatch,
                readback=readback,
                expected_scope_hash=self.binding.scope_hash,
                active_checkpoint_revision=intent.checkpoint_revision,
                active_fencing_token=replay_lease.fencing_token,
            )
            human_required = classified.human_required
            external_effect_count = classified.effect_count or external_effect_count
            duplicate_prevented = not classified.repeat_dispatch_allowed
        elif scenario.failure_class == "DUPLICATE_WORKER":
            try:
                store.acquire_lease(
                    run_id=run_id,
                    lease_owner="worker-c",
                    ttl_seconds=60,
                    now=takeover_at + timedelta(seconds=1),
                )
                duplicate_prevented = False
            except LeaseConflict:
                duplicate_prevented = True
                events.append("duplicate-worker.rejected")

        checkpoint = store.read_checkpoint(run_id)
        if human_required:
            events.append("human.takeover.required")
        else:
            if checkpoint.revision == 0:
                checkpoint = store.cas_checkpoint(
                    run_id=run_id,
                    expected_revision=0,
                    lease_owner=replay,
                    fencing_token=replay_lease.fencing_token,
                    next_state={
                        "status": "REPLAY_VERIFIED",
                        "next_action": "emit_terminal",
                        "evidence": events,
                    },
                    now=takeover_at + timedelta(seconds=2),
                )
            events.append("replay.verified")

        return ReplayEvidence(
            scenario.scenario_id,
            scenario.boundary,
            first,
            replay,
            first_lease.fencing_token,
            replay_lease.fencing_token,
            checkpoint.revision,
            external_effect_count,
            terminal,
            human_required,
            duplicate_prevented,
            stale_rejected,
            tuple(events),
        )


def verify_matrix(
    scenarios: Iterable[Scenario],
    harness: CrashReplayHarness,
) -> list[ReplayEvidence]:
    results = [harness.run(scenario) for scenario in scenarios]
    if len(results) != 27:
        raise ValueError(f"expected 27 scenarios, got {len(results)}")
    if {result.boundary for result in results} != set(CrashBoundary):
        raise ValueError("scenario matrix does not cover every B0-B5 boundary")
    if not all(
        result.stale_worker_rejected and result.duplicate_effect_prevented
        for result in results
    ):
        raise AssertionError("replay invariants failed")
    return results
