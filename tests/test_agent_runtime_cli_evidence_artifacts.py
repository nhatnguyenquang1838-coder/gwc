"""Native CLI gate-evidence plumbing: the UR.G0 consumption regression.

Without ``--evidence-artifacts`` the CLI called
``UniversalController.consume_executor_receipt(receipt)`` with no evidence,
so every non-``UR.G2`` gate failed closed with ``Q0_GATE_EVIDENCE_REQUIRED``
and the native lane could never advance past UR.G0. These tests pin the
plumbing and its fail-closed negatives.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.node_architect import agent_runtime_cli as cli
from tools.node_architect.agent_runtime_cli import AgentRuntimeCliError, _load_evidence_artifacts


def test_missing_evidence_path_is_empty_mapping():
    assert _load_evidence_artifacts(None) == {}


def test_evidence_artifacts_round_trip(tmp_path: Path):
    payload = {"UNDERSTANDING_RECEIPT": {"receipt_digest": "sha256:" + "a" * 64}}
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert _load_evidence_artifacts(path) == payload


def test_evidence_artifacts_non_object_is_rejected(tmp_path: Path):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(AgentRuntimeCliError, match="evidence artifacts must be a JSON object"):
        _load_evidence_artifacts(path)


def test_evidence_artifacts_invalid_json_is_rejected(tmp_path: Path):
    path = tmp_path / "evidence.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(AgentRuntimeCliError, match="evidence artifacts file is not valid JSON"):
        _load_evidence_artifacts(path)


def test_cli_forwards_evidence_artifacts_to_controller_consumption(tmp_path: Path):
    """The regression: evidence must actually reach consume_executor_receipt."""
    from unittest import mock

    import tools.node_architect.universal_run_controller as urc
    import tools.node_architect.universal_run_execution as execution

    seen: dict[str, object] = {}

    class _Executor:
        def execute(self, **_kwargs):
            return {"host_status": "ACTION_COMPLETE", "receipt_digest": "r"}

    class _Controller:
        def assign_current_action(self):
            return {"actor": "EXECUTOR", "run_id": "unit-run"}

        def consume_executor_receipt(self, receipt, evidence_artifacts=None):
            seen["evidence_artifacts"] = evidence_artifacts
            return {"gate_advanced": True}

    class _Provider:
        name = "configured-provider"

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps({"UNDERSTANDING_RECEIPT": {"ref": "unit:understood"}}), encoding="utf-8")

    with mock.patch.object(execution, "UniversalExecutor", _Executor), \
            mock.patch.object(cli, "_load_factory", lambda _spec: (lambda: _Provider())), \
            mock.patch.object(cli, "_load_manifest", lambda _path: {
                "provider_name": "configured-provider",
                "event": {"event_id": "unit-event"},
                "universal_run": {"evidence_root": str(tmp_path / "evidence")},
            }), \
            mock.patch.object(cli, "_prepare_event", lambda _manifest, _provider: {"event_id": "unit-event"}), \
            mock.patch.object(urc.UniversalController, "from_manifest",
                              classmethod(lambda _cls, **_kwargs: _Controller())):
        rc = cli.main([
            "--manifest", str(manifest_path),
            "--provider-factory", "unused:factory",
            "--evidence-artifacts", str(evidence_path),
        ])

    assert rc == 0
    assert seen["evidence_artifacts"] == {"UNDERSTANDING_RECEIPT": {"ref": "unit:understood"}}


def test_cli_without_evidence_artifacts_forwards_empty_mapping(tmp_path: Path):
    """No flag => {} is passed, so non-UR.G2 gates still fail closed downstream."""
    from unittest import mock

    import tools.node_architect.universal_run_controller as urc
    import tools.node_architect.universal_run_execution as execution

    seen: dict[str, object] = {}

    class _Executor:
        def execute(self, **_kwargs):
            return {"host_status": "ACTION_COMPLETE", "receipt_digest": "r"}

    class _Controller:
        def assign_current_action(self):
            return {"actor": "EXECUTOR", "run_id": "unit-run"}

        def consume_executor_receipt(self, receipt, evidence_artifacts=None):
            seen["evidence_artifacts"] = evidence_artifacts
            return {"gate_advanced": False}

    class _Provider:
        name = "configured-provider"

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")

    with mock.patch.object(execution, "UniversalExecutor", _Executor), \
            mock.patch.object(cli, "_load_factory", lambda _spec: (lambda: _Provider())), \
            mock.patch.object(cli, "_load_manifest", lambda _path: {
                "provider_name": "configured-provider",
                "event": {"event_id": "unit-event"},
                "universal_run": {"evidence_root": str(tmp_path / "evidence")},
            }), \
            mock.patch.object(cli, "_prepare_event", lambda _manifest, _provider: {"event_id": "unit-event"}), \
            mock.patch.object(urc.UniversalController, "from_manifest",
                              classmethod(lambda _cls, **_kwargs: _Controller())):
        rc = cli.main(["--manifest", str(manifest_path), "--provider-factory", "unused:factory"])

    assert rc == 0
    assert seen["evidence_artifacts"] == {}
