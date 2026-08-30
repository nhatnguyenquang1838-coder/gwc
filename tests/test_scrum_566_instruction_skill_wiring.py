from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

from tools.node_architect.build_node_instruction_pack import build_node_instruction_pack


def _module(name: str):
    spec = importlib.util.find_spec(name)
    assert spec is not None, f"{name} must exist"
    return importlib.import_module(name)


def _write(root: Path, ref: str, content: str) -> None:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _root(tmp_path: Path, *, skill_text: str = "executor skill v1") -> Path:
    _write(tmp_path, "AGENTS.md", "root agents instruction")
    _write(tmp_path, "agents/chatgpt-agent/gwc-governed-base.md", "governed base instruction")
    _write(tmp_path, "agents/chatgpt-agent/agent-instructions.md", "chatgpt composed instruction")
    _write(tmp_path, "agents/autonomous-agent/agent-instructions.md", "autonomous role overlay")
    _write(tmp_path, "skills/executor/SKILL.md", skill_text)
    _write(tmp_path, "skills/task-controller/SKILL.md", "task controller skill")
    _write(
        tmp_path,
        "core/node-architect/node-instructions/repo_delivery/ai-assisted-execution.node-instruction.yaml",
        "node_id: repo_delivery.ai-assisted-execution\nentry: true\n",
    )
    return tmp_path


def _bundle(root: Path):
    module = _module("tools.node_architect.agent_instruction_bundle")
    return module.resolve_agent_instruction_bundle(
        root=root,
        instruction_refs=(
            "AGENTS.md",
            "agents/chatgpt-agent/gwc-governed-base.md",
            "agents/chatgpt-agent/agent-instructions.md",
        ),
        role_overlay_refs=("agents/autonomous-agent/agent-instructions.md",),
        required_skill_names=("task-controller", "executor"),
        node_instruction_ref=(
            "core/node-architect/node-instructions/repo_delivery/"
            "ai-assisted-execution.node-instruction.yaml"
        ),
    )


def _request() -> dict:
    return {
        "run_id": "scrum-566-instruction-wiring",
        "task_id": "SCRUM-566",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "preprod_base_sha": "a" * 40,
        "working_branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "scope_hash": "sha256:" + "b" * 64,
        "graph_revision": "graph-r1",
        "policy_revision": "policy-r1",
        "allowed_paths": [],
        "prohibited_paths": [],
        "authorized_actions": [],
        "validation_commands": [],
        "idempotency_key": "instruction-wiring-idem",
    }


def test_bundle_contains_actual_instruction_skill_and_node_instruction_contents(tmp_path: Path):
    bundle = _bundle(_root(tmp_path))

    assert bundle["instruction_refs"] == [
        "AGENTS.md",
        "agents/chatgpt-agent/gwc-governed-base.md",
        "agents/chatgpt-agent/agent-instructions.md",
    ]
    assert bundle["role_overlay_refs"] == ["agents/autonomous-agent/agent-instructions.md"]
    assert bundle["skill_refs"] == [
        "skills/task-controller/SKILL.md",
        "skills/executor/SKILL.md",
    ]
    assert bundle["node_instruction_ref"].endswith("ai-assisted-execution.node-instruction.yaml")
    assert bundle["bundle_digest"].startswith("sha256:")
    assert all(item["digest"].startswith("sha256:") for item in bundle["artifacts"])
    by_ref = {item["ref"]: item for item in bundle["artifacts"]}
    assert by_ref["AGENTS.md"]["content"] == "root agents instruction"
    assert by_ref["skills/executor/SKILL.md"]["content"] == "executor skill v1"
    assert "node_id: repo_delivery.ai-assisted-execution" in by_ref[bundle["node_instruction_ref"]]["content"]


def test_skill_selection_is_explicit_and_cannot_escape_skill_root(tmp_path: Path):
    module = _module("tools.node_architect.agent_instruction_bundle")
    root = _root(tmp_path)

    try:
        module.resolve_agent_instruction_bundle(
            root=root,
            instruction_refs=("AGENTS.md",),
            required_skill_names=("../executor",),
            node_instruction_ref="core/node-architect/node-instructions/repo_delivery/ai-assisted-execution.node-instruction.yaml",
        )
    except module.InstructionBundleError as exc:
        assert exc.reason_code == "AGENT_SKILL_NAME_INVALID"
    else:
        raise AssertionError("skill path escape must fail closed")


def test_missing_required_skill_fails_closed_instead_of_silent_fallback(tmp_path: Path):
    module = _module("tools.node_architect.agent_instruction_bundle")
    root = _root(tmp_path)

    try:
        module.resolve_agent_instruction_bundle(
            root=root,
            instruction_refs=("AGENTS.md",),
            required_skill_names=("missing-skill",),
            node_instruction_ref="core/node-architect/node-instructions/repo_delivery/ai-assisted-execution.node-instruction.yaml",
        )
    except module.InstructionBundleError as exc:
        assert exc.reason_code == "AGENT_INSTRUCTION_SOURCE_MISSING"
        assert "skills/missing-skill/SKILL.md" in str(exc)
    else:
        raise AssertionError("missing required skill must fail closed")


def test_instruction_pack_carries_resolved_bundle_and_content_change_breaks_replay_digest(tmp_path: Path):
    first_root = _root(tmp_path / "first", skill_text="executor skill v1")
    second_root = _root(tmp_path / "second", skill_text="executor skill v2")
    first_bundle = _bundle(first_root)
    second_bundle = _bundle(second_root)

    first = build_node_instruction_pack(_request(), instruction_bundle=first_bundle)
    second = build_node_instruction_pack(_request(), instruction_bundle=second_bundle)

    assert first.instruction_bundle_digest == first_bundle["bundle_digest"]
    assert first.skill_refs == tuple(first_bundle["skill_refs"])
    assert first.skill_digests == tuple(first_bundle["skill_digests"])
    assert first.node_instruction_ref == first_bundle["node_instruction_ref"]
    assert first.node_instruction_digest == first_bundle["node_instruction_digest"]
    assert any(item[1] == "skills/executor/SKILL.md" and item[3] == "executor skill v1" for item in first.instruction_bundle)
    assert first.content_digest != second.content_digest


class RecordingProvider:
    name = "recording-provider"

    def __init__(self):
        self.packs = []

    def run(self, pack):
        self.packs.append(pack)
        return {"changed_paths": [], "recorded_actions": [], "validation_passed": True}


def test_agent_provider_receives_host_resolved_bundle_and_node_input_cannot_override_skills(tmp_path: Path):
    bridge = _module("tools.node_architect.agent_provider_bridge")
    bundle = _bundle(_root(tmp_path))
    provider = RecordingProvider()
    binding = bridge.build_agent_provider_binding(
        node_id="repo_delivery.ai-assisted-execution",
        evaluator_path="tools/node_architect/ai_agent_adapter.py",
        request=_request(),
        provider=provider,
        instruction_bundle=bundle,
        idempotency_store={},
    )

    result = binding.handler({
        "objective": "repair",
        "skill_refs": ["skills/attacker/SKILL.md"],
        "instruction_bundle": {"bundle_digest": "sha256:attacker"},
    })

    assert result["runtime_disposition"] == "CONTINUE"
    pack = provider.packs[0]
    assert pack.instruction_bundle_digest == bundle["bundle_digest"]
    assert pack.skill_refs == tuple(bundle["skill_refs"])
    assert "skills/attacker/SKILL.md" not in pack.skill_refs
    assert any(item[1] == "skills/task-controller/SKILL.md" for item in pack.instruction_bundle)


def test_agent_provider_fails_closed_when_instruction_bundle_missing():
    bridge = _module("tools.node_architect.agent_provider_bridge")
    provider = RecordingProvider()
    binding = bridge.build_agent_provider_binding(
        node_id="repo_delivery.ai-assisted-execution",
        evaluator_path="tools/node_architect/ai_agent_adapter.py",
        request=_request(),
        provider=provider,
        instruction_bundle=None,
        idempotency_store={},
    )

    result = binding.handler({"objective": "repair"})

    assert result["runtime_disposition"] == "BLOCK"
    assert result["reason_code"] == "AGENT_INSTRUCTION_BUNDLE_MISSING"
    assert provider.packs == []
