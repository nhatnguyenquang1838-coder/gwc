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
from dataclasses import asdict, dataclass, field
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

    @property
    def content_digest(self) -> str:
        """Deterministic digest over the identity-bearing fields of the pack.

        Used for idempotency/replay: same key + same digest => prior result;
        same key + different digest => replay conflict.
        """
        canonical = "|".join([
            self.run_id,
            self.task_id,
            self.repository,
            self.preprod_base_sha,
            self.working_branch,
            self.scope_hash,
            self.graph_revision,
            self.policy_revision,
            ",".join(sorted(self.allowed_paths)),
            ",".join(sorted(self.prohibited_paths)),
            ",".join(sorted(self.authorized_actions)),
            ",".join(sorted(self.validation_commands)),
            self.idempotency_key,
        ]).encode("utf-8")
        return "sha256:" + hashlib.sha256(canonical).hexdigest()

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
) -> InstructionPack:
    """Compose a typed InstructionPack from a validated request + planning context.

    The function is pure: it does not touch the filesystem, git, or any provider.
    """
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
    )
