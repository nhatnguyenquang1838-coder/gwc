#!/usr/bin/env python3
"""Resolve connector-provided G5 candidates into exact-SHA status evidence.

This tool intentionally performs no connector calls. The caller supplies the
observed candidates and discovery trace; the resolver rejects stale or
unrelated runs and produces a deterministic, fail-closed evidence packet.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import yaml


PENDING = {"queued", "waiting", "requested", "in_progress"}
FAILURE = {"failure", "cancelled", "timed_out", "action_required"}


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle) if path.suffix.lower() == ".json" else yaml.safe_load(handle)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _workflow_names(value: Any) -> list[str]:
    names: list[str] = []
    for item in value or []:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return list(dict.fromkeys(names))


def resolve(payload: dict[str, Any]) -> dict[str, Any]:
    merge_sha = payload.get("merge_commit_sha")
    required = _workflow_names(payload.get("required_workflows"))
    candidates = payload.get("candidates", payload.get("runs", []))
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")
    if not isinstance(merge_sha, str) or len(merge_sha) != 40 or any(ch not in "0123456789abcdef" for ch in merge_sha):
        raise ValueError("merge_commit_sha must be a 40-character lowercase SHA")
    if not required:
        raise ValueError("required_workflows must contain at least one workflow")

    discovery = payload.get("discovery", {})
    if not isinstance(discovery, dict):
        raise ValueError("discovery must be an object")
    discovery = {
        "method": discovery.get("method", "exact_push_lookup"),
        "exact_sha_lookup_attempted": bool(discovery.get("exact_sha_lookup_attempted", True)),
        "fallbacks_attempted": list(discovery.get("fallbacks_attempted", [])),
    }
    if discovery.get("connector_limitations"):
        discovery["connector_limitations"] = list(discovery["connector_limitations"])

    rejected: list[dict[str, Any]] = []
    selected_by_workflow: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("each candidate must be an object")
        workflow = candidate.get("workflow")
        if workflow not in required:
            rejected.append({"run_id": candidate.get("run_id"), "head_sha": candidate.get("head_sha", ""), "reason": "not_required_workflow"})
            continue
        if candidate.get("head_sha") != merge_sha:
            rejected.append({"run_id": candidate.get("run_id"), "head_sha": candidate.get("head_sha", ""), "reason": "sha_mismatch"})
            continue
        current = selected_by_workflow.get(workflow)
        rank = (int(candidate.get("run_attempt", 0)), int(candidate.get("run_id", 0)))
        if current is not None:
            current_rank = (int(current.get("run_attempt", 0)), int(current.get("run_id", 0)))
            if rank <= current_rank:
                rejected.append({"run_id": candidate.get("run_id"), "head_sha": merge_sha, "reason": "stale_attempt"})
                continue
        selected_by_workflow[workflow] = candidate

    selected = [selected_by_workflow[name] for name in required if name in selected_by_workflow]
    selected.sort(key=lambda item: (required.index(item["workflow"]), item["run_attempt"], item["run_id"]))
    conclusions = {item.get("conclusion") for item in selected}
    statuses = {item.get("status") for item in selected}
    missing = set(required) - {item["workflow"] for item in selected}
    if not selected:
        classification = "SHA_MISMATCH" if rejected and any(item["reason"] == "sha_mismatch" for item in rejected) else "CONNECTOR_OBSERVABILITY_INCOMPLETE"
    elif statuses & PENDING:
        classification = "CI_PENDING"
    elif conclusions & FAILURE:
        classification = "failure"
    elif not missing and conclusions == {"success"}:
        classification = "success"
    else:
        classification = "CONNECTOR_OBSERVABILITY_INCOMPLETE"

    evidence: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": "g5-status-evidence",
        "generated_at": payload.get("generated_at", utc_now()),
        "task_id": payload.get("task_id", ""),
        "repository": payload.get("repository", ""),
        "gate": "G5_DEPLOY",
        "merge_commit_sha": merge_sha,
        "classification": classification,
        "discovery": discovery,
        "required_workflows": required,
        "selected_runs": selected,
        "rejected_candidates": rejected,
        "checkpoint_required": classification == "CI_PENDING",
        "manual_action_authorized": False,
    }
    if payload.get("g4_approval_id") is not None:
        evidence["g4_approval_id"] = payload["g4_approval_id"]
    if payload.get("g4_scope_hash") is not None:
        evidence["g4_scope_hash"] = payload["g4_scope_hash"]
    if classification == "CI_PENDING":
        checkpoint_path = payload.get("checkpoint_path")
        if checkpoint_path:
            evidence["checkpoint_path"] = checkpoint_path
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        evidence = resolve(load(args.input))
        serialized = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(serialized, encoding="utf-8")
        else:
            print(serialized, end="")
    except (OSError, ValueError, TypeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"G5 STATUS RESOLUTION FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
