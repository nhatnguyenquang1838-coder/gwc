from __future__ import annotations

import pytest

from tools.node_architect.universal_run_execution import UniversalExecutor, UniversalRunExecutionError


def test_v2_executor_rejects_legacy_assignment_schema_without_writing_receipt(tmp_path):
    evidence_root = tmp_path / "evidence"
    assignment = {
        "schema_id": "gwc.universal-run.executor-assignment",
        "schema_version": 1,
        "gate": "G2",
    }

    with pytest.raises(UniversalRunExecutionError) as caught:
        UniversalExecutor().execute(
            assignment=assignment,
            provider=object(),
            event={},
            evidence_root=evidence_root,
        )

    assert caught.value.code == "EXECUTOR_ASSIGNMENT_SCHEMA_MISMATCH"
    assert not evidence_root.exists()
