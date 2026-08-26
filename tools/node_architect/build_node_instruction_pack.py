#!/usr/bin/env python3
"""Build a typed instruction pack for the ai-task-execution node.

Provider-neutral: composes a deterministic, serializable pack from Agent boot,
task/repository/gate identity, semantic node identity, authority scope,
validation plan, and the exact repository instruction/skill bundle. Any
meaning-bearing drift changes the content digest.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from .agent_instruction_bundle import validate_agent_instruction_bundle


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
    head_sha: str = ""
    gate: str = ""
    requested_action: str = ""
    g0_g1_decision_ref: str = ""
    task_summary: str = ""
    objective: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    gate_node_route: tuple[str, ...] = ()
    plan_refs: tuple[str, ...] = ()
    node_id: str = ""
    node_version: str = ""
    implementation_ref: str = ""
    profile_revision: str = ""
    node_registry_revision: str = ""
    provider_contract_revision: str = ""
    agent_boot_ref: str = ""
    agent_instruction_digest: str = ""
    semantic_input_digest: str = ""
    instruction_bundle_digest: str = ""
    instruction_refs: tuple[str, ...] = ()
    instruction_digests: tuple[str, ...] = ()
    role_overlay_refs: tuple[str, ...] = ()
    role_overlay_digests: tuple[str, ...] = ()
    skill_refs: tuple[str, ...] = ()
    skill_digests: tuple[str, ...] = ()
    node_instruction_ref: str = ""
    node_instruction_digest: str = ""
    # (kind, repo ref, sha256 digest, actual UTF-8 content)
    instruction_bundle: tuple[tuple[str, str, str, str], ...] = ()

    @property
    def content_digest(self) -> str:
        """Digest every meaning-bearing field of the provider instruction pack."""
        canonical = {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "repository": self.repository,
            "preprod_base_sha": self.preprod_base_sha,
            "head_sha": self.head_sha,
            "working_branch": self.working_branch,
            "scope_hash": self.scope_hash,
            "gate": self.gate,
            "requested_action": self.requested_action,
            "graph_revision": self.graph_revision,
            "policy_revision": self.policy_revision,
            "profile_revision": self.profile_revision,
            "node_registry_revision": self.node_registry_revision,
            "node_id": self.node_id,
            "node_version": self.node_version,
            "implementation_ref": self.implementation_ref,
            "provider_contract_revision": self.provider_contract_revision,
            "agent_boot_ref": self.agent_boot_ref,
            "agent_instruction_digest": self.agent_instruction_digest,
            "instruction_bundle_digest": self.instruction_bundle_digest,
            "instruction_refs": list(self.instruction_refs),
            "instruction_digests": list(self.instruction_digests),
            "role_overlay_refs": list(self.role_overlay_refs),
            "role_overlay_digests": list(self.role_overlay_digests),
            "skill_refs": list(self.skill_refs),
            "skill_digests": list(self.skill_digests),
            "node_instruction_ref": self.node_instruction_ref,
            "node_instruction_digest": self.node_instruction_digest,
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


def _bundle_fields(instruction_bundle: Mapping[str, Any] | None) -> dict[str, Any]:
    if instruction_bundle is None:
        return {
            "instruction_bundle_digest": "",
            "instruction_refs": (),
            "instruction_digests": (),
            "role_overlay_refs": (),
            "role_overlay_digests": (),
            "skill_refs": (),
            "skill_digests": (),
            "node_instruction_ref": "",
            "node_instruction_digest": "",
            "instruction_bundle": (),
        }
    bundle = validate_agent_instruction_bundle(instruction_bundle)
    artifacts = tuple(
        (str(item["kind"]), str(item["ref"]), str(item["digest"]), str(item["content"]))
        for item in bundle["artifacts"]
    )
    return {
        "instruction_bundle_digest": str(bundle["bundle_digest"]),
        "instruction_refs": tuple(map(str, bundle["instruction_refs"])),
        "instruction_digests": tuple(map(str, bundle["instruction_digests"])),
        "role_overlay_refs": tuple(map(str, bundle["role_overlay_refs"])),
        "role_overlay_digests": tuple(map(str, bundle["role_overlay_digests"])),
        "skill_refs": tuple(map(str, bundle["skill_refs"])),
        "skill_digests": tuple(map(str, bundle["skill_digests"])),
        "node_instruction_ref": str(bundle["node_instruction_ref"]),
        "node_instruction_digest": str(bundle["node_instruction_digest"]),
        "instruction_bundle": artifacts,
    }


def build_node_instruction_pack(
    request: Mapping[str, Any],
    *,
    head_sha: str = "",
    gate: str = "",
    requested_action: str = "",
    g0_g1_decision_ref: str = "",
    task_summary: str = "",
    objective: str = "",
    acceptance_criteria: Sequence[str] = (),
    gate_node_route: Sequence[str] = (),
    plan_refs: Sequence[str] = (),
    node_id: str = "",
    node_version: str = "",
    implementation_ref: str = "",
    profile_revision: str = "",
    node_registry_revision: str = "",
    provider_contract_revision: str = "",
    agent_boot_ref: str = "",
    agent_instruction_digest: str = "",
    semantic_input_digest: str = "",
    instruction_bundle: Mapping[str, Any] | None = None,
) -> InstructionPack:
    """Compose a typed InstructionPack from a validated request + runtime context."""
    bundle_fields = _bundle_fields(instruction_bundle)
    # A materialized bundle is the authoritative repository instruction identity.
    if bundle_fields["instruction_bundle_digest"]:
        agent_instruction_digest = str(bundle_fields["instruction_bundle_digest"])
        refs = bundle_fields["instruction_refs"]
        if refs:
            agent_boot_ref = str(refs[0])

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
        head_sha=str(head_sha),
        gate=str(gate),
        requested_action=str(requested_action),
        g0_g1_decision_ref=str(g0_g1_decision_ref),
        task_summary=str(task_summary),
        objective=str(objective),
        acceptance_criteria=tuple(map(str, acceptance_criteria)),
        gate_node_route=tuple(map(str, gate_node_route)),
        plan_refs=tuple(map(str, plan_refs)),
        node_id=str(node_id),
        node_version=str(node_version),
        implementation_ref=str(implementation_ref),
        profile_revision=str(profile_revision),
        node_registry_revision=str(node_registry_revision),
        provider_contract_revision=str(provider_contract_revision),
        agent_boot_ref=str(agent_boot_ref),
        agent_instruction_digest=str(agent_instruction_digest),
        semantic_input_digest=str(semantic_input_digest),
        **bundle_fields,
    )
