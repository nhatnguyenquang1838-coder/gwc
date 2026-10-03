"""The production CLI fails closed when a V2 assignment is absent or invalid."""
from __future__ import annotations

import json
from pathlib import Path

from tools.node_architect import agent_runtime_cli


def _write_manifest(path: Path, *, universal_run=None):
    payload = {
        "provider_name": "q0-test-provider",
        "event": {"task_id": "SCRUM-781", "event_id": "q0-cli-test"},
    }
    if universal_run is not None:
        payload["universal_run"] = universal_run
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cli_rejects_manifest_without_v2_assignment_and_never_falls_back(tmp_path, capsys):
    manifest = _write_manifest(tmp_path / "legacy-shaped.json")

    exit_code = agent_runtime_cli.main(["--manifest", str(manifest)])
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "GWC_RUNTIME_DEFECT"
    assert result["runtime_family"] == "UNIVERSAL_V2"
    assert result["legacy_fallback"] is False
    assert result["authority_granted"] is False
    assert result["executed_effects"] == []


def test_cli_requires_provider_for_valid_v2_assignment(tmp_path, capsys):
    manifest = _write_manifest(tmp_path / "v2-assignment.json", universal_run={})

    exit_code = agent_runtime_cli.main(["--manifest", str(manifest)])
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "GWC_RUNTIME_DEFECT"
    assert result["legacy_fallback"] is False
    assert result["authority_granted"] is False
    assert result["executed_effects"] == []
