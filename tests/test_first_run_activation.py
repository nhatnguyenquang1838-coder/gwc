"""First-run activation for a distinct child run (Controller COMMAND #89 / B2)."""
from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from tools.node_architect import first_run_activation as fra

PLAN_REF = "core/plan-r1.json"
RECEIPT_REF = ".gwc/tasks/SCRUM-781/activation/child-activation-r1.json"
PARENT_TERMINAL = ".gwc/tasks/SCRUM-781/evidence/parent.json"
RUN_ID = "scrum781-q0-cf-load-r1"
PARENT = "scrum781-q0-fresh-20261010-r1"
BRANCH = "fix/test-child"


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture()
def repo(tmp_path: Path) -> dict:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    plan = {
        "run_id": RUN_ID,
        "parent_run_ref": PARENT,
        "branch": BRANCH,
        "scope": {"allowed_actions": ["run_sandboxed_validation"]},
        "recursive_plan": {"id": "F0", "children": []},
    }
    (root / "core").mkdir()
    (root / PLAN_REF).write_text(json.dumps(plan))
    (root / ".gwc/tasks/SCRUM-781/evidence").mkdir(parents=True)
    (root / PARENT_TERMINAL).write_text(json.dumps({"run_id": PARENT, "claim_boundary": "terminal"}))
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    _git(root, "checkout", "-qb", BRANCH)
    head = _git(root, "rev-parse", "HEAD")
    return {"root": root, "head": head, "checkpoint": tmp_path / "cp" / "checkpoint.sqlite"}


def _activate(repo: dict, **overrides):
    kwargs = dict(
        repository_root=repo["root"],
        plan_ref=PLAN_REF,
        receipt_ref=RECEIPT_REF,
        checkpoint_ref=repo["checkpoint"],
        run_id=RUN_ID,
        parent_run_ref=PARENT,
        branch=BRANCH,
        head_sha=repo["head"],
        parent_terminal_ref=PARENT_TERMINAL,
        authority_ref="github://issue/595#comment-1",
        reason="B2 child bootstrap test",
    )
    kwargs.update(overrides)
    return fra.activate_first_run_child(**kwargs)


def test_activation_binds_child_and_is_idempotent(repo: dict) -> None:
    receipt = _activate(repo)
    assert receipt["run_id"] == RUN_ID
    assert receipt["authority_granted"] is False
    assert receipt["native_runtime_activation"] is False
    assert receipt["idempotent_replay"] is False
    assert (repo["root"] / RECEIPT_REF).is_file()
    again = _activate(repo)
    assert again["idempotent_replay"] is True
    assert again["receipt_digest"] == receipt["receipt_digest"]
    with sqlite3.connect(repo["checkpoint"]) as db:
        assert db.execute(
            "SELECT generation FROM engineering_plan_activation WHERE plan_ref=?", (PLAN_REF,)
        ).fetchone()[0] == 1


def test_wrong_branch_fails_closed(repo: dict) -> None:
    with pytest.raises(ValueError, match="FIRST_RUN_PLAN_BRANCH_MISMATCH"):
        _activate(repo, branch="fix/other")


def test_run_mismatch_fails_closed(repo: dict) -> None:
    with pytest.raises(ValueError, match="FIRST_RUN_PLAN_RUN_MISMATCH"):
        _activate(repo, run_id="other-run")


def test_missing_parent_terminal_fails_closed(repo: dict) -> None:
    with pytest.raises(ValueError, match="FIRST_RUN_PARENT_TERMINAL_MISSING"):
        _activate(repo, parent_terminal_ref=".gwc/missing.json")


def test_stale_head_fails_closed(repo: dict) -> None:
    with pytest.raises(ValueError, match="FIRST_RUN_SOURCE_HEAD_DRIFT"):
        _activate(repo, head_sha="0" * 40)


def test_foreign_checkpoint_fails_closed(repo: dict) -> None:
    repo["checkpoint"].parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(repo["checkpoint"]) as db:
        db.execute(
            "CREATE TABLE engineering_workflow (run TEXT PRIMARY KEY, context_digest TEXT, state TEXT)"
        )
        db.execute("INSERT INTO engineering_workflow VALUES ('other-run','x','{}')")
    with pytest.raises(ValueError, match="FIRST_RUN_CHECKPOINT_FOREIGN_RUN"):
        _activate(repo)


def test_plan_digest_drift_after_activation_fails_closed(repo: dict) -> None:
    receipt = _activate(repo)
    plan_path = repo["root"] / PLAN_REF
    data = json.loads(plan_path.read_text())
    data["goal"] = "mutated"
    plan_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="FIRST_RUN_PLAN_DIGEST_DRIFT"):
        fra.verify_first_run_receipt(
            repository_root=repo["root"],
            receipt_ref=RECEIPT_REF,
            checkpoint_ref=repo["checkpoint"],
        )
