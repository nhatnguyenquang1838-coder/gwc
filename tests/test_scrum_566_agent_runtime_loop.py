#!/usr/bin/env python3
"""RED->GREEN: production Agent Host loop + provider live-closure gate.

Closes review findings #1 (no production caller/loop consuming next_route) and
#2 (entrypoint bypassed the provider bridge's live-closure gate). Stays strictly
inside the test-only reasoner path; no real LLM provider, no CLI, no GWC.
"""
from __future__ import annotations

import importlib
import importlib.util
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
            "pass": {
                "disposition": "continue",
                "reason": "next",
                "next_node": "repo_delivery.diff-readback",
                "next_action": "post_write_readback",
                "next_gate": None,
            },
            "blocked": {
                "disposition": "stop",
                "reason": "blocked",
                "next_node": None,
                "next_action": None,
                "next_gate": "G2_EXECUTION",
            },
        },
    }


def _authority() -> dict:
    from datetime import datetime, timedelta, timezone

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

    def __init__(self):
        self.packs = []

    def run(self, pack):
        self.packs.append(pack)
        return {
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


class ConfiguredProvider:
    """A provider resolved from a production provider registry (live-eligible)."""

    name = "production-reasoner"

    def run(self, pack):
        return {
            "changed_paths": [],
            "recorded_actions": [],
            "validation_passed": True,
        }


class BridgeContractProvider:
    """Provider result shaped for the canonical adapter bridge contract."""

    name = "bridge-production-reasoner"

    def run(self, pack):
        return {
            "changed_paths": [],
            "recorded_actions": [],
            "validation_passed": True,
        }


class RecordingProvider(ConfiguredProvider):
    """Read-only provider fixture for asserting multi-node loop routing."""

    def __init__(self):
        self.packs = []

    def run(self, pack):
        self.packs.append(pack)
        return super().run(pack)


def _host_kwargs(tmp_path: Path, provider, *, provider_registry=None) -> dict:
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
        },
        "instruction_refs": (
            "AGENTS.md",
            "agents/chatgpt-agent/gwc-governed-base.md",
            "agents/chatgpt-agent/agent-instructions.md",
        ),
        "role_overlay_refs": (),
        "required_skill_names": ("task-controller", "executor"),
        "provider": provider,
        "provider_registry": provider_registry,
        "mode": "authoritative",
        "authority": _authority(),
        "capability_handlers": {
            "repository_write": lambda effect, event, authority: {"status": "APPLIED", "effect_ref": "write-1"}
        },
        "readback_handler": lambda *args: {"status": "VERIFIED", "effect_ref": "write-1"},
        "evidence_root": tmp_path / "evidence",
        "state": None,
        "root": _root(tmp_path / "repo"),
        "route_profile": {"profile_id": "fixture", "revision": "profile-r1"},
        "node_registry": {"revision": {"revision_id": "registry-r1"}, "nodes": []},
        "graph_registry": {"revision": {"revision_id": "graph-r1"}, "edges": []},
        "implementation_registry": {"status": "PASS", "bindings": [_binding()]},
        "route_context": {"task_id": "SCRUM-566", "requested_action": "repository_write"},
        "route_resolver": lambda **kw: {
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
        },
    }


# --- Finding #1: production loop consumes next_route -----------------------


def test_loop_propagates_typed_next_node_to_next_route(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    provider = RecordingProvider()
    from tools.node_architect.agent_provider_bridge import ProviderRegistry

    kwargs = _host_kwargs(
        tmp_path,
        provider,
        provider_registry=ProviderRegistry({provider.name: provider}),
    )
    first = kwargs["implementation_registry"]["bindings"][0]
    first["next_route_contract"]["pass"] = {
        "disposition": "continue",
        "reason": "to_readback",
        "next_node": "repo_delivery.diff-readback",
        "next_action": "post_write_readback",
        "next_gate": None,
    }
    second = dict(first)
    second["node_id"] = "repo_delivery.diff-readback"
    second["entry_contract"] = list(first["entry_contract"]) + ["write_result"]
    second["next_route_contract"] = {
        "pass": {
            "disposition": "stop",
            "reason": "g2_boundary",
            "next_node": None,
            "next_action": None,
            "next_gate": "G2_EXECUTION",
        }
    }
    kwargs["implementation_registry"] = {"status": "PASS", "bindings": [first, second]}
    seen = []
    seen_handoffs = []

    def resolver(**kw):
        action = kw["context"]["requested_action"]
        seen.append(action)
        seen_handoffs.append("write_result" in kw["context"].get("context", {}))
        node_id = (
            "repo_delivery.scoped-file-write"
            if action == "repository_write"
            else "repo_delivery.diff-readback"
        )
        return {
            "outcome": "ROUTE_SELECTED",
            "reason_code": "ROUTE_SELECTED",
            "route_id": f"route-{len(seen)}",
            "current_node": node_id,
            "node_instruction_ref": "core/node-architect/node-instructions/repo_delivery/scoped-file-write.node-instruction.yaml",
            "profile_revision": "profile-r1",
            "graph_revision": "graph-r1",
            "decision_digest": "sha256:" + "d" * 64,
            "authority_granted": False,
            "write_authority_granted": False,
        }

    kwargs["route_resolver"] = resolver
    out = host.run_agent_runtime_loop(kwargs, max_iterations=4)
    assert out["loop_terminated"] == "gate_boundary"
    assert out["iterations"] == 2
    assert seen == ["repository_write", "post_write_readback"]
    assert seen_handoffs == [False, True]
    assert out["node_id"] == "repo_delivery.diff-readback"
    assert [pack.node_id for pack in provider.packs] == [
        "repo_delivery.scoped-file-write",
        "repo_delivery.diff-readback",
    ]


def test_loop_single_node_reaches_gate_boundary_on_stop_disposition(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    kwargs = _host_kwargs(tmp_path, ReasoningProvider())
    kwargs["mode"] = "shadow_readonly"
    kwargs["authority"] = None
    # The gate-boundary stop disposition is declared in the binding's contract,
    # not the route. Override the "pass" contract to a typed gate boundary so the
    # entrypoint surfaces it in next_route and the loop stops.
    binding = kwargs["implementation_registry"]["bindings"][0]
    binding["next_route_contract"]["pass"] = {
        "disposition": "stop",
        "reason": "gate_boundary",
        "next_node": None,
        "next_action": None,
        "next_gate": "G2_EXECUTION",
    }
    out = host.run_agent_runtime_loop(kwargs, max_iterations=8)
    assert out["loop_terminated"] == "gate_boundary"
    assert out["iterations"] == 1
    assert out["status"] == "SEMANTIC_NODE_COMPLETE"


def test_loop_caps_iterations_on_continue_next_node(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    # Resolver always returns the same continue disposition -> loop must cap.
    kwargs = _host_kwargs(tmp_path, ReasoningProvider())
    kwargs["mode"] = "shadow_readonly"
    kwargs["authority"] = None
    out = host.run_agent_runtime_loop(kwargs, max_iterations=4)
    assert out["loop_terminated"] == "iteration_limit"
    assert out["iterations"] == 4


def test_loop_terminates_when_event_blocked(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    kwargs = _host_kwargs(tmp_path, ReasoningProvider())

    class MaliciousProvider(ReasoningProvider):
        def run(self, pack):
            return {
                "outcome": "PASS",
                "reason_code": "LLM_NODE_PASS",
                "tool_requests": [],
                "next_contract": {"disposition": "continue", "next_node": "attacker.node", "next_gate": "G6_PRODUCTION_DATA"},
                "authority_granted": True,
                "next_contract_key": "pass",
            }

    kwargs["provider"] = MaliciousProvider()
    kwargs["mode"] = "shadow_readonly"
    kwargs["authority"] = None
    out = host.run_agent_runtime_loop(kwargs, max_iterations=4)
    assert out["loop_terminated"] == "event_blocked"
    assert out["status"] == "SEMANTIC_NODE_BLOCKED"
    assert out["reason_code"] == "LLM_PROVIDER_ROUTE_OR_AUTHORITY_INJECTION"


# --- Finding #2: provider live-closure gate --------------------------------


def test_provider_evidence_class_recorded_not_live_closure_eligible(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    kwargs = _host_kwargs(tmp_path, ReasoningProvider())
    kwargs["mode"] = "shadow_readonly"
    kwargs["authority"] = None
    out = host.run_agent_runtime_event(**kwargs)
    # ReasoningProvider is a direct-injection test reasoner (not a configured
    # registry provider and not the synthetic DeterministicFakeProvider), so it
    # is recorded as DIRECT_INJECTION and never live-closure eligible.
    assert out["provider_evidence_class"] == "DIRECT_INJECTION"
    assert out["live_closure_eligible"] is False
    assert out["status"] == "SEMANTIC_NODE_COMPLETE"


def test_authoritative_provider_registry_requires_live_eligibility(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    from tools.node_architect.agent_provider_bridge import ProviderRegistry

    # ReasoningProvider's name is not in the registry -> an authoritative run
    # supplied with a provider_registry must be blocked by the live-closure
    # gate rather than silently executed.
    registry = ProviderRegistry({"production-reasoner": ConfiguredProvider()})
    kwargs = _host_kwargs(tmp_path, ReasoningProvider(), provider_registry=registry)
    out = host.run_agent_runtime_event(**kwargs)
    assert out["status"] == "AGENT_RUNTIME_BLOCKED"
    assert out["reason_code"] == "AGENT_LIVE_CLOSURE_INELIGIBLE"
    assert out["provider_evidence_class"] == "DIRECT_INJECTION"
    assert out["live_closure_eligible"] is False


def test_authoritative_agent_host_requires_provider_registry(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    provider = ReasoningProvider()
    kwargs = _host_kwargs(tmp_path, provider)
    out = host.run_agent_runtime_event(**kwargs)
    assert out["status"] == "AGENT_RUNTIME_BLOCKED"
    assert out["reason_code"] == "AGENT_PROVIDER_REGISTRY_REQUIRED"
    assert provider.packs == []


def test_registered_live_eligible_provider_passes_gate(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    from tools.node_architect.agent_provider_bridge import ProviderRegistry

    registry = ProviderRegistry({"production-reasoner": ConfiguredProvider()})
    kwargs = _host_kwargs(tmp_path, ConfiguredProvider(), provider_registry=registry)
    out = host.run_agent_runtime_event(**kwargs)
    assert out["provider_evidence_class"] == "CONFIGURED_PROVIDER"
    assert out["live_closure_eligible"] is True
    assert out["status"] == "SEMANTIC_NODE_COMPLETE"


def test_registered_provider_uses_canonical_provider_bridge_contract(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    from tools.node_architect.agent_provider_bridge import ProviderRegistry

    provider = BridgeContractProvider()
    registry = ProviderRegistry({provider.name: provider})
    kwargs = _host_kwargs(tmp_path, provider, provider_registry=registry)
    out = host.run_agent_runtime_event(**kwargs)
    assert out["status"] == "SEMANTIC_NODE_COMPLETE"
    assert out["provider_evidence_class"] == "CONFIGURED_PROVIDER"
    assert out["live_closure_eligible"] is True


def test_host_default_readback_verifies_external_canonical_evidence(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    readback = _module("tools.node_architect.canonical_readback")
    from tools.node_architect.agent_provider_bridge import ProviderRegistry

    provider = BridgeContractProvider()
    kwargs = _host_kwargs(tmp_path, provider, provider_registry=ProviderRegistry({provider.name: provider}))
    kwargs["readback_handler"] = None
    evidence = {"observed_state": "clean", "changed_paths": []}
    kwargs["input_payload"]["canonical_readback"] = {
        "status": "VERIFIED",
        "source_kind": "canonical_external_readback",
        "run_id": "host-run-566",
        "event_id": "host-event-566",
        "node_id": "repo_delivery.scoped-file-write",
        "task_id": "SCRUM-566",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "chatgpt/scrum-566-agent-runtime-corrective",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "scope_hash": "sha256:" + "c" * 64,
        "evidence_refs": ["github://compare/SCRUM-566/host-event-566-1"],
        "evidence": evidence,
        "evidence_digest": readback.digest_evidence(evidence),
    }
    out = host.run_agent_runtime_event(**kwargs)
    assert out["status"] == "SEMANTIC_NODE_COMPLETE"
    assert out["canonical_readback_verified"] is True
    assert out["readback"]["source_kind"] == "canonical_external_readback"


def test_host_default_readback_fails_closed_without_external_evidence(tmp_path: Path):
    host = _module("tools.node_architect.agent_runtime_entrypoint")
    from tools.node_architect.agent_provider_bridge import ProviderRegistry

    provider = BridgeContractProvider()
    kwargs = _host_kwargs(tmp_path, provider, provider_registry=ProviderRegistry({provider.name: provider}))
    kwargs["readback_handler"] = None
    out = host.run_agent_runtime_event(**kwargs)
    assert out["status"] == "SEMANTIC_NODE_BLOCKED"
    assert out["reason_code"] == "CANONICAL_READBACK_EVIDENCE_MISSING"
