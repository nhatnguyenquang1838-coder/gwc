"""Deterministic M5 CI evidence capture for validation_quality.ci-evidence-capture.

This module is data-only: callers supply provider readback and an optional
in-memory checkpoint store. It never calls GitHub or grants later-gate authority.
"""
from __future__ import annotations
from copy import deepcopy
import re
from typing import Any, Mapping, MutableMapping
from .ci_run_capture import capture_ci_observation, digest_payload
from .checkpoint_store import CheckpointInput, checkpoint_key, persist_checkpoint, replay_checkpoint

NODE_ID = "validation_quality.ci-evidence-capture"
PASS = "PASS"; BLOCKED = "BLOCKED"; WAIT = "WAIT"
REASON_CODES = {"CI_SUCCESS","CI_FAILURE","CI_CANCELLED","CI_PENDING","CI_UNAVAILABLE_AT_CHECK","CI_TIMEOUT","STALE_HEAD","CI_SHA_MISMATCH"}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SCOPE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _require_text(payload: Mapping[str, Any], field: str) -> str:
    value = str(payload.get(field, "")).strip()
    if not value:
        raise ValueError(f"{field} is required")
    return value


def _legacy_provider_payload(payload: Mapping[str, Any], head_sha: str) -> dict[str, Any]:
    provider = dict(payload.get("provider_payload") or {})
    if provider.get("workflow_runs") or provider.get("runs") or provider.get("statuses"):
        return provider
    status = payload.get("status") or payload.get("conclusion")
    if status is None:
        return provider
    normalized = str(status).lower()
    run_status = "completed" if normalized in {"success","passed","failure","failed","cancelled","timed_out","error"} else normalized
    return {"workflow_runs":[{"id":payload.get("run_id") or "legacy-client-runtime","name":payload.get("workflow_name") or "client-runtime-ci","head_sha":payload.get("head_sha") or head_sha,"status":run_status,"conclusion":normalized,"html_url":payload.get("url")}]}


def _cancelled(observation: Mapping[str, Any]) -> bool:
    return any(str(run.get("conclusion", "")).lower() == "cancelled" for run in observation.get("selected_runs", []))


def _stable_input(payload: Mapping[str, Any], provider_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task_id": payload["task_id"], "run_id": payload["run_id"], "repository": payload["repository"],
        "branch": payload["branch"], "base_sha": payload["base_sha"], "head_sha": payload["head_sha"],
        "scope_hash": payload["scope_hash"], "graph_revision": payload["graph_revision"],
        "idempotency_key": payload["idempotency_key"], "timed_out": bool(payload.get("timed_out", False)),
        "provider_payload_digest": digest_payload(provider_payload),
        "prior_head_sha": (payload.get("prior_evidence") or {}).get("head_sha"),
    }


def _result(*, payload: Mapping[str, Any], observation: Mapping[str, Any], status: str, reason_code: str,
            input_digest: str, checkpoint_required: bool, replayed: bool = False, detail_code: str | None = None) -> dict[str, Any]:
    result = {
        "schema_version": "1.0", "artifact_type": "ci-evidence-capture-decision", "node_id": NODE_ID,
        "task_id": payload["task_id"], "run_id": payload["run_id"], "repository": payload["repository"],
        "branch": payload["branch"], "base_sha": payload["base_sha"], "head_sha": payload["head_sha"],
        "scope_hash": payload["scope_hash"], "graph_revision": payload["graph_revision"],
        "idempotency_key": payload["idempotency_key"], "status": status, "reason_code": reason_code,
        "detail_code": detail_code, "provider_observation": dict(observation), "input_digest": input_digest,
        "checkpoint_required": checkpoint_required,
        "checkpoint_key": checkpoint_key(payload["task_id"], payload["run_id"], NODE_ID) if checkpoint_required else None,
        "replayed": replayed, "merge_authority_granted": False, "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    digest_basis = {k: v for k, v in result.items() if k not in {"evidence_digest", "replayed"}}
    digest_basis["provider_observation"] = {k: v for k, v in result["provider_observation"].items() if k not in {"observed_at", "observation_digest"}}
    result["evidence_digest"] = digest_payload(digest_basis)
    return result


def capture_ci_evidence(
    evidence: Mapping[str, Any], *, checkpoint_store: MutableMapping[str, Any] | None = None,
    replay_cache: MutableMapping[str, dict[str, Any]] | None = None, observed_at: str | None = None,
    crash_after_checkpoint: bool = False,
) -> dict[str, Any]:
    payload = dict(evidence)
    for field in ("task_id","run_id","repository","branch","base_sha","head_sha","scope_hash","graph_revision","idempotency_key"):
        payload[field] = _require_text(payload, field)
    if not _SHA_RE.fullmatch(payload["base_sha"]): raise ValueError("base_sha must be a 40-character lowercase SHA")
    if not _SHA_RE.fullmatch(payload["head_sha"]): raise ValueError("head_sha must be a 40-character lowercase SHA")
    if not _SCOPE_RE.fullmatch(payload["scope_hash"]): raise ValueError("scope_hash must be sha256:<64 lowercase hex>")

    provider_payload = _legacy_provider_payload(payload, payload["head_sha"])
    stable = _stable_input(payload, provider_payload); input_digest = digest_payload(stable)
    cache_key = payload["idempotency_key"]
    if replay_cache is not None and cache_key in replay_cache:
        cached = replay_cache[cache_key]
        if cached.get("input_digest") != input_digest:
            observation = capture_ci_observation(task_id=payload["task_id"], repository=payload["repository"], branch=payload["branch"], base_sha=payload["base_sha"], head_sha=payload["head_sha"], scope_hash=payload["scope_hash"], provider_payload=provider_payload, observed_at=observed_at)
            return _result(payload=payload, observation=observation, status=BLOCKED, reason_code="CI_FAILURE", input_digest=input_digest, checkpoint_required=False, detail_code="IDEMPOTENCY_CONFLICT")
        replay = deepcopy(cached); replay["replayed"] = True; return replay

    existing = replay_checkpoint(checkpoint_store, payload["task_id"], payload["run_id"], NODE_ID) if checkpoint_store is not None else None
    if existing and existing.get("state", {}).get("input_digest") == input_digest:
        replay = deepcopy(existing["state"]["result"]); replay["replayed"] = True
        if replay_cache is not None: replay_cache[cache_key] = deepcopy(existing["state"]["result"])
        return replay

    observation = capture_ci_observation(task_id=payload["task_id"], repository=payload["repository"], branch=payload["branch"], base_sha=payload["base_sha"], head_sha=payload["head_sha"], scope_hash=payload["scope_hash"], provider_payload=provider_payload, observed_at=observed_at)
    prior = payload.get("prior_evidence") or {}
    if prior.get("head_sha") and prior.get("head_sha") != payload["head_sha"]:
        result = _result(payload=payload, observation=observation, status=BLOCKED, reason_code="STALE_HEAD", input_digest=input_digest, checkpoint_required=False)
    elif observation["classification"] == "PASSED":
        result = _result(payload=payload, observation=observation, status=PASS, reason_code="CI_SUCCESS", input_digest=input_digest, checkpoint_required=False)
    elif observation["classification"] == "FAILED":
        reason = "CI_CANCELLED" if _cancelled(observation) else "CI_FAILURE"
        result = _result(payload=payload, observation=observation, status=BLOCKED, reason_code=reason, input_digest=input_digest, checkpoint_required=False)
    elif observation["classification"] == "SHA_MISMATCH":
        result = _result(payload=payload, observation=observation, status=BLOCKED, reason_code="CI_SHA_MISMATCH", input_digest=input_digest, checkpoint_required=False)
    else:
        if bool(payload.get("timed_out", False)):
            reason = "CI_TIMEOUT"
        elif observation["classification"] == "PENDING":
            reason = "CI_PENDING"
        else:
            reason = "CI_UNAVAILABLE_AT_CHECK"
        result = _result(payload=payload, observation=observation, status=WAIT, reason_code=reason, input_digest=input_digest, checkpoint_required=True)
        if checkpoint_store is not None:
            persist_checkpoint(checkpoint_store, CheckpointInput(task_id=payload["task_id"], run_id=payload["run_id"], node_id=NODE_ID, repository=payload["repository"], branch=payload["branch"], base_sha=payload["base_sha"], head_sha=payload["head_sha"], scope_hash=payload["scope_hash"], graph_revision=payload["graph_revision"], state={"input_digest":input_digest,"result":deepcopy(result)}), committed_at=observed_at)
            if crash_after_checkpoint: raise RuntimeError("SIMULATED_CRASH_AFTER_CHECKPOINT")
    if result["reason_code"] not in REASON_CODES: raise AssertionError("reason code escaped closed set")
    if replay_cache is not None: replay_cache[cache_key] = deepcopy(result)
    return result

__all__=["BLOCKED","NODE_ID","PASS","REASON_CODES","WAIT","capture_ci_evidence"]
