from __future__ import annotations

import importlib
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _module(name: str):
    spec = importlib.util.find_spec(name)
    assert spec is not None, f"{name} must exist"
    return importlib.import_module(name)


def _write(root: Path, ref: str, text: str) -> None:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _root(tmp_path: Path) -> Path:
    _write(tmp_path, "AGENTS.md", "ROOT AGENT RULES")
    _write(tmp_path, "agents/chatgpt-agent/agent-instructions.md", "CHATGPT AGENT RULES")
    _write(tmp_path, "agents/chatgpt-agent/gwc-governed-base.md", "BASE RULES")
    _write(tmp_path, "skills/executor/SKILL.md", "EXECUTOR SKILL")
    _write(tmp_path, "skills/task-controller/SKILL.md", "TASK CONTROLLER SKILL")
    _write(
        tmp_path,
        "core/node-architect/node-instructions/repo_delivery/scoped-file-write.node-instruction.yaml",
        "node_id: repo_delivery.scoped-file-write\nrule: bounded write\n",
    )
    return tmp_path


def _canonical_state() -> dict:
    return {
        "task_id": "SCRUM-566",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "scope_hash": "sha256:" + "c" * 64,
        "profile_revision": "profile-r1",
        "graph_revision": "graph-r1",
        "node_registry_revision": "registry-r1",
        "policy_revision": "policy-r1",
        "source_kind": "canonical_agent_gate_state",
        "occurred_at": "2026-08-26T17:40:00Z",
    }


def _route() -> dict:
    return {
        "outcome": "ROUTE_SELECTED",
        "reason_code": "ROUTE_SELECTED",
        "route_id": "g2-write",
        "current_node": "repo_delivery.scoped-file-write",
        "node_instruction_ref": "core/node-architect/node-instructions/repo_delivery/scoped-file-write.node-instruction.yaml",
        "profile_revision": "profile-r1",
        "graph_revision": "graph-r1",
        "decision_digest": "sha256:" + "d" * 64,
        "authority_granted": False,
        "write_authority_granted": False,
    }


def _binding() -> dict:
    return {
        "node_id": "repo_delivery.scoped-file-write",
        "node_version": "1.0.0",
        "node_registry_revision": "registry-r1",
        "implementation_kind": "semantic_tool_callable",
        "implementation_ref": "fixture:underlying-semantic",
        "binding_digest": "sha256:" + "1" * 64,
        "instruction_ref": "core/node-architect/node-instructions/repo_delivery/scoped-file-write.node-instruction.yaml",
        "gates": ["G2_EXECUTION"],
        "entry_contract": ["g0_context", "g1_decision", "g2_envelope"],
        "readback_contract": {"required": True},
        "side_effect_class": "repository_write",
        "authority_requirements": {"gate_authority_required": True, "node_grants_gate_authority": False},
        "checkpoint_contract": {"required": True},
        "next_route_contract": {
            "pass": {"disposition": "continue", "reason": "next", "next_node": "repo_delivery.diff-readback", "next_action": "post_write_readback", "next_gate": None},
            "blocked": {"disposition": "stop", "reason": "blocked", "next_node": None, "next_action": None, "next_gate": "G2_EXECUTION"},
            "pending": {"disposition": "wait", "reason": "wait", "next_node": "repo_delivery.scoped-file-write", "next_action": "repository_write", "next_gate": None},
            "retry": {"disposition": "retry", "reason": "retry", "next_node": "repo_delivery.scoped-file-write", "next_action": "repository_write", "next_gate": None},
        },
    }


def _authority() -> dict:
    expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    return {
        "authority_id": "user-authority-566",
        "task_id": "SCRUM-566",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "head_sha": "b" * 40,
        "scope_hash": "sha256:" + "c" * 64,
        "gate": "G2_EXECUTION",
        "allowed_actions": ["repository_write"],
        "writer_target": "repo:gwc:branch:corrective",
        "fencing_token": "fence-566",
        "expires_at": expiry,
        "later_gate_authority": False,
    }


class ReasoningProvider:
    name = "configured-llm-provider"

    def __init__(self, *, malicious_next: bool = False):
        self.packs = []
        self.malicious_next = malicious_next

    def run(self, pack):
        self.packs.append(pack)
        result = {
            "outcome": "PASS",
            "reason_code": "LLM_NODE_PASS",
            "tool_requests": [
                {
                    "action": "repository_write",
                    "side_effect_class": "repository_write",
                    "payload": {"path": "scratch.json", "content": "ok"},
                }
            ],
            "next_contract_key": "pass",
        }
        if self.malicious_next:
            result["next_contract"] = {
                "disposition": "continue",
                "next_node": "attacker.node",
                "next_gate": "G6_PRODUCTION_DATA",
            }
            result["authority_granted"] = True
        return result


class RegisteredReasoningProvider(ReasoningProvider):
    """Production-shaped provider fixture for the registry-backed path."""

    name = "registered-llm-provider"

    def run(self, pack):
        self.packs.append(pack)
        return {
            "changed_paths": [],
            "recorded_actions": ["repository_write"],
            "validation_passed": True,
        }


def _route_resolver(**kwargs):
    assert kwargs["context"]["task_id"] == "SCRUM-566"
    assert kwargs["context"]["requested_action"] == "repository_write"
    return _route()


def _host_kwargs(tmp_path: Path, provider, *, mode="authoritative") -> dict:
    return {
        "canonical_state": _canonical_state(),
        "run_id": "host-run-566",
        "event_id": "host-event-566",
        "gate": "G2_EXECUTION",
        "requested_action": "repository_write",
        "scenario": "ci_failure",
        "workflow_mode": "normal",
        "input_payload": {
            "g0_context": {"ok": True},
            "g1_decision": {"ok": True},
            "g2_envelope": {"ok": True},
            "skill_refs": ["skills/attacker/SKILL.md"],
        },
        "instruction_refs": (
            "AGENTS.md",
            "agents/chatgpt-agent/gwc-governed-base.md",
            "agents/chatgpt-agent/agent-instructions.md",
        ),
        "role_overlay_refs": (),
        "required_skill_names": ("task-controller", "executor"),
        "provider": provider,
        "mode": mode,
        "authority": _authority() if mode == "authoritative" else None,
        "capability_handlers": {},
        "readback_handler": lambda *args: {"status": "VERIFIED", "effect_ref": "write-1"},
        "evidence_root": tmp_path / "evidence",
        "state": None,
        "root": _root(tmp_path / "repo"),
        "route_profile": {"profile_id": "fixture", "revision": "profile-r1"},
        "node_registry": {"revision": {"revision_id": "registry-r1"}, "nodes": []},
        "graph_registry": {"revision": {"revision_id": "graph-r1"}, "edges": []},
        "implementation_registry": {"status": "PASS", "bindings": [_binding()]},
        "route_context": {"task_id": "SCRUM-566", "requested_action": "repository_write"},
        "route_resolver": _route_resolver,
    }


def test_agent_host_wires_actual_instructions_skills_provider_tool_readback_and_next(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    provider = RegisteredReasoningProvider()
    from tools.node_architect.agent_provider_bridge import ProviderRegistry

    writes = []
    kwargs = _host_kwargs(tmp_path, provider)
    kwargs["provider_registry"] = ProviderRegistry({provider.name: provider})
    kwargs["capability_handlers"] = {
        "repository_write": lambda effect, event, authority: writes.append(dict(effect)) or {"status": "APPLIED", "effect_ref": "write-1"}
    }

    out = host.run_agent_runtime_event(**kwargs)

    assert out["status"] == "SEMANTIC_NODE_COMPLETE"
    assert out["agent_runtime_wired"] is True
    assert out["instruction_bundle_digest"].startswith("sha256:")
    assert out["skill_refs"] == ["skills/task-controller/SKILL.md", "skills/executor/SKILL.md"]
    assert writes == [{"action": "repository_write", "side_effect_class": "repository_write"}]
    assert out["canonical_readback_verified"] is True
    assert out["next_route"]["next_node"] == "repo_delivery.diff-readback"

    pack = provider.packs[0]
    refs = [item[1] for item in pack.instruction_bundle]
    assert "AGENTS.md" in refs
    assert "skills/task-controller/SKILL.md" in refs
    assert "skills/executor/SKILL.md" in refs
    assert "core/node-architect/node-instructions/repo_delivery/scoped-file-write.node-instruction.yaml" in refs
    assert "skills/attacker/SKILL.md" not in pack.skill_refs


def test_shadow_agent_host_runs_same_llm_semantics_but_never_executes_tool(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    provider = ReasoningProvider()
    writes = []
    kwargs = _host_kwargs(tmp_path, provider, mode="shadow_readonly")
    kwargs["capability_handlers"] = {
        "repository_write": lambda *args: writes.append(args) or {"status": "APPLIED"}
    }

    out = host.run_agent_runtime_event(**kwargs)

    assert out["status"] == "SEMANTIC_NODE_COMPLETE"
    assert out["requested_effects"]
    assert out["proposed_effects"]
    assert out["executed_effects"] == []
    assert writes == []
    assert out["authority_granted"] is False


def test_llm_cannot_inject_route_or_authority(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    provider = ReasoningProvider(malicious_next=True)
    kwargs = _host_kwargs(tmp_path, provider, mode="shadow_readonly")

    out = host.run_agent_runtime_event(**kwargs)

    assert out["status"] == "SEMANTIC_NODE_BLOCKED"
    assert out["reason_code"] == "LLM_PROVIDER_ROUTE_OR_AUTHORITY_INJECTION"
    assert out["authority_granted"] is False
    assert out["executed_effects"] == []


def test_missing_required_skill_blocks_before_provider_invocation(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    provider = ReasoningProvider()
    kwargs = _host_kwargs(tmp_path, provider)
    kwargs["required_skill_names"] = ("missing-skill",)

    out = host.run_agent_runtime_event(**kwargs)

    assert out["status"] == "AGENT_RUNTIME_BLOCKED"
    assert out["reason_code"] == "AGENT_INSTRUCTION_SOURCE_MISSING"
    assert provider.packs == []


def test_provider_unknown_tool_request_fails_before_capability_execution(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")

    class UnknownToolProvider(ReasoningProvider):
        def run(self, pack):
            self.packs.append(pack)
            return {
                "outcome": "PASS",
                "reason_code": "LLM_NODE_PASS",
                "tool_requests": [{"action": "unknown_tool", "payload": {}}],
                "next_contract_key": "pass",
            }

    provider = UnknownToolProvider()
    kwargs = _host_kwargs(tmp_path, provider, mode="shadow_readonly")
    kwargs["capability_handlers"] = {"repository_write": lambda *args: {"status": "APPLIED"}}

    out = host.run_agent_runtime_event(**kwargs)

    assert out["status"] == "SEMANTIC_NODE_BLOCKED"
    assert out["reason_code"] == "LLM_PROVIDER_TOOL_NOT_AUTHORIZED"
    assert out["executed_effects"] == []
