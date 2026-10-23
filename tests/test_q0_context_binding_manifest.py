"""Regression coverage for source-bound Q0 context history and head deltas."""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import subprocess

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


def test_context_manifest_round_trip_is_digest_stable(tmp_path):
    from tools.node_architect.task_context_binding import (
        build_context_manifest, digest, load_context_manifests, seal_context_manifest,
    )

    value = _context(tmp_path)
    manifest = build_context_manifest(value)
    manifest_digest = seal_context_manifest(value["workflow"]["checkpoint_ref"], manifest)
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
    before = _file_sha(__import__("pathlib").Path(checkpoint))
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
    assert _file_sha(__import__("pathlib").Path(checkpoint)) == before


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
    checkpoint = __import__("pathlib").Path(old["workflow"]["checkpoint_ref"])
    before = _file_sha(checkpoint)
    result = reconcile_engineering_source_head(old, new, repository_root=tmp_path,
                                               reason="fixture", dry_run=True)
    assert result["dry_run"] is True
    assert result["would_apply"]["new_context_digest"]
    assert result["receipt"]["old_head"] == old["repository"]["head_sha"]
    assert _file_sha(checkpoint) == before


def test_head_reconcile_still_rejects_non_head_drift(tmp_path):
    from tools.node_architect.engineering_m1_m7_workflow import reconcile_engineering_source_head

    old = _context(tmp_path)
    _repository(tmp_path, old)
    new = copy.deepcopy(old)
    new["engineering"]["work_items"][0]["input_digest"] = "sha256:" + "d" * 64
    with pytest.raises(ValueError, match="ENGINEERING_RECONCILE_NON_HEAD_DRIFT"):
        reconcile_engineering_source_head(old, new, repository_root=tmp_path, reason="fixture")
