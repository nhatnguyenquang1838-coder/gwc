"""SCRUM-841 does not alter the Q0/default runtime path (P7).

Verifies the explicit SCRUM-841 manifest/profile selection is only an optional
workflow-mode: without the manifest the default CLI path has no workflow
selection, the default entrypoint never injects the SCRUM-841 selection, and
the profile explicitly rejects Q0 authority/plan/qualification reuse.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from tools.node_architect.m1_m7_agent_workflow import load_m1_m7_contracts
    _M1M7_AVAILABLE = True
except ImportError:  # langgraph is an optional isolated dependency (P7)
    load_m1_m7_contracts = None  # type: ignore[assignment,misc]
    _M1M7_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _M1M7_AVAILABLE, reason="langgraph backend not installed (optional isolated dependency)"
)

from tools.node_architect.agent_runtime_entrypoint import _run_selected_m1_m7_workflow

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "hermes/SCRUM-841-m1-m7-langgraph-r1"


def test_default_cli_manifest_has_no_workflow_selection(tmp_path: Path):
    from tools.node_architect.agent_runtime_cli import _load_manifest, _prepare_event

    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"provider_name": "p", "event": {"event_id": "e1"}}), encoding="utf-8")
    manifest = _load_manifest(path)
    event = _prepare_event(manifest, type("Provider", (), {"name": "p"})())
    assert "m1_m7_workflow_selection" not in event


def test_cli_rejects_selection_inside_event_payload(tmp_path: Path):
    from tools.node_architect.agent_runtime_cli import AgentRuntimeCliError, _load_manifest

    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {"provider_name": "p", "event": {"event_id": "e1", "m1_m7_workflow_selection": {"workflow_id": "scrum841-m1-m7-agent-workflow-r1"}}}
        ),
        encoding="utf-8",
    )
    try:
        _load_manifest(path)
    except AgentRuntimeCliError as exc:
        assert "AGENT_RUNTIME_WORKFLOW_SELECTION_INJECTION" in str(exc)
    else:
        raise AssertionError("workflow selection injection inside event must be rejected")


def test_manifest_profile_rejects_q0_reuse_and_binds_generic_authority():
    manifest, profile = load_m1_m7_contracts(ROOT)
    assert profile["q0_authority_reused"] is False
    assert profile["q0_runtime_plan_reused"] is False
    assert profile["q0_qualification_profile_reused"] is False
    assert profile["global_dependency_change"] is False
    assert profile["external_effects_by_graph"] is False
    assert profile["checkpoint_io_by_graph"] is False
    assert manifest["graph_performs_external_io"] is False
    assert manifest["graph_grants_authority"] is False
    assert manifest["graph_settles_native_loop"] is False
    assert manifest["max_children"] == 0
    assert manifest["max_parallel"] == 1
    assert profile["working_branch"] == BRANCH


def test_invalid_selection_fails_closed_before_graph_execution():
    out = _run_selected_m1_m7_workflow(
        selection={"workflow_id": "unknown"},
        canonical_state={},
        current_binding={},
        root=ROOT,
    )
    assert out["outcome"] == "BLOCKED"
    assert out["reason_code"] == "WORKFLOW_SELECTION_INVALID"
    assert out["executed_effects"] == []
    assert out["authority_granted"] is False