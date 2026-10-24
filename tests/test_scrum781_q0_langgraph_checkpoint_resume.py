"""Persistent Q0 LangGraph checkpoint/resume parity (optional SQLite backend)."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pytest

from scripts.scrum781_q0_fixture_replay import (
    DEFAULT_FIXTURE,
    ROOT,
    RUN_ID,
    FixtureError,
    build_langgraph_graph,
    execute_replay,
    load_fixture,
    run_fixture,
    validate_fixture,
)

WORKER = ROOT / "tests/q0_langgraph_checkpoint_resume_worker.py"
PLAN_PATH = ROOT / "core/node-architect/scrum781-q0-fresh-execution-plan-r2.json"


def test_sqlite_resume_reinitializes_process_and_matches_native(tmp_path):
    pytest.importorskip("langgraph.checkpoint.sqlite")
    fixture, fixture_digest = load_fixture(DEFAULT_FIXTURE)
    validate_fixture(fixture, root=ROOT)
    assert fixture["fixture_id"] == "SCRUM-781-Q0-C91-E52-RECONSTRUCTED-V1"
    assert fixture["incident"]["provenance_class"] == "RECONSTRUCTED_SOURCE_BOUND"
    assert fixture["incident"]["original_trace_status"] == "MISSING"
    assert fixture["source_binding"]["runtimeplan_sha256"] == hashlib.sha256(
        PLAN_PATH.read_bytes()
    ).hexdigest()

    native = run_fixture(fixture, root=ROOT, engine="native")
    assert native["authentic_dwo_login_replay"] is False
    assert native["q0_l3_qualified"] is False
    assert native["native_gate_receipt"] is None

    checkpoint_path = tmp_path / "q0-langgraph-checkpoints.sqlite"
    effect_ledger_path = tmp_path / "q0-replay-invocation-ledger.sqlite"
    thread_id = f"{RUN_ID}:sqlite-resume:{fixture_digest.split(':', 1)[1][:16]}"
    phases = []
    for phase in ("pause", "resume", "terminal-noop"):
        command = [
            sys.executable,
            str(WORKER),
            phase,
            str(checkpoint_path),
            str(effect_ledger_path),
            thread_id,
            fixture_digest,
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, (
            f"worker phase={phase} failed: rc={result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        phases.append(json.loads(result.stdout))

    paused, resumed, terminal = phases
    assert paused["result"] == "CHECKPOINT_PAUSED_BEFORE_REPLAY"
    assert paused["pending_next"] == ["replay"]
    assert paused["validated"] is True
    assert paused["adapter_call_count"] == 0
    assert resumed["result"] == "PERSISTED_CHECKPOINT_RESUMED"
    assert resumed["thread_id"] == thread_id
    assert resumed["actual"] == native["observed"]
    assert resumed["verified"] is True
    assert resumed["adapter_call_count"] == 1
    assert resumed["authority_granted"] is not True
    assert not resumed["executed_effects"]
    assert terminal["result"] == "TERMINAL_CHECKPOINT_NOOP"
    assert terminal["next"] == []
    assert terminal["adapter_call_count"] == 1
    assert checkpoint_path.is_file() and checkpoint_path.stat().st_size > 0
    assert effect_ledger_path.is_file()

    evidence = {
        "result": "Q0_SQLITE_CHECKPOINT_RESUME_PARITY_PASS",
        "q0_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip(),
        "python": sys.version.split()[0],
        "langgraph": metadata.version("langgraph"),
        "langgraph_checkpoint_sqlite": metadata.version(
            "langgraph-checkpoint-sqlite"
        ),
        "fixture_id": fixture["fixture_id"],
        "fixture_digest": fixture_digest,
        "runtimeplan_sha256": fixture["source_binding"]["runtimeplan_sha256"],
        "checkpoint_namespace": "root (implicit empty checkpoint_ns)",
        "checkpoint_path": str(checkpoint_path),
        "effect_ledger_path": str(effect_ledger_path),
        "process_phases": phases,
        "native_gate_receipt": native["native_gate_receipt"],
        "authentic_dwo_login_replay": native["authentic_dwo_login_replay"],
        "q0_l3_qualified": native["q0_l3_qualified"],
        "external_effects": [],
    }
    print("Q0_SQLITE_CHECKPOINT_RESUME=" + json.dumps(evidence, sort_keys=True))


def test_langgraph_rejects_runtimeplan_digest_drift_before_replay():
    memory = pytest.importorskip("langgraph.checkpoint.memory")
    fixture, _ = load_fixture(DEFAULT_FIXTURE)
    tampered = copy.deepcopy(fixture)
    tampered["source_binding"]["runtimeplan_sha256"] = "0" * 64
    adapter_calls = []

    def should_not_run(**kwargs):
        adapter_calls.append(kwargs)
        return execute_replay(fixture)

    graph = build_langgraph_graph(
        tampered,
        root=ROOT,
        executor=should_not_run,
        checkpointer=memory.MemorySaver(),
    )
    with pytest.raises(FixtureError, match="PLAN_DRIFT"):
        graph.invoke({}, {"configurable": {"thread_id": RUN_ID + ":digest-negative"}})
    assert adapter_calls == []


def test_langgraph_rejects_provenance_upgrade_before_replay():
    memory = pytest.importorskip("langgraph.checkpoint.memory")
    fixture, _ = load_fixture(DEFAULT_FIXTURE)
    tampered = copy.deepcopy(fixture)
    tampered["incident"]["provenance_class"] = "ORIGINAL_RECOVERED"
    adapter_calls = []

    def should_not_run(**kwargs):
        adapter_calls.append(kwargs)
        return execute_replay(fixture)

    graph = build_langgraph_graph(
        tampered,
        root=ROOT,
        executor=should_not_run,
        checkpointer=memory.MemorySaver(),
    )
    with pytest.raises(FixtureError, match="PROVENANCE_INVALID"):
        graph.invoke({}, {"configurable": {"thread_id": RUN_ID + ":provenance-negative"}})
    assert adapter_calls == []
