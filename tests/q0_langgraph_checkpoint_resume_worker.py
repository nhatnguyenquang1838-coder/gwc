#!/usr/bin/env python3
"""Test-only worker for Q0 persisted LangGraph checkpoint/resume regression."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from scripts.scrum781_q0_fixture_replay import (
    DEFAULT_FIXTURE,
    RUN_ID,
    build_langgraph_graph,
    load_fixture,
    validate_fixture,
)
from tools.node_architect.universal_run_epoch import replay_c91_incident

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = ""  # LangGraph root namespace; non-empty values resolve subgraph paths.


def _effect_count(path: Path, effect_id: str) -> int:
    if not path.exists():
        return 0
    with sqlite3.connect(str(path)) as connection:
        row = connection.execute(
            "SELECT calls FROM replay_invocations WHERE effect_id = ?", (effect_id,)
        ).fetchone()
    return 0 if row is None else int(row[0])


def _tracked_executor(path: Path, effect_id: str):
    def execute(**kwargs: Any) -> dict:
        with sqlite3.connect(str(path)) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS replay_invocations "
                "(effect_id TEXT PRIMARY KEY, calls INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT INTO replay_invocations(effect_id, calls) VALUES (?, 1) "
                "ON CONFLICT(effect_id) DO UPDATE SET calls = calls + 1",
                (effect_id,),
            )
            connection.commit()
        return replay_c91_incident(**kwargs)

    return execute


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        raise SystemExit(
            "usage: worker.py <pause|resume|terminal-noop> "
            "<checkpoint.sqlite> <invocations.sqlite> <thread_id> <fixture_digest>"
        )
    phase, checkpoint_raw, effects_raw, thread_id, expected_digest = argv
    checkpoint_path = Path(checkpoint_raw)
    effect_path = Path(effects_raw)
    fixture, fixture_digest = load_fixture(DEFAULT_FIXTURE)
    if fixture_digest != expected_digest:
        raise ValueError("Q0_FIXTURE_DIGEST_CHANGED")
    validate_fixture(fixture, root=ROOT)
    effect_id = "execute-replay:" + fixture_digest
    connection = sqlite3.connect(str(checkpoint_path), check_same_thread=False)
    try:
        checkpointer = SqliteSaver(connection)
        checkpointer.setup()
        graph = build_langgraph_graph(
            fixture,
            root=ROOT,
            executor=_tracked_executor(effect_path, effect_id),
            checkpointer=checkpointer,
            interrupt_before=["replay"],
        )
        config = {
            "configurable": {"thread_id": thread_id, "checkpoint_ns": NAMESPACE}
        }
        if phase == "pause":
            graph.invoke({}, config)
            snapshot = graph.get_state(config)
            assert snapshot.values.get("validated") is True
            assert "actual" not in snapshot.values
            assert snapshot.next == ("replay",), snapshot.next
            calls = _effect_count(effect_path, effect_id)
            assert calls == 0, calls
            result = {
                "result": "CHECKPOINT_PAUSED_BEFORE_REPLAY",
                "pending_next": list(snapshot.next),
                "validated": snapshot.values.get("validated"),
                "adapter_call_count": calls,
                "checkpoint_id": snapshot.config["configurable"].get("checkpoint_id"),
            }
        elif phase == "resume":
            pending = graph.get_state(config)
            assert pending.values.get("validated") is True
            assert "actual" not in pending.values
            assert pending.next == ("replay",), pending.next
            graph.invoke(None, config)
            snapshot = graph.get_state(config)
            actual = snapshot.values.get("actual")
            assert snapshot.values.get("verified") is True
            assert snapshot.next == (), snapshot.next
            assert actual is not None
            assert actual.get("authority_granted") is not True
            assert not actual.get("executed_effects")
            calls = _effect_count(effect_path, effect_id)
            assert calls == 1, calls
            result = {
                "result": "PERSISTED_CHECKPOINT_RESUMED",
                "thread_id": snapshot.config["configurable"]["thread_id"],
                "checkpoint_ns": snapshot.config["configurable"].get("checkpoint_ns"),
                "checkpoint_id": snapshot.config["configurable"].get("checkpoint_id"),
                "actual": actual,
                "verified": snapshot.values.get("verified"),
                "authority_granted": actual.get("authority_granted"),
                "executed_effects": actual.get("executed_effects"),
                "adapter_call_count": calls,
            }
        elif phase == "terminal-noop":
            before = graph.get_state(config)
            assert before.values.get("verified") is True
            assert before.next == (), before.next
            graph.invoke(None, config)
            after = graph.get_state(config)
            calls = _effect_count(effect_path, effect_id)
            assert after.values.get("actual") == before.values.get("actual")
            assert after.next == (), after.next
            assert calls == 1, calls
            result = {
                "result": "TERMINAL_CHECKPOINT_NOOP",
                "next": list(after.next),
                "adapter_call_count": calls,
                "checkpoint_id": after.config["configurable"].get("checkpoint_id"),
            }
        else:
            raise ValueError("Q0_LANGGRAPH_WORKER_PHASE_INVALID")
    finally:
        connection.close()
    result.update({
        "phase": phase,
        "run_id": RUN_ID,
        "fixture_id": fixture["fixture_id"],
        "fixture_digest": fixture_digest,
        "runtimeplan_sha256": fixture["source_binding"]["runtimeplan_sha256"],
        "thread_id": thread_id,
        "checkpoint_namespace": NAMESPACE,
        "checkpoint_path": str(checkpoint_path),
        "effect_ledger_path": str(effect_path),
        "python": sys.version.split()[0],
        "langgraph": metadata.version("langgraph"),
        "langgraph_checkpoint_sqlite": metadata.version("langgraph-checkpoint-sqlite"),
        "branch": _git("branch", "--show-current"),
        "q0_head": _git("rev-parse", "HEAD"),
        "native_gate_receipt": None,
        "q0_l3_qualified": False,
        "authentic_dwo_login_replay": False,
    })
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
