#!/usr/bin/env python3
"""Exact-head CI observation capture for GWC repository delivery nodes.

This module normalizes provider-supplied CI facts into deterministic local
observation evidence. It does not call GitHub itself; callers provide already-read
workflow/status payloads. The classifier is fail-closed: absent or ambiguous data
is UNAVAILABLE and can never be treated as PASS.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

TERMINAL_SUCCESS = {"success", "passed"}
TERMINAL_FAILURE = {"failure", "cancelled", "timed_out", "action_required", "failed", "error"}
NON_TERMINAL = {"queued", "waiting", "requested", "in_progress", "pending"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _run_conclusion(run: dict[str, Any]) -> str | None:
    conclusion = run.get("conclusion")
    if conclusion is not None:
        return str(conclusion).lower()
    state = run.get("status")
    return str(state).lower() if state is not None else None


def classify_provider_payload(head_sha: str, payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], bool]:
    runs = payload.get("workflow_runs") or payload.get("runs") or []
    statuses = payload.get("statuses") or []
    candidates: list[dict[str, Any]] = []
    for run in runs:
        candidate_sha = run.get("head_sha") or run.get("headSha") or run.get("sha")
        candidates.append({"source": "workflow_run", "id": run.get("id") or run.get("run_id"), "name": run.get("name") or run.get("workflow") or run.get("workflow_name"), "head_sha": candidate_sha, "status": run.get("status"), "conclusion": run.get("conclusion"), "url": run.get("html_url") or run.get("url")})
    for status in statuses:
        candidate_sha = status.get("sha") or payload.get("sha") or head_sha
        candidates.append({"source": "combined_status", "id": status.get("id") or status.get("context"), "name": status.get("context") or status.get("name"), "head_sha": candidate_sha, "status": status.get("state"), "conclusion": status.get("conclusion") or status.get("state"), "url": status.get("target_url") or status.get("url")})

    selected = [item for item in candidates if item.get("head_sha") == head_sha]
    rejected = [{**item, "reason": "sha_mismatch" if item.get("head_sha") else "missing_head_sha"} for item in candidates if item.get("head_sha") != head_sha]
    if not candidates:
        return "UNAVAILABLE", [], [], False
    if not selected:
        return "SHA_MISMATCH", [], rejected, False

    conclusions = {_run_conclusion(item) for item in selected}
    conclusions.discard(None)
    if any(item in TERMINAL_FAILURE for item in conclusions):
        return "FAILED", selected, rejected, False
    if selected and conclusions and all(item in TERMINAL_SUCCESS for item in conclusions):
        return "PASSED", selected, rejected, False
    if any(item in NON_TERMINAL for item in conclusions):
        return "PENDING", selected, rejected, True
    return "UNAVAILABLE", selected, rejected, False


def capture_ci_observation(*, task_id: str, repository: str, branch: str, base_sha: str, head_sha: str, scope_hash: str, provider_payload: dict[str, Any], observed_at: str | None = None) -> dict[str, Any]:
    classification, selected, rejected, checkpoint_required = classify_provider_payload(head_sha, provider_payload)
    observation = {"schema_version": "1.0", "artifact_type": "ci-observation", "task_id": task_id, "repository": repository, "branch": branch, "base_sha": base_sha, "head_sha": head_sha, "scope_hash": scope_hash, "observed_at": observed_at or _now(), "classification": classification, "selected_runs": selected, "rejected_candidates": rejected, "checkpoint_required": checkpoint_required, "provider_payload_digest": digest_payload(provider_payload)}
    observation["observation_digest"] = digest_payload({k: v for k, v in observation.items() if k != "observation_digest"})
    return observation


def is_replay_equivalent(first: dict[str, Any], second: dict[str, Any]) -> bool:
    def stable(payload: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in payload.items() if k not in {"observed_at", "observation_digest"}}
    return digest_payload(stable(first)) == digest_payload(stable(second))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize exact-head CI observation evidence.")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--scope-hash", required=True)
    parser.add_argument("--provider-payload", required=True)
    args = parser.parse_args(argv)
    payload = json.loads(args.provider_payload)
    print(json.dumps(capture_ci_observation(task_id=args.task_id, repository=args.repository, branch=args.branch, base_sha=args.base_sha, head_sha=args.head_sha, scope_hash=args.scope_hash, provider_payload=payload), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
