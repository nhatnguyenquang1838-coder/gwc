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
