#!/usr/bin/env python3
"""Build a typed instruction pack for the ai-task-execution node.

Provider-neutral: composes a deterministic, serializable pack from the task,
repository context, G0/G1 decision, file scope, gate/node route and validation
plan. The pack is what gets handed to whatever AI implementation provider is
plugged in (initially a custom/self-hosted runner; Hermes, Codex or another
agent implement the same Provider protocol without graph changes).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class InstructionPack:
    run_id: str
    task_id: str
    repository: str
    preprod_base_sha: str
    working_branch: str
    scope_hash: str
    graph_revision: str
    policy_revision: str
    allowed_paths: tuple[str, ...]
    prohibited_paths: tuple[str, ...]
    authorized_actions: tuple[str, ...]
    validation_commands: tuple[str, ...]
    idempotency_key: str
    g0_g1_decision_ref: str = ""
    task_summary: str = ""
    objective: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    gate_node_route: tuple[str, ...] = ()
    plan_refs: tuple[str, ...] = ()
    semantic_input_digest: str = ""

    @property
    def content_digest(self) -> str:
        """Digest every meaning-bearing field of the provider instruction pack.

        Idempotency is safe only when a semantic change changes this digest.
        Lists whose order is not semantic are normalized; route, acceptance
        criteria and plan refs preserve declared order because ordering can carry
        execution meaning.
        """
        canonical = {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "repository": self.repository,
            "preprod_base_sha": self.preprod_base_sha,
            "working_branch": self.working_branch,
            "scope_hash": self.scope_hash,
            "graph_revision": self.graph_revision,
            "policy_revision": self.policy_revision,
            "allowed_paths": sorted(self.allowed_paths),
            "prohibited_paths": sorted(self.prohibited_paths),
            "authorized_actions": sorted(self.authorized_actions),
            "validation_commands": list(self.validation_commands),
            "idempotency_key": self.idempotency_key,
            "g0_g1_decision_ref": self.g0_g1_decision_ref,
            "task_summary": self.task_summary,
            "objective": self.objective,
            "acceptance_criteria": list(self.acceptance_criteria),
            "gate_node_route": list(self.gate_node_route),
            "plan_refs": list(self.plan_refs),
            "semantic_input_digest": self.semantic_input_digest,
        }
        raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_node_instruction_pack(
    request: Mapping[str, Any],
    *,
    g0_g1_decision_ref: str = "",
    task_summary: str = "",
    objective: str = "",
    acceptance_criteria: Sequence[str] = (),
    gate_node_route: Sequence[str] = (),
    plan_refs: Sequence[str] = (),
    semantic_input_digest: str = "",
) -> InstructionPack:
    """Compose a typed InstructionPack from a validated request + planning context."""
    return InstructionPack(
        run_id=str(request["run_id"]),
        task_id=str(request["task_id"]),
        repository=str(request["repository"]),
        preprod_base_sha=str(request["preprod_base_sha"]),
        working_branch=str(request["working_branch"]),
        scope_hash=str(request["scope_hash"]),
        graph_revision=str(request["graph_revision"]),
        policy_revision=str(request["policy_revision"]),
        allowed_paths=tuple(map(str, request.get("allowed_paths", ()))),
        prohibited_paths=tuple(map(str, request.get("prohibited_paths", ()))),
        authorized_actions=tuple(map(str, request.get("authorized_actions", ()))),
        validation_commands=tuple(map(str, request.get("validation_commands", ()))),
        idempotency_key=str(request["idempotency_key"]),
        g0_g1_decision_ref=str(g0_g1_decision_ref),
        task_summary=str(task_summary),
        objective=str(objective),
        acceptance_criteria=tuple(map(str, acceptance_criteria)),
        gate_node_route=tuple(map(str, gate_node_route)),
        plan_refs=tuple(map(str, plan_refs)),
        semantic_input_digest=str(semantic_input_digest),
    )
