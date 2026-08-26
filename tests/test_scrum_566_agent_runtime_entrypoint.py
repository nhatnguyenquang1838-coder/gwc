from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module(name: str):
    spec = importlib.util.find_spec(name)
    assert spec is not None, f"{name} must exist"
    return importlib.import_module(name)


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _canonical_state(**overrides) -> dict:
    profile = _load("core/node-architect/gate-node-route-profile.json")
    graph = _load("core/node-architect/runtime-graph-registry.json")
    registry = _load("core/node-architect/node-registry.json")
    reg_rev = registry["revision"]
    reg_revision = reg_rev["revision_id"] if isinstance(reg_rev, dict) else str(reg_rev)
    graph_rev = graph["revision"]
    graph_revision = graph_rev["revision_id"] if isinstance(graph_rev, dict) else str(graph_rev)
    value = {
        "schema_version": "1.0",
        "task_id": "SCRUM-566",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "scope_hash": "sha256:" + "c" * 64,
        "profile_revision": profile["revision"],
        "graph_revision": graph_revision,
        "node_registry_revision": reg_revision,
        "policy_revision": "gwc-gate-applicability-policy-registry",
        "source_kind": "canonical_agent_gate_state",
        "workflow_profile_ref": profile["workflow_profile_ref"],
    }
    value.update(overrides)
    return value


def _route_context(action: str = "draft_pr_creation") -> dict:
    envelope = {
        "task_id": "SCRUM-566",
        "authority_gate": "G2_EXECUTION",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "base_sha": "a" * 40,
        "working_branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "scope_hash": "sha256:" + "c" * 64,
    }
    profile = _load("core/node-architect/gate-node-route-profile.json")
    return {
        "task_id": "SCRUM-566",
        "gate": "G2_EXECUTION",
        "requested_action": action,
        "workflow_mode": "normal",
        "repository": envelope["repository"],
        "base_sha": envelope["base_sha"],
        "working_branch": envelope["working_branch"],
        "scope_hash": envelope["scope_hash"],
        "expected_profile_revision": profile["revision"],
        "expected_graph_revision": profile["bound_graph_revision"],
        "available_connectors": ["GitHub.compare_commits"],
        "context": {
            "g0_context": {"status": "READY"},
            "g1_decision": {"status": "PASS"},
            "g2_envelope": envelope,
            "approval_receipt": {"status": "VALID"},
            "task_claim": {"agent": "ChatGPT"},
            "base_sha_readback": {"sha": envelope["base_sha"]},
            "write_result": {"status": "success"},
            "diff_readback": {"status": "PASS"},
            "draft_pr_result": {"status": "CREATED"},
        },
    }


def _bundle_inputs() -> dict:
    return {
        "instruction_refs": [
            "AGENTS.md",
            "agents/chatgpt-agent/agent-instructions.md",
            "agents/chatgpt-agent/gwc-governed-base.md",
        ],
        "role_overlay_refs": ["agents/autonomous-agent/agent-instructions.md"],
        "required_skill_names": ["task-controller", "executor"],
        "node_instruction_ref": "core/node-architect/node-instructions/repo_delivery/draft-pr-creation.node-instruction.yaml",
    }


def test_agent_runtime_entrypoint_module_and_public_api_exist():
    entry = _module("tools.node_architect.agent_runtime_entrypoint")
    for name in ("bootstrap_agent_runtime", "run_agent_node"):
        assert callable(getattr(entry, name)), name


def test_entrypoint_composes_full_semantic_agent_chain(tmp_path: Path):
    """RED contract: one production entrypoint composes bundle -> route -> binding ->
    live event -> lifecycle -> provider -> capability -> readback -> ledger -> NEXT."""
    entry = _module("tools.node_architect.agent_runtime_entrypoint")
    bundle = entry.resolve_agent_instruction_bundle(
        root=ROOT,
        instruction_refs=_bundle_inputs()["instruction_refs"],
        role_overlay_refs=_bundle_inputs()["role_overlay_refs"],
        required_skill_names=_bundle_inputs()["required_skill_names"],
        node_instruction_ref=_bundle_inputs()["node_instruction_ref"],
    )
    assert bundle["bundle_digest"].startswith("sha256:")
    assert len(bundle["artifacts"]) >= 6  # 3 instructions + 1 overlay + 2 skills + 1 node instruction
    artifacts = {item["ref"]: item for item in bundle["artifacts"]}
    for ref in (
        "AGENTS.md",
        "agents/chatgpt-agent/gwc-governed-base.md",
        "skills/task-controller/SKILL.md",
        "skills/executor/SKILL.md",
    ):
        assert ref in artifacts, ref
        assert artifacts[ref]["content"], ref

    route = entry.resolve_agent_route(
        root=ROOT,
        canonical_state=_canonical_state(),
        route_context=_route_context(),
    )
    assert route["outcome"] == "ROUTE_SELECTED"
    assert route["current_node"] == "repo_delivery.draft-pr-creation"

    result = entry.run_agent_node(
        root=ROOT,
        canonical_state=_canonical_state(),
        route_context=_route_context(),
        bundle=bundle,
        event_id="evt-entrypoint-1",
        run_id="run-entrypoint-1",
        gate="G2_EXECUTION",
        requested_action="draft_pr_creation",
        scenario="standard_pr_delivery",
        input_payload={
            "g2_envelope": {"task_id": "SCRUM-566", "authority_gate": "G2_EXECUTION", "repository": "nhatnguyenquang1838-coder/gwc", "base_sha": "a" * 40, "working_branch": "chatgpt/scrum-566-agent-runtime-corrective", "scope_hash": "sha256:" + "c" * 64},
            "approval_receipt": {"status": "VALID"},
            "approved_paths": ["tools/node_architect/scratch/x.py"],
            "working_branch": "chatgpt/scrum-566-agent-runtime-corrective",
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "scope_hash": "sha256:" + "c" * 64,
            "idempotency_key": "evt-entrypoint-1",
        },
        evidence_root=tmp_path,
        mode="shadow_readonly",
    )

    assert result["status"] in ("SEMANTIC_NODE_COMPLETE", "SEMANTIC_NODE_BLOCKED")
    assert result["node_id"] == "repo_delivery.draft-pr-creation"
    assert result["binding_digest"].startswith("sha256:")
    assert result["semantic_execution"] is True
    assert result["implementation_invoked"] is True
    assert result["canonical_readback_verified"] is True
    assert result["event_digest"].startswith("sha256:")
    assert isinstance(result["evidence_summary"], dict)
    # typed NEXT must be present and gate-authority non-escalating
    assert "next_route" in result
    assert result["next_route"].get("automatic_gate_advance") is False
    assert result["authority_granted"] is False
    assert result["executed_effects"] == []


def test_entrypoint_provider_pack_carries_host_instruction_bundle(tmp_path: Path):
    """The LLM provider must receive the HOST-resolved instruction bundle contents."""
    entry = _module("tools.node_architect.agent_runtime_entrypoint")
    captured = {}

    class RecordingProvider:
        name = "recording-provider"

        def run(self, pack):
            captured["pack"] = pack
            return {"changed_paths": [], "recorded_actions": [], "validation_passed": True}

    bundle = entry.resolve_agent_instruction_bundle(
        root=ROOT,
        instruction_refs=["AGENTS.md"],
        role_overlay_refs=[],
        required_skill_names=["executor"],
        node_instruction_ref="core/node-architect/node-instructions/repo_delivery/draft-pr-creation.node-instruction.yaml",
    )

    entry.run_agent_node(
        root=ROOT,
        canonical_state=_canonical_state(),
        route_context=_route_context(),
        bundle=bundle,
        event_id="evt-provider-1",
        run_id="run-provider-1",
        gate="G2_EXECUTION",
        requested_action="draft_pr_creation",
        scenario="standard_pr_delivery",
        input_payload={
            "g2_envelope": {"task_id": "SCRUM-566", "authority_gate": "G2_EXECUTION", "repository": "nhatnguyenquang1838-coder/gwc", "base_sha": "a" * 40, "working_branch": "chatgpt/scrum-566-agent-runtime-corrective", "scope_hash": "sha256:" + "c" * 64},
            "approval_receipt": {"status": "VALID"},
            "approved_paths": ["tools/node_architect/scratch/x.py"],
            "working_branch": "chatgpt/scrum-566-agent-runtime-corrective",
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "scope_hash": "sha256:" + "c" * 64,
            "idempotency_key": "evt-provider-1",
        },
        evidence_root=tmp_path,
        mode="shadow_readonly",
        provider=RecordingProvider(),
    )

    pack = captured["pack"]
    assert pack.instruction_bundle_digest == bundle["bundle_digest"]
    assert set(pack.skill_refs) == {"skills/executor/SKILL.md"}
    assert pack.skill_digests
    assert pack.node_instruction_ref == bundle["node_instruction_ref"]
    assert pack.node_instruction_digest == bundle["node_instruction_digest"]
    # immutable contents carried into the provider pack
    assert pack.instruction_bundle
    contents = {item[1]: item for item in pack.instruction_bundle}
    assert "AGENTS.md" in contents
    assert contents["AGENTS.md"][2].startswith("sha256:")


def test_entrypoint_node_input_cannot_override_host_bundle(tmp_path: Path):
    """A node/LLM-supplied instruction_bundle/skill_refs must not replace the host bundle."""
    entry = _module("tools.node_architect.agent_runtime_entrypoint")
    captured = {}

    class RecordingProvider:
        name = "recording-provider"

        def run(self, pack):
            captured["pack"] = pack
            return {"changed_paths": [], "recorded_actions": [], "validation_passed": True}

    host_bundle = entry.resolve_agent_instruction_bundle(
        root=ROOT,
        instruction_refs=["AGENTS.md"],
        role_overlay_refs=[],
        required_skill_names=["executor"],
        node_instruction_ref="core/node-architect/node-instructions/repo_delivery/draft-pr-creation.node-instruction.yaml",
    )

    entry.run_agent_node(
        root=ROOT,
        canonical_state=_canonical_state(),
        route_context=_route_context(),
        bundle=host_bundle,
        event_id="evt-override-1",
        run_id="run-override-1",
        gate="G2_EXECUTION",
        requested_action="draft_pr_creation",
        scenario="standard_pr_delivery",
        input_payload={
            "g2_envelope": {"task_id": "SCRUM-566", "authority_gate": "G2_EXECUTION", "repository": "nhatnguyenquang1838-coder/gwc", "base_sha": "a" * 40, "working_branch": "chatgpt/scrum-566-agent-runtime-corrective", "scope_hash": "sha256:" + "c" * 64},
            "approval_receipt": {"status": "VALID"},
            "approved_paths": ["tools/node_architect/scratch/x.py"],
            "working_branch": "chatgpt/scrum-566-agent-runtime-corrective",
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "scope_hash": "sha256:" + "c" * 64,
            "idempotency_key": "evt-override-1",
            "skill_refs": ["skills/attacker/SKILL.md"],
            "instruction_bundle": {"schema_version": "1.0", "artifact_type": "agent-instruction-bundle", "artifacts": [], "bundle_digest": "sha256:" + "0" * 64},
        },
        evidence_root=tmp_path,
        mode="shadow_readonly",
        provider=RecordingProvider(),
    )

    pack = captured["pack"]
    assert pack.instruction_bundle_digest == host_bundle["bundle_digest"]
    assert pack.skill_refs == ("skills/executor/SKILL.md",)
    assert "skills/attacker/SKILL.md" not in pack.skill_refs
    assert pack.content_digest != "sha256:" + "0" * 64


def test_entrypoint_missing_bundle_blocks_before_provider(tmp_path: Path):
    entry = _module("tools.node_architect.agent_runtime_entrypoint")
    called = {"provider": False}

    class RecordingProvider:
        name = "recording-provider"

        def run(self, pack):
            called["provider"] = True
            return {"changed_paths": [], "recorded_actions": [], "validation_passed": True}

    result = entry.run_agent_node(
        root=ROOT,
        canonical_state=_canonical_state(),
        route_context=_route_context(),
        bundle=None,
        event_id="evt-nobundle-1",
        run_id="run-nobundle-1",
        gate="G2_EXECUTION",
        requested_action="draft_pr_creation",
        scenario="standard_pr_delivery",
        input_payload={
            "g2_envelope": {"task_id": "SCRUM-566", "authority_gate": "G2_EXECUTION", "repository": "nhatnguyenquang1838-coder/gwc", "base_sha": "a" * 40, "working_branch": "chatgpt/scrum-566-agent-runtime-corrective", "scope_hash": "sha256:" + "c" * 64},
            "approval_receipt": {"status": "VALID"},
            "approved_paths": ["tools/node_architect/scratch/x.py"],
            "working_branch": "chatgpt/scrum-566-agent-runtime-corrective",
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "scope_hash": "sha256:" + "c" * 64,
            "idempotency_key": "evt-nobundle-1",
        },
        evidence_root=tmp_path,
        mode="shadow_readonly",
        provider=RecordingProvider(),
    )

    assert called["provider"] is False
    assert result["status"] == "SEMANTIC_NODE_BLOCKED"
    assert "AGENT_INSTRUCTION_BUNDLE_MISSING" in str(result.get("reason_code", ""))
