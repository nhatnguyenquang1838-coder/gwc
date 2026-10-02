from __future__ import annotations

import json
from pathlib import Path

import pytest


# The production caller is intentionally required to exist; this import is RED
# until the bounded CLI is implemented.
from tools.node_architect import agent_runtime_cli


class RegisteredProvider:
    name = "production-provider"

    def run(self, pack):
        return {
            "terminal_outcome": "SUCCESS",
            "changed_paths": [],
            "recorded_actions": [],
            "validation_passed": True,
            "next_action": "stop",
        }


def _manifest(tmp_path: Path) -> Path:
    payload = {
        "provider_name": "production-provider",
        "event": {
            "canonical_state": {"task_id": "SCRUM-566"},
            "run_id": "live-run-566",
            "event_id": "live-event-566",
            "gate": "G2_EXECUTION",
            "requested_action": "semantic_runtime_execution",
            "scenario": "production_agent_runtime",
            "workflow_mode": "authoritative",
            "input_payload": {},
            "instruction_refs": ["AGENTS.md"],
            "role_overlay_refs": [],
            "required_skill_names": [],
            "mode": "shadow_readonly",
            "authority": None,
            "capability_handlers": {},
            "evidence_root": str(tmp_path / "evidence"),
            "root": str(tmp_path),
            "route_profile": {},
            "node_registry": {},
            "graph_registry": {},
        },
    }
    path = tmp_path / "runtime-manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cli_requires_explicit_provider_factory(tmp_path: Path, capsys):
    result = agent_runtime_cli.main(["--manifest", str(_manifest(tmp_path))])
    assert result == 1
    assert json.loads(capsys.readouterr().out)["reason_code"] == "AGENT_PROVIDER_FACTORY_REQUIRED"


def test_cli_builds_registry_and_calls_canonical_loop(tmp_path: Path, monkeypatch, capsys):
    module = tmp_path / "production_provider.py"
    module.write_text(
        "class Provider:\n"
        "    name = 'production-provider'\n"
        "    def run(self, pack):\n"
        "        return {'terminal_outcome': 'SUCCESS', 'changed_paths': [], 'recorded_actions': [], 'validation_passed': True, 'next_action': 'stop'}\n"
        "def build_provider():\n"
        "    return Provider()\n",
        encoding="utf-8",
    )
    calls = {}

    def fake_loop(event_kwargs, *, max_iterations=32):
        calls["event_kwargs"] = event_kwargs
        calls["max_iterations"] = max_iterations
        return {"status": "SEMANTIC_NODE_COMPLETE", "loop_terminated": "terminal"}

    monkeypatch.setattr(agent_runtime_cli, "run_agent_runtime_loop", fake_loop)
    result = agent_runtime_cli.main([
        "--manifest", str(_manifest(tmp_path)),
        "--provider-factory", f"{module}:build_provider",
        "--max-iterations", "7",
    ])
    assert result == 0
    assert calls["max_iterations"] == 7
    event = calls["event_kwargs"]
    assert event["provider"].name == "production-provider"
    assert event["provider_registry"].resolve("production-provider") is event["provider"]
    assert event["mode"] == "shadow_readonly"
    assert json.loads(capsys.readouterr().out)["status"] == "SEMANTIC_NODE_COMPLETE"


def test_cli_rejects_factory_name_mismatch(tmp_path: Path, capsys):
    module = tmp_path / "wrong_provider.py"
    module.write_text(
        "class Provider:\n"
        "    name = 'wrong-provider'\n"
        "def build_provider():\n"
        "    return Provider()\n",
        encoding="utf-8",
    )
    result = agent_runtime_cli.main([
        "--manifest", str(_manifest(tmp_path)),
        "--provider-factory", f"{module}:build_provider",
    ])
    assert result == 1
    assert json.loads(capsys.readouterr().out)["reason_code"] == "AGENT_PROVIDER_NAME_MISMATCH"


def test_cli_routes_universal_run_manifest_through_execution_adapter(tmp_path: Path, monkeypatch, capsys):
    module = tmp_path / "universal_provider.py"
    module.write_text(
        "class Provider:\n"
        "    name = 'production-provider'\n"
        "    def run(self, pack): return {'terminal_outcome':'SUCCESS','changed_paths':[],'recorded_actions':[],'validation_passed':True,'next_action':'stop'}\n"
        "def build_provider(): return Provider()\n",
        encoding="utf-8",
    )
    manifest_path = _manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    universal_run = {
        "route_id": "UNIVERSAL_RUN_NEW_RUNTIME",
        "runtime_plan": {"run_id": "RUN-Q0", "digest": "sha256:" + "a" * 64},
        "run_state": {"run_id": "RUN-Q0", "active_gate": "UR.G2"},
        "node_allocation": {"run_id": "RUN-Q0", "node_allocation_id": "RUN-Q0:q0.qualification-campaign"},
        "evidence_root": str(tmp_path / "ledger"),
        "parent_composition": None,
    }
    manifest["universal_run"] = universal_run
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    calls = {}

    def fake_adapter(**kwargs):
        calls.update(kwargs)
        return {"status": "UNIVERSAL_RUN_NODE_COMPLETE", "authority_granted": False, "executed_effects": []}

    def unexpected_loop(*args, **kwargs):
        raise AssertionError("Q0 Universal Run manifest bypassed the execution adapter")

    monkeypatch.setattr(agent_runtime_cli, "execute_universal_run_node", fake_adapter, raising=False)
    monkeypatch.setattr(agent_runtime_cli, "run_agent_runtime_loop", unexpected_loop)
    result = agent_runtime_cli.main([
        "--manifest", str(manifest_path),
        "--provider-factory", f"{module}:build_provider",
        "--max-iterations", "5",
    ])

    assert result == 0
    assert calls["route_id"] == "UNIVERSAL_RUN_NEW_RUNTIME"
    assert calls["runtime_plan"] == universal_run["runtime_plan"]
    assert calls["run_state"] == universal_run["run_state"]
    assert calls["node_allocation"] == universal_run["node_allocation"]
    assert calls["event_kwargs"]["provider"].name == "production-provider"
    assert calls["max_iterations"] == 5
    assert json.loads(capsys.readouterr().out)["status"] == "UNIVERSAL_RUN_NODE_COMPLETE"
