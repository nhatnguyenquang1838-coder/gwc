"""Regression coverage for source-bound Q0 context history and head deltas."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from test_task_context_binding import context


def _context(tmp_path, *, task="TASK-MANIFEST"):
    value = context(task)
    value["workflow"]["checkpoint_ref"] = str(tmp_path / "checkpoint.sqlite")
    value["workflow"]["mode"] = "Q0_ENGINEERING_COORDINATION"
    value["repository"]["branch"] = "fix/context-manifest"
    value["repository"]["worktree"] = str(tmp_path)
    value["runtime_plan"] = {"scope": {"allowed_actions": ["run_sandboxed_validation"]}}
    value["engineering"] = {
        "route_policy_ref": "route.json",
        "route_policy_digest": "sha256:" + "b" * 64,
        "work_items": [{"id": "probe", "input_digest": "sha256:" + "c" * 64}],
    }
    return value


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _repository(tmp_path, value):
    (tmp_path / "source.txt").write_text("base\n")
    _git(tmp_path, "init", "-b", value["repository"]["branch"])
    _git(tmp_path, "add", ".")
    _git(tmp_path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "-m", "base")
    value["repository"]["head_sha"] = _git(tmp_path, "rev-parse", "HEAD")


def _file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tables(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()


def test_context_manifest_round_trip_is_digest_stable(tmp_path):
    from tools.node_architect.task_context_binding import (
        build_context_manifest, digest, load_context_manifests, seal_context_manifest,
    )

    value = _context(tmp_path)
    manifest = build_context_manifest(value)
    manifest_digest = seal_context_manifest(value["workflow"]["checkpoint_ref"], manifest,
                                            authorized=True)
    row, = load_context_manifests(value["workflow"]["checkpoint_ref"], value["run"]["id"])
    assert row["manifest_digest"] == manifest_digest == digest(manifest)
    assert json.loads(row["manifest"]) == manifest
    assert manifest["context_digest"] == digest(value)
    assert manifest["previous_context_digest"] is None
    assert {"head_sha", "branch", "worktree", "plan_ref", "plan_blob_sha256",
            "runtime_plan_digest", "route_policy_ref", "route_policy_digest",
            "conversation_url", "session_id", "checkpoint_ref", "workflow_epoch",
            "schema_version"} <= manifest.keys()


def test_context_delta_classifies_head_only_and_material_input_drift(tmp_path):
    from tools.node_architect.task_context_binding import classify_context_delta

    old = _context(tmp_path)
    _repository(tmp_path, old)
    _git(tmp_path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "--allow-empty", "-m", "advance")
    new = copy.deepcopy(old)
    new["repository"]["head_sha"] = _git(tmp_path, "rev-parse", "HEAD")
    result = classify_context_delta(old, new, repository_root=tmp_path)
    assert result["classification"] == "HEAD_ONLY_SAFE"
    assert result["changed_fields"] == ["repository.head_sha"]
    assert result["head_only"] is True

    changed = copy.deepcopy(new)
    changed["engineering"]["work_items"][0]["input_digest"] = "sha256:" + "d" * 64
    result = classify_context_delta(old, changed, repository_root=tmp_path)
    assert result["classification"] == "MATERIAL_DRIFT"
    assert result["head_only"] is False


def test_context_delta_plan_transition_and_session_rotation():
    from tools.node_architect.task_context_binding import classify_context_delta

    old = context()
    new = copy.deepcopy(old)
    new["run"]["runtime_plan_digest"] = "sha256:" + "d" * 64
    assert classify_context_delta(old, new)["classification"] == "PLAN_TRANSITION"

    new = copy.deepcopy(old)
    new["controller"]["conversation_url"] = "https://chatgpt.com/c/rotated"
    assert classify_context_delta(old, new)["classification"] == "SESSION_ROTATION"

    new = copy.deepcopy(old)
    new["engineering"] = {"approved_successor_g1": {"status": "PENDING"}}
    assert classify_context_delta(old, new)["classification"] == "ADDITIVE_ROUTE_METADATA"

    new = copy.deepcopy(old)
    new["repository"]["head_sha"] = "f" * 40
    assert classify_context_delta(old, new)["classification"] == "HEAD_ONLY_UNVERIFIED"
    assert classify_context_delta({}, new)["classification"] == "UNKNOWN"


def test_unprovable_historical_context_is_typed_and_read_only(tmp_path):
    from tools.node_architect.engineering_m1_m7_workflow import resolve_prior_context
    from tools.node_architect.task_context_binding import digest

    value = _context(tmp_path)
    checkpoint = value["workflow"]["checkpoint_ref"]
    stored = copy.deepcopy(value)
    stored["task"]["objective"] = "different historical binding"
    stored_digest = digest(stored)
    with sqlite3.connect(checkpoint) as db:
        db.execute("CREATE TABLE engineering_workflow (run TEXT PRIMARY KEY, context_digest TEXT, state TEXT)")
        db.execute("INSERT INTO engineering_workflow VALUES (?,?,?)", (value["run"]["id"], stored_digest, "{}"))
        db.execute("CREATE TABLE engineering_firing_telemetry (run TEXT, source_head TEXT)")
        db.execute("INSERT INTO engineering_firing_telemetry VALUES (?,?)", (value["run"]["id"], "e" * 40))
        db.execute("CREATE TABLE engineering_invocations (run TEXT, key TEXT, binding TEXT, result TEXT)")
        db.execute("INSERT INTO engineering_invocations VALUES (?,?,?,NULL)",
                    (value["run"]["id"], "attempt-1", stored_digest))
    before = _file_sha(Path(checkpoint))
    with pytest.raises(ValueError, match="HISTORICAL_CONTEXT_NOT_PROVABLE") as caught:
        resolve_prior_context(checkpoint, value["run"]["id"], candidate_old=value,
                              candidate_new=value)
    package = caught.value.recovery_package
    assert caught.value.error_code == "HISTORICAL_CONTEXT_NOT_PROVABLE"
    assert package["stored_context_digest"] == stored_digest
    assert package["telemetry_previous_head"] == "e" * 40
    assert package["current_head"] == value["repository"]["head_sha"]
    assert package["attempted_bindings"] == [{"key": "attempt-1", "result": None}]
    assert isinstance(package["sealed_manifest_digests"], list)
    assert package["suggested_actions"]
    assert _file_sha(Path(checkpoint)) == before


def test_head_reconcile_dry_run_is_byte_identical(tmp_path):
    from tools.node_architect.engineering_m1_m7_workflow import reconcile_engineering_source_head
    from tools.node_architect.task_m1_m7_runner import run_task_workflow

    old = _context(tmp_path)
    _repository(tmp_path, old)
    run_task_workflow(old, host_capabilities={}, invocation_key="seed")
    _git(tmp_path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "--allow-empty", "-m", "advance")
    new = copy.deepcopy(old)
    new["repository"]["head_sha"] = _git(tmp_path, "rev-parse", "HEAD")
    checkpoint = Path(old["workflow"]["checkpoint_ref"])
    isolated_dir = tmp_path / "isolated"
    isolated_dir.mkdir()
    target_copy = isolated_dir / "checkpoint.sqlite"
    shutil.copy2(checkpoint, target_copy)
    before = _file_sha(checkpoint)
    copy_before = _file_sha(target_copy)
    result = reconcile_engineering_source_head(old, new, repository_root=tmp_path,
                                               reason="fixture", dry_run=True,
                                               target_copy=str(target_copy))
    assert result["dry_run"] is True
    assert result["would_apply"]["new_context_digest"]
    assert result["receipt"]["old_head"] == old["repository"]["head_sha"]
    assert _file_sha(checkpoint) == before
    assert _file_sha(target_copy) != copy_before
    with sqlite3.connect(target_copy) as db:
        assert db.execute("SELECT context_digest FROM engineering_workflow WHERE run=?",
                          (old["run"]["id"],)).fetchone()[0] == result["would_apply"]["new_context_digest"]


def test_head_reconcile_still_rejects_non_head_drift(tmp_path):
    from tools.node_architect.engineering_m1_m7_workflow import reconcile_engineering_source_head

    old = _context(tmp_path)
    _repository(tmp_path, old)
    new = copy.deepcopy(old)
    new["engineering"]["work_items"][0]["input_digest"] = "sha256:" + "d" * 64
    with pytest.raises(ValueError, match="ENGINEERING_RECONCILE_NON_HEAD_DRIFT"):
        reconcile_engineering_source_head(old, new, repository_root=tmp_path, reason="fixture")


def _reconcile_fixture(tmp_path):
    from test_engineering_m1_m7_workflow import binding, capabilities
    from tools.node_architect.task_m1_m7_runner import run_task_workflow

    old = binding(tmp_path)
    old["repository"]["worktree"] = str(tmp_path)
    (tmp_path / "source").write_text("fixture\n")
    _git(tmp_path, "init", "-b", old["repository"]["branch"])
    _git(tmp_path, "add", ".")
    _git(tmp_path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "-m", "base")
    old["repository"]["head_sha"] = _git(tmp_path, "rev-parse", "HEAD")
    run_task_workflow(old, host_capabilities=capabilities(old, {"read": 0, "execute": 0}),
                      invocation_key="fence-fixture")
    _git(tmp_path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "--allow-empty", "-m", "advance")
    new = copy.deepcopy(old)
    new["repository"]["head_sha"] = _git(tmp_path, "rev-parse", "HEAD")
    return old, new


def test_unvalidated_manifest_seal_is_byte_identical(tmp_path):
    from tools.node_architect.task_context_binding import build_context_manifest, seal_context_manifest
    from test_engineering_m1_m7_workflow import binding

    checkpoint = tmp_path / "checkpoint.sqlite"
    with sqlite3.connect(checkpoint) as db:
        db.execute("CREATE TABLE sentinel(value TEXT)")
        db.execute("INSERT INTO sentinel VALUES ('unchanged')")
    before = _file_sha(checkpoint)
    with pytest.raises(ValueError, match="MANIFEST_SEAL_NOT_AUTHORIZED"):
        seal_context_manifest(checkpoint, build_context_manifest(binding(tmp_path)))
    assert _file_sha(checkpoint) == before
    assert _tables(checkpoint) == [("sentinel",)]


def test_dry_run_requires_isolated_copy(tmp_path):
    from tools.node_architect.engineering_m1_m7_workflow import reconcile_engineering_source_head

    old, new = _reconcile_fixture(tmp_path)
    with pytest.raises(ValueError, match="DRY_RUN_REQUIRES_ISOLATED_COPY"):
        reconcile_engineering_source_head(old, new, repository_root=tmp_path,
                                          reason="fixture", dry_run=True)


def test_dry_run_rejects_live_path_symlink_and_hardlink(tmp_path):
    from tools.node_architect.engineering_m1_m7_workflow import (
        assert_isolated_copy, reconcile_engineering_source_head,
    )

    old, new = _reconcile_fixture(tmp_path)
    live = old["workflow"]["checkpoint_ref"]
    with pytest.raises(ValueError, match="DRY_RUN_TARGET_IS_LIVE"):
        reconcile_engineering_source_head(old, new, repository_root=tmp_path,
                                          reason="fixture", dry_run=True, target_copy=live)

    symlink = tmp_path / "checkpoint-symlink.sqlite"
    symlink.symlink_to(live)
    with pytest.raises(ValueError, match="DRY_RUN_TARGET_SYMLINK"):
        assert_isolated_copy(live, symlink)

    hardlink = tmp_path / "checkpoint-hardlink.sqlite"
    os.link(live, hardlink)
    with pytest.raises(ValueError, match="DRY_RUN_TARGET_HARDLINK"):
        assert_isolated_copy(live, hardlink)


def test_dry_run_changes_only_a_genuine_isolated_copy(tmp_path):
    from tools.node_architect.engineering_m1_m7_workflow import reconcile_engineering_source_head

    old, new = _reconcile_fixture(tmp_path)
    live = old["workflow"]["checkpoint_ref"]
    isolated_dir = tmp_path / "isolated"
    isolated_dir.mkdir()
    target_copy = isolated_dir / "checkpoint.sqlite"
    shutil.copy2(live, target_copy)
    live_before = _file_sha(Path(live))
    copy_before = _file_sha(target_copy)

    result = reconcile_engineering_source_head(old, new, repository_root=tmp_path,
        reason="fixture", dry_run=True, target_copy=str(target_copy))

    assert result["dry_run"] is True
    assert result["would_apply"]["new_context_digest"]
    assert _file_sha(Path(live)) == live_before
    assert _file_sha(target_copy) != copy_before
    with sqlite3.connect(target_copy) as db:
        assert db.execute("SELECT context_digest FROM engineering_workflow WHERE run=?",
                          (old["run"]["id"],)).fetchone()[0] == result["would_apply"]["new_context_digest"]


@pytest.mark.parametrize(("kwargs", "code"), [
    ({"last_acked_seq": 3}, "FENCE_UNCONSUMED_CONTROLLER_COMMAND"),
    ({"approval_id": None}, "FENCE_APPROVAL_ID_REQUIRED"),
    ({"scope_hash": "sha256:" + "b" * 64}, "FENCE_SCOPE_PREFIX_MISMATCH"),
    ({"expires_at": "2020-01-01T00:00:00Z"}, "FENCE_APPROVAL_EXPIRED"),
])
def test_effect_fence_rejects_unapproved_or_stale_effect(kwargs, code):
    from tools.node_architect.engineering_m1_m7_workflow import assert_effect_fence

    values = {
        "read_latest_command": lambda: {"seq": 4}, "last_acked_seq": 4,
        "approval_id": "APPROVE_G2_SCRUM781_20261023",
        "scope_hash": "sha256:" + "a" * 64, "approved_scope_prefix": "sha256:" + "a" * 16,
        "expires_at": "2099-01-01T00:00:00Z", "now": "2026-10-23T00:00:00Z",
    }
    values.update(kwargs)
    with pytest.raises(ValueError, match=code):
        assert_effect_fence(**values)


def test_effect_fence_returns_typed_ok_result():
    from tools.node_architect.engineering_m1_m7_workflow import assert_effect_fence

    result = assert_effect_fence(
        read_latest_command=lambda: {"seq": 4}, last_acked_seq=4,
        approval_id="APPROVE_G2_SCRUM781_20261023", scope_hash="sha256:" + "a" * 64,
        approved_scope_prefix="sha256:" + "a" * 16,
        expires_at="2099-01-01T00:00:00Z", now="2026-10-23T00:00:00Z")
    assert result["ok"] is True
    assert result["approval_id"] == "APPROVE_G2_SCRUM781_20261023"


def test_non_dry_reconcile_runs_effect_fence_before_checkpoint_write(tmp_path):
    from tools.node_architect.engineering_m1_m7_workflow import reconcile_engineering_source_head

    old, new = _reconcile_fixture(tmp_path)
    checkpoint = Path(old["workflow"]["checkpoint_ref"])
    before = _file_sha(checkpoint)
    with pytest.raises(ValueError, match="FENCE_UNCONSUMED_CONTROLLER_COMMAND"):
        reconcile_engineering_source_head(
            old, new, repository_root=tmp_path, reason="fixture",
            read_latest_command=lambda: {"seq": 5}, last_acked_seq=4,
            approval_id="APPROVE_G2_SCRUM781_20261023",
            scope_hash="sha256:" + "a" * 64,
            approved_scope_prefix="sha256:" + "a" * 16,
            expires_at="2099-01-01T00:00:00Z", now="2026-10-23T00:00:00Z")
    assert _file_sha(checkpoint) == before


def test_head_reconcile_preserves_non_head_drift_guard(tmp_path):
    from tools.node_architect.engineering_m1_m7_workflow import reconcile_engineering_source_head

    old, new = _reconcile_fixture(tmp_path)
    new["engineering"]["work_items"][0]["input_digest"] = "sha256:" + "d" * 64
    with pytest.raises(ValueError, match="ENGINEERING_RECONCILE_NON_HEAD_DRIFT"):
        reconcile_engineering_source_head(old, new, repository_root=tmp_path, reason="fixture")


def test_workflow_failed_preflight_does_not_create_or_mutate_checkpoint(tmp_path, monkeypatch):
    import argparse
    import scripts.scrum781_engineering_loop as loop

    checkpoint_root = tmp_path / "host"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_SESSION_ID", "fixture-session")
    monkeypatch.setattr(loop, "inspect", lambda args: {
        "outcome": "ENGINEERING_PREFLIGHT_BLOCKED", "reason_code": "fixture-blocked",
        "run_id": "fixture-run",
    })
    args = argparse.Namespace(session="fixture-session", tick=None, controller_url="https://chatgpt.com/c/fixture")
    before = sorted((str(path.relative_to(tmp_path)), _file_sha(path)) for path in tmp_path.rglob("*.sqlite"))
    with pytest.raises(ValueError, match="fixture-blocked"):
        loop.workflow(args, host_capabilities={})
    after = sorted((str(path.relative_to(tmp_path)), _file_sha(path)) for path in tmp_path.rglob("*.sqlite"))
    assert after == before
    assert not checkpoint_root.exists()


def test_context_drift_is_rejected_before_checkpoint_schema_or_rows_change(tmp_path):
    from test_engineering_m1_m7_workflow import binding, capabilities
    from tools.node_architect.task_m1_m7_runner import run_task_workflow

    context_value = binding(tmp_path)
    run_task_workflow(context_value,
                      host_capabilities=capabilities(context_value, {"read": 0, "execute": 0}),
                      invocation_key="drift-original")
    checkpoint = Path(context_value["workflow"]["checkpoint_ref"])
    before_sha, before_tables = _file_sha(checkpoint), _tables(checkpoint)
    drifted = copy.deepcopy(context_value)
    drifted["task"]["objective"] = "Changed binding that must not write"

    with pytest.raises(ValueError, match="ENGINEERING_CHECKPOINT_CONTEXT_DRIFT"):
        run_task_workflow(drifted,
            host_capabilities=capabilities(drifted, {"read": 0, "execute": 0}),
            invocation_key="drifted-call")

    assert _file_sha(checkpoint) == before_sha
    assert _tables(checkpoint) == before_tables
