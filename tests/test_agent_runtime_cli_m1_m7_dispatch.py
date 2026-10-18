"""SCRUM-841 explicit workflow selection through the existing Agent Host CLI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.node_architect.agent_runtime_cli import AgentRuntimeCliError, _load_manifest, _prepare_event, main as cli_main


def _write_manifest(path: Path, *, workflow_selection=None):
    payload = {"provider_name": "configured-provider", "event": {"event_id": "event-841", "input_payload": {"task_summary": "M1-M7"}}}
    if workflow_selection is not None:
        payload["workflow_selection"] = workflow_selection
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cli_preserves_explicit_scrum841_workflow_selection(tmp_path: Path):
    selection = {
        "workflow_id": "scrum841-m1-m7-agent-workflow-r1",
        "operation_envelope": {"operation_id": "op-841-1"},
        "inputs": {"observer_qualified": False},
    }
    manifest = _load_manifest(_write_manifest(tmp_path / "manifest.json", workflow_selection=selection))
    event = _prepare_event(manifest, type("Provider", (), {"name": "configured-provider"})())
    assert event["m1_m7_workflow_selection"] == selection


def test_cli_passes_explicit_selection_through_canonical_loop(tmp_path: Path, monkeypatch, capsys):
    import tools.node_architect.agent_runtime_cli as cli

    selection = {
        "workflow_id": "scrum841-m1-m7-agent-workflow-r1",
        "operation_envelope": {"operation_id": "op-841-2"},
        "inputs": {"observer_qualified": False},
    }
    manifest_path = _write_manifest(tmp_path / "manifest.json", workflow_selection=selection)
    class Provider:
        name = "configured-provider"
    captured = {}
    monkeypatch.setattr(cli, "_load_factory", lambda _: (lambda: Provider()))
    def fake_loop(event_kwargs, *, max_iterations=32):
        captured.update(event_kwargs)
        return {"status": "SEMANTIC_NODE_SUSPENDED", "reason_code": "OBSERVER_UNQUALIFIED"}
    monkeypatch.setattr(cli, "run_agent_runtime_loop", fake_loop)
    result = cli_main(["--manifest", str(manifest_path), "--provider-factory", "unused:factory"])
    assert result == 0
    assert captured["m1_m7_workflow_selection"] == selection
    assert json.loads(capsys.readouterr().out)["reason_code"] == "OBSERVER_UNQUALIFIED"


def test_cli_rejects_unknown_workflow_selection(tmp_path: Path):
    with pytest.raises(AgentRuntimeCliError, match="WORKFLOW_SELECTION_INVALID"):
        _load_manifest(_write_manifest(tmp_path / "manifest.json", workflow_selection={"workflow_id": "unknown"}))


def test_default_cli_manifest_has_no_workflow_selection(tmp_path: Path):
    manifest = _load_manifest(_write_manifest(tmp_path / "manifest.json"))
    event = _prepare_event(manifest, type("Provider", (), {"name": "configured-provider"})())
    assert "m1_m7_workflow_selection" not in event
