"""First-run activation for a DISTINCT child run (Controller COMMAND #89 / B2).

A same-run successor transition (`reconcile_engineering_plan_transition`) cannot
bootstrap a new child: it requires an existing workflow row for the same run.
This module owns the smallest separate path:

  verify parent terminal binding + approved plan digest + exact repo
  HEAD/branch/worktree + unique checkpoint identity, then atomically write the
  child's activation generation/receipt and return the durable receipt.

It never copies the parent's terminal flag, verified work or authority, and it
grants no native runtime effect authority, typed C/E or gate receipt.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

SCHEMA_ID = "gwc.q0.first-run-activation/v1"


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=30)
    db.execute(
        "CREATE TABLE IF NOT EXISTS engineering_plan_activation "
        "(plan_ref TEXT PRIMARY KEY, plan_digest TEXT, context_digest TEXT, "
        "generation INTEGER, activated_at TEXT)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS engineering_first_run_activation "
        "(run_id TEXT PRIMARY KEY, parent_run_ref TEXT, plan_ref TEXT, plan_digest TEXT, "
        "context_digest TEXT, head_sha TEXT, branch TEXT, receipt_digest TEXT, activated_at TEXT)"
    )
    return db


def verify_first_run_binding(
    *,
    repository_root: Path | str,
    plan_ref: str,
    run_id: str,
    parent_run_ref: str,
    branch: str,
    head_sha: str,
    parent_terminal_ref: str,
) -> dict:
    """Read-only verification of the binding. Raises on any mismatch."""
    root = Path(repository_root).resolve()
    plan_path = (root / plan_ref).resolve()
    _require(plan_path.is_file(), "FIRST_RUN_PLAN_MISSING")
    _require(str(plan_path).startswith(str(root)), "FIRST_RUN_PLAN_PATH_ESCAPE")
    plan = json.loads(plan_path.read_text())

    _require(plan.get("run_id") == run_id, "FIRST_RUN_PLAN_RUN_MISMATCH")
    _require(plan.get("branch") == branch, "FIRST_RUN_PLAN_BRANCH_MISMATCH")
    _require(plan.get("parent_run_ref") == parent_run_ref, "FIRST_RUN_PARENT_REF_MISMATCH")

    terminal_path = (root / parent_terminal_ref).resolve()
    _require(terminal_path.is_file(), "FIRST_RUN_PARENT_TERMINAL_MISSING")
    terminal = json.loads(terminal_path.read_text())
    _require(terminal.get("run_id") == parent_run_ref, "FIRST_RUN_PARENT_TERMINAL_MISMATCH")

    _require(_git(root, "rev-parse", "HEAD") == head_sha, "FIRST_RUN_SOURCE_HEAD_DRIFT")
    _require(_git(root, "rev-parse", "--abbrev-ref", "HEAD") == branch, "FIRST_RUN_BRANCH_DRIFT")
    _require(bool(plan.get("scope")) and bool(plan.get("recursive_plan")), "FIRST_RUN_PLAN_INVALID")

    return {
        "plan": plan,
        "plan_digest": _sha256_file(plan_path),
        "parent_terminal_digest": _sha256_file(terminal_path),
    }


def activate_first_run_child(
    *,
    repository_root: Path | str,
    plan_ref: str,
    receipt_ref: str,
    checkpoint_ref: Path | str,
    run_id: str,
    parent_run_ref: str,
    branch: str,
    head_sha: str,
    parent_terminal_ref: str,
    authority_ref: str,
    reason: str,
) -> dict:
    """Atomically bind a distinct child run. Idempotent for an identical request."""
    _require(isinstance(reason, str) and bool(reason.strip()), "FIRST_RUN_REASON_REQUIRED")
    _require(isinstance(authority_ref, str) and bool(authority_ref.strip()), "FIRST_RUN_AUTHORITY_REQUIRED")
    root = Path(repository_root).resolve()
    verified = verify_first_run_binding(
        repository_root=root,
        plan_ref=plan_ref,
        run_id=run_id,
        parent_run_ref=parent_run_ref,
        branch=branch,
        head_sha=head_sha,
        parent_terminal_ref=parent_terminal_ref,
    )
    plan_digest = verified["plan_digest"]
    binding = {
        "schema_id": SCHEMA_ID,
        "run_id": run_id,
        "parent_run_ref": parent_run_ref,
        "plan_ref": plan_ref,
        "plan_digest": plan_digest,
        "branch": branch,
        "head_sha": head_sha,
        "parent_terminal_ref": parent_terminal_ref,
        "parent_terminal_digest": verified["parent_terminal_digest"],
        "authority_ref": authority_ref,
        "reason": reason,
    }
    context_digest = _digest(binding)
    checkpoint = Path(checkpoint_ref).resolve()

    existing = None
    if checkpoint.is_file():
        with sqlite3.connect(checkpoint.as_uri() + "?mode=ro", uri=True) as ro:
            tables = {r[0] for r in ro.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "engineering_first_run_activation" in tables:
                existing = ro.execute(
                    "SELECT plan_digest, context_digest, receipt_digest FROM engineering_first_run_activation "
                    "WHERE run_id=?",
                    (run_id,),
                ).fetchone()
            foreign = False
            if "engineering_workflow" in tables:
                foreign = ro.execute(
                    "SELECT 1 FROM engineering_workflow WHERE run<>?", (run_id,)
                ).fetchone() is not None
            _require(not foreign, "FIRST_RUN_CHECKPOINT_FOREIGN_RUN")

    if existing is not None:
        _require(existing[0] == plan_digest, "FIRST_RUN_EXISTING_DIGEST_MISMATCH")
        _require(existing[1] == context_digest, "FIRST_RUN_EXISTING_BINDING_MISMATCH")
        receipt_path = (root / receipt_ref).resolve()
        _require(receipt_path.is_file(), "FIRST_RUN_RECEIPT_MISSING")
        receipt = json.loads(receipt_path.read_text())
        _require(receipt.get("receipt_digest") == existing[2], "FIRST_RUN_RECEIPT_DIGEST_MISMATCH")
        return {**receipt, "idempotent_replay": True}

    activated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with _connect(checkpoint) as db:
        db.execute("BEGIN IMMEDIATE")
        generation = db.execute(
            "SELECT COALESCE(MAX(generation),0)+1 FROM engineering_plan_activation"
        ).fetchone()[0]
        db.execute(
            "INSERT OR REPLACE INTO engineering_plan_activation VALUES (?,?,?,?,?)",
            (plan_ref, plan_digest, context_digest, generation, activated_at),
        )
        receipt_body = {
            **binding,
            "checkpoint_ref": str(checkpoint),
            "activation_generation": generation,
            "activated_at": activated_at,
            "authority_granted": False,
            "typed_ce_admitted": False,
            "native_runtime_activation": False,
            "claim_boundary": (
                "child first-run plan activation only; no native LOAD_PROOF, L3, "
                "typed C/E admission or gate receipt"
            ),
        }
        receipt_digest = _digest(receipt_body)
        db.execute(
            "INSERT INTO engineering_first_run_activation VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, parent_run_ref, plan_ref, plan_digest, context_digest, head_sha, branch,
             receipt_digest, activated_at),
        )
        db.commit()

    receipt = {**receipt_body, "receipt_digest": receipt_digest}
    receipt_path = (root / receipt_ref).resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n")

    with sqlite3.connect(checkpoint.as_uri() + "?mode=ro", uri=True) as ro:
        row = ro.execute(
            "SELECT f.plan_digest, f.receipt_digest, p.generation "
            "FROM engineering_first_run_activation f "
            "JOIN engineering_plan_activation p ON p.plan_ref = f.plan_ref "
            "WHERE f.run_id=?",
            (run_id,),
        ).fetchone()
    _require(row is not None and row[0] == plan_digest and row[1] == receipt_digest,
             "FIRST_RUN_READBACK_FAILED")
    return {**receipt, "idempotent_replay": False}


def verify_first_run_receipt(*, repository_root: Path | str, receipt_ref: str, checkpoint_ref: Path | str) -> dict:
    """Fail-closed verification used by plan resolution."""
    root = Path(repository_root).resolve()
    receipt_path = (root / receipt_ref).resolve()
    _require(receipt_path.is_file(), "FIRST_RUN_RECEIPT_MISSING")
    receipt = json.loads(receipt_path.read_text())
    _require(receipt.get("schema_id") == SCHEMA_ID, "FIRST_RUN_RECEIPT_SCHEMA_INVALID")
    plan_path = (root / receipt["plan_ref"]).resolve()
    _require(plan_path.is_file(), "FIRST_RUN_PLAN_MISSING")
    _require(_sha256_file(plan_path) == receipt.get("plan_digest"), "FIRST_RUN_PLAN_DIGEST_DRIFT")
    checkpoint = Path(checkpoint_ref).resolve()
    _require(checkpoint.is_file(), "FIRST_RUN_CHECKPOINT_MISSING")
    with sqlite3.connect(checkpoint.as_uri() + "?mode=ro", uri=True) as ro:
        tables = {r[0] for r in ro.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        _require("engineering_first_run_activation" in tables, "FIRST_RUN_ACTIVATION_ROW_MISSING")
        row = ro.execute(
            "SELECT plan_digest, receipt_digest FROM engineering_first_run_activation WHERE run_id=?",
            (receipt["run_id"],),
        ).fetchone()
    _require(row is not None, "FIRST_RUN_ACTIVATION_ROW_MISSING")
    _require(row[0] == receipt["plan_digest"], "FIRST_RUN_PLAN_DIGEST_DRIFT")
    _require(row[1] == receipt["receipt_digest"], "FIRST_RUN_RECEIPT_DIGEST_MISMATCH")
    return receipt
