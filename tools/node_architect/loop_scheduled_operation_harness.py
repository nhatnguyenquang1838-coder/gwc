#!/usr/bin/env python3
"""SCRUM-842 Loop scheduled operation integration/harness layer (G2).

INTEGRATE + HARNESS ONLY — Hermes core is out of scope (read-only reference).
This module is the host-side adapter that wires the **frozen SCRUM-841**
LangGraph M1-M7 workflow into the native Hermes Loop schedule without touching
LoopManager internals or scheduler core:

1. ``emit_operation_envelope`` — on each Loop firing, builds a bound operation
   envelope with a stable tick/activity ID and the envelope fields required by
   the SCRUM-841 manifest (task_id, repository, run_id, operation_id,
   activity_id, base_sha, head_sha, working_branch, scope_hash,
   runtime_plan_digest, protocol_version, continuation_ref, cursor).
2. ``invoke_or_resume`` — invokes/resumes the same persistent frozen M1-M7
   graph run, replaying the run-bound checkpoint when present (CAS-guarded).
3. ``validate_verdict_and_readback`` — validates the structured verdict and the
   exact envelope readback (fail-closed on binding drift / forbidden bindings).
4. ``LoopSettlementReconciler`` (loop_settlement_reconciler) — exactly-once
   native LoopManager settlement.

Scheduler state stays native; browser bindings stay out of graph checkpoints.
The graph never settles the native loop itself (graph_settles_native_loop is
false in the frozen contract) — settlement is host-owned, exactly once.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .loop_settlement_reconciler import LoopSettlementReconciler, SettlementReconcilerError

OPERATION_ENVELOPE_FIELDS = (
    "task_id",
    "repository",
    "run_id",
    "operation_id",
    "activity_id",
    "base_sha",
    "head_sha",
    "working_branch",
    "scope_hash",
    "runtime_plan_digest",
    "protocol_version",
    "continuation_ref",
    "cursor",
)

PROTOCOL_VERSION = "dw.taskcontroller.continuation/v1"
M1_M7_NODE_ID = "scrum841-m1-m7-workflow"
M1_M7_TASK_ID = "SCRUM-841"
CHECKPOINT_ALLOWED_ROOT = ".gwc/tasks/SCRUM-842/g2/checkpoints"

_FORBIDDEN_CHECKPOINT_KEYS = {
    "browser_url", "browser_session", "dom_refs", "screenshots",
    "composer_contents", "send_control_state", "same", "same:N", "SAME:XX",
    "secret", "secrets",
}
_FORBIDDEN_PREFIXES = ("same", "secret")
_SHA256_PREFIX = "sha256:"


class HarnessContractError(ValueError):
    """A harness input violates the frozen SCRUM-841/SCRUM-842 contract."""


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(payload: Any) -> str:
    return _SHA256_PREFIX + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _load_contracts(root: Path | str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the frozen SCRUM-841 manifest/profile pair without langgraph import."""
    repo_root = Path(root).resolve()
    manifest_path = repo_root / "core/node-architect/scrum841-m1-m7-agent-workflow-r1.json"
    profile_path = repo_root / "core/node-architect/scrum841-m1-m7-runtime-profile-r1.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessContractError("WORKFLOW_CONTRACT_SOURCE_UNAVAILABLE") from exc
    if not isinstance(manifest, Mapping) or not isinstance(profile, Mapping):
        raise HarnessContractError("WORKFLOW_CONTRACT_SOURCE_UNAVAILABLE")
    if manifest.get("workflow_id") != "scrum841-m1-m7-agent-workflow-r1":
        raise HarnessContractError("WORKFLOW_SELECTION_INVALID")
    return dict(manifest), dict(profile)


# --------------------------------------------------------------------------
# 1. Bound operation envelope emission (per Loop firing)
# --------------------------------------------------------------------------

def emit_operation_envelope(
    root: Path | str,
    *,
    run_id: str,
    tick: int,
    operation_id: str | None = None,
    activity_id: str | None = None,
) -> dict[str, Any]:
    """Build the bound operation envelope for one Loop firing.

    Identity is bound to the frozen SCRUM-841 runtime profile (task_id,
    repository, base_sha, working_branch, scope_hash, runtime_plan_digest) and
    the stable tick: the same ``(run_id, tick)`` always yields an identical
    envelope, and a different tick yields a different operation/activity ID.
    """
    if not isinstance(run_id, str) or not run_id:
        raise HarnessContractError("OPERATION_ENVELOPE_RUN_ID_MISSING")
    if run_id.startswith("scrum781-q0-"):
        raise HarnessContractError("Q0_SOURCE_BOUND_ADAPTER_REQUIRED")
    if not isinstance(tick, int) or tick < 0:
        raise HarnessContractError("OPERATION_ENVELOPE_TICK_INVALID")

    manifest, profile = _load_contracts(root)
    task_id = str(profile["task_id"])
    repository = str(profile["repository"])
    base_sha = str(profile["base_sha"])
    working_branch = str(profile["working_branch"])
    scope_hash = str(profile["scope_hash"])
    runtime_plan_digest = str(profile["runtime_plan_digest"])

    resolved_activity_id = activity_id or f"tick-{tick}"
    resolved_operation_id = operation_id or f"{task_id}:{run_id}:{resolved_activity_id}"
    identity = {
        "task_id": task_id,
        "repository": repository,
        "run_id": run_id,
        "operation_id": resolved_operation_id,
        "activity_id": resolved_activity_id,
        "base_sha": base_sha,
        "head_sha": base_sha,
        "working_branch": working_branch,
        "scope_hash": scope_hash,
        "runtime_plan_digest": runtime_plan_digest,
    }
    return {
        **identity,
        "protocol_version": PROTOCOL_VERSION,
        "continuation_ref": _digest(identity),
        "cursor": {"controller_seq": tick, "executor_seq": tick},
    }


# --------------------------------------------------------------------------
# 2. Invoke / resume of the frozen persistent M1-M7 run
# --------------------------------------------------------------------------

def _resolve_checkpoint(
    root: Path,
    operation_envelope: Mapping[str, Any],
    checkpoint_store_ref: str | None,
    checkpoint_expected_revision: int | None,
) -> tuple[Path, int, dict[str, Any], dict[str, Any] | None]:
    """Read/reconcile the same-run checkpoint before resuming graph work.

    Mirrors the SCRUM-841 host guard: the store ref must be exactly the
    run-bound expected path under the SCRUM-842 checkpoint root; the CAS
    revision must match; an existing record must replay with no binding drift
    and be validated readback-safe.
    """
    run_id = operation_envelope.get("run_id")
    if not isinstance(run_id, str) or not run_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for ch in run_id):
        raise HarnessContractError("CHECKPOINT_RUN_ID_INVALID")
    expected_ref = f"{CHECKPOINT_ALLOWED_ROOT}/{run_id}.json"
    if checkpoint_store_ref != expected_ref:
        raise HarnessContractError("CHECKPOINT_STORE_PATH_NOT_RUN_BOUND")
    path = (root / str(checkpoint_store_ref)).resolve()
    allowed_root = (root / CHECKPOINT_ALLOWED_ROOT).resolve()
    if not str(path).startswith(str(allowed_root)):
        raise HarnessContractError("CHECKPOINT_STORE_PATH_OUTSIDE_SCOPE")

    from .checkpoint_store import (
        CheckpointInput,
        load_store,
        reconcile_unknown_outcome,
        replay_checkpoint,
        validate_readback,
    )
    exists = path.exists()
    store = load_store(path)
    actual_revision = int(store.get("revision", 0))
    expected_revision = checkpoint_expected_revision
    if expected_revision is None and not exists:
        expected_revision = 0
    if not isinstance(expected_revision, int) or expected_revision < 0 or expected_revision != actual_revision:
        raise HarnessContractError("CHECKPOINT_CAS_REVISION_MISMATCH")
    if not exists:
        return path, expected_revision, store, None

    record = replay_checkpoint(store, M1_M7_TASK_ID, run_id, M1_M7_NODE_ID)
    if not isinstance(record, Mapping):
        raise HarnessContractError("CHECKPOINT_UNKNOWN_OUTCOME_REQUIRES_RECONCILIATION")
    binding = {
        "task_id": operation_envelope.get("task_id"),
        "repository": operation_envelope.get("repository"),
        "branch": operation_envelope.get("working_branch"),
        "base_sha": operation_envelope.get("base_sha"),
        "head_sha": operation_envelope.get("head_sha"),
        "scope_hash": operation_envelope.get("scope_hash"),
    }
    if any(record.get(key) != value for key, value in binding.items()):
        raise HarnessContractError("CHECKPOINT_BINDING_DRIFT")
    item = CheckpointInput(
        task_id=M1_M7_TASK_ID, run_id=run_id, node_id=M1_M7_NODE_ID,
        repository=str(operation_envelope["repository"]),
        branch=str(operation_envelope["working_branch"]),
        base_sha=str(operation_envelope["base_sha"]),
        head_sha=str(operation_envelope["head_sha"]),
        scope_hash=str(operation_envelope["scope_hash"]),
        state=dict(record.get("state") or {}),
        expected_revision=expected_revision,
        graph_revision="scrum841-m1-m7-agent-workflow-r1",
    )
    if reconcile_unknown_outcome(store, item).get("outcome") != "KNOWN_STATE":
        raise HarnessContractError("CHECKPOINT_UNKNOWN_OUTCOME_REQUIRES_RECONCILIATION")
    validate_readback(store, item)
    return path, expected_revision, store, dict(record.get("state") or {})


def invoke_or_resume(
    root: Path | str,
    *,
    operation_envelope: Mapping[str, Any],
    inputs: Mapping[str, Any],
    checkpoint_store_ref: str,
    checkpoint_expected_revision: int | None = None,
) -> dict[str, Any]:
    """Invoke (or resume) the same frozen persistent LangGraph M1-M7 run.

    Returns a structured result with the graph verdict, host request lists
    (including the data-only settlement request when M7 requires host
    settlement), the exact checkpoint projection and persistence evidence.
    Fails closed on contract/source errors; the graph is never asked to
    settle the native loop, own scheduler state, or touch browser bindings.
    """
    repo_root = Path(root).resolve()
    if not isinstance(operation_envelope, Mapping) or not isinstance(inputs, Mapping):
        raise HarnessContractError("WORKFLOW_OPERATION_ENVELOPE_INVALID")
    for field in OPERATION_ENVELOPE_FIELDS:
        if field != "cursor" and (not isinstance(operation_envelope.get(field), str) or not operation_envelope[field]):
            raise HarnessContractError("OPERATION_IDENTITY_MISSING")
    if not isinstance(operation_envelope.get("cursor"), Mapping):
        raise HarnessContractError("OPERATION_IDENTITY_MISSING")

    try:
        from .m1_m7_agent_workflow import build_m1_m7_graph, load_m1_m7_contracts
    except (ImportError, ModuleNotFoundError) as exc:
        return {
            "verdict": {"status": "BLOCKED", "reason_code": "LANGGRAPH_BACKEND_UNAVAILABLE", "current_activity": "M1"},
            "host_action_requests": [], "controller_exchange_requests": [],
            "settlement_requests": [], "checkpoint_projection": None,
            "checkpoint_persistence": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

    manifest, profile = load_m1_m7_contracts(repo_root)
    exact = {
        "task_id": "task_id", "repository": "repository", "base_sha": "base_sha",
        "working_branch": "working_branch", "scope_hash": "scope_hash",
    }
    if any(operation_envelope.get(op_key) != profile.get(state_key) for op_key, state_key in exact.items()):
        return {
            "verdict": {"status": "BLOCKED", "reason_code": "WORKFLOW_CANONICAL_STATE_MISMATCH", "current_activity": "M1"},
            "host_action_requests": [], "controller_exchange_requests": [],
            "settlement_requests": [], "checkpoint_projection": None,
            "checkpoint_persistence": None,
        }
    if operation_envelope.get("head_sha") != operation_envelope.get("base_sha"):
        return {
            "verdict": {"status": "BLOCKED", "reason_code": "INITIAL_HEAD_BINDING_MISMATCH", "current_activity": "M1"},
            "host_action_requests": [], "controller_exchange_requests": [],
            "settlement_requests": [], "checkpoint_projection": None,
            "checkpoint_persistence": None,
        }

    graph = build_m1_m7_graph(
        workflow_manifest=manifest,
        runtime_profile=profile,
        activity_source_sha256=manifest["source_sha256"],
    )
    initial: dict[str, Any] = {
        "operation_envelope": dict(operation_envelope),
        "inputs": dict(inputs),
        "host_action_requests": [],
        "settlement_requests": [],
        "child_dispatch_requests": [],
        "controller_exchange_requests": [],
        "activity_results": {},
        "authority_granted": False,
        "executed_effects": [],
    }
    try:
        checkpoint_path, expected_revision, checkpoint_store, prior_projection = _resolve_checkpoint(
            repo_root, operation_envelope, checkpoint_store_ref, checkpoint_expected_revision
        )
        if prior_projection is not None:
            if prior_projection.get("operation_id") != operation_envelope["operation_id"]:
                old_activity = str(prior_projection.get("activity_id", ""))
                new_activity = str(operation_envelope["activity_id"])
                safe_empty_hold = (
                    prior_projection.get("current_activity") == "M1"
                    and (prior_projection.get("activity_results") or {}).get("M1", {}).get("reason_code") == "OBSERVER_UNQUALIFIED"
                    and not any(prior_projection.get(key) for key in ("idempotency_keys", "controller_exchange_idempotency_keys", "settlement_idempotency_keys"))
                )
                if not (safe_empty_hold and old_activity.startswith("tick-") and new_activity.startswith("tick-") and old_activity[5:].isdigit() and new_activity[5:].isdigit() and int(new_activity[5:]) > int(old_activity[5:])):
                    raise HarnessContractError("CHECKPOINT_PRIOR_OPERATION_UNSETTLED")
                prior_projection = {**prior_projection, **{key: operation_envelope[key] for key in OPERATION_ENVELOPE_FIELDS}, "current_activity": "M1", "activity_results": {}, "mailbox_classification": None}
            initial["checkpoint_projection"] = prior_projection
            initial["activity_results"] = dict(prior_projection.get("activity_results") or {})
            initial["mailbox_classification"] = prior_projection.get("mailbox_classification")
            for state_key, projection_key in (
                ("host_action_requests", "idempotency_keys"),
                ("controller_exchange_requests", "controller_exchange_idempotency_keys"),
                ("settlement_requests", "settlement_idempotency_keys"),
            ):
                prior_keys = list(prior_projection.get(projection_key) or [])
                if prior_keys:
                    initial[state_key] = [{"idempotency_key": key} for key in prior_keys]
        raw = graph.invoke(initial)
    except HarnessContractError as exc:
        return {
            "verdict": {"status": "BLOCKED", "reason_code": str(exc), "current_activity": "M1"},
            "host_action_requests": [], "controller_exchange_requests": [],
            "settlement_requests": [], "checkpoint_projection": None,
            "checkpoint_persistence": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "verdict": {"status": "BLOCKED", "reason_code": "M1_M7_GRAPH_OR_CHECKPOINT_ERROR", "current_activity": "M1"},
            "host_action_requests": [], "controller_exchange_requests": [],
            "settlement_requests": [], "checkpoint_projection": None,
            "checkpoint_persistence": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

    prior_checkpoint = initial.get("checkpoint_projection")
    prior_checkpoint = prior_checkpoint if isinstance(prior_checkpoint, Mapping) else {}
    activity_results = raw.get("activity_results")
    activity_results = activity_results if isinstance(activity_results, Mapping) else dict(prior_checkpoint.get("activity_results") or {})

    projection: dict[str, Any] = {
        key: operation_envelope[key] for key in OPERATION_ENVELOPE_FIELDS if key in operation_envelope
    }
    projection.update({
        "current_activity": raw.get("current_activity") or prior_checkpoint.get("current_activity") or "M1",
        "mailbox_classification": raw.get("mailbox_classification") or prior_checkpoint.get("mailbox_classification"),
        "activity_results": dict(activity_results),
        "receipt_refs": list(dict.fromkeys(
            value.get("readback_digest") for value in activity_results.values()
            if isinstance(value, Mapping) and value.get("readback_digest")
        )),
        "idempotency_keys": list(prior_checkpoint.get("idempotency_keys") or []),
        "controller_exchange_idempotency_keys": list(prior_checkpoint.get("controller_exchange_idempotency_keys") or []),
        "settlement_idempotency_keys": list(prior_checkpoint.get("settlement_idempotency_keys") or []),
    })

    for state_key, projection_key in (
        ("host_action_requests", "idempotency_keys"),
        ("controller_exchange_requests", "controller_exchange_idempotency_keys"),
        ("settlement_requests", "settlement_idempotency_keys"),
    ):
        projection[projection_key] = list(dict.fromkeys([
            *projection[projection_key],
            *[item["idempotency_key"] for item in raw.get(state_key, []) if isinstance(item, Mapping) and isinstance(item.get("idempotency_key"), str)],
        ]))

    # persist with CAS (exactly-once checkpointing; replay of identical state is a no-op)
    from .checkpoint_store import CheckpointInput, digest_payload, load_store, persist_to_file, replay_checkpoint, validate_readback
    item = CheckpointInput(
        task_id=M1_M7_TASK_ID, run_id=str(operation_envelope["run_id"]),
        node_id=M1_M7_NODE_ID, repository=str(operation_envelope["repository"]),
        branch=str(operation_envelope["working_branch"]),
        base_sha=str(operation_envelope["base_sha"]),
        head_sha=str(operation_envelope["head_sha"]),
        scope_hash=str(operation_envelope["scope_hash"]),
        state=dict(projection), expected_revision=expected_revision,
        graph_revision=str(manifest["workflow_id"]),
    )
    prior_record = replay_checkpoint(checkpoint_store, item.task_id, item.run_id, item.node_id)
    if prior_record is not None and prior_record.get("state_digest") == digest_payload(item.state):
        checkpoint_result = {
            "outcome": "IDEMPOTENT_REPLAY", "revision": prior_record.get("revision"),
            "state_digest": prior_record.get("state_digest"), "store_path": str(checkpoint_path),
        }
    else:
        persist_to_file(checkpoint_path, item)
        checkpoint_result = {**validate_readback(load_store(checkpoint_path), item), "store_path": str(checkpoint_path)}

    settlement_requests = raw.get("settlement_requests")
    settlement_requests = settlement_requests if isinstance(settlement_requests, list) else []
    host_action_requests = raw.get("host_action_requests")
    host_action_requests = host_action_requests if isinstance(host_action_requests, list) else []
    controller_exchange_requests = raw.get("controller_exchange_requests")
    controller_exchange_requests = controller_exchange_requests if isinstance(controller_exchange_requests, list) else []

    return {
        "verdict": {
            "status": str(raw.get("status") or "BLOCKED"),
            "reason_code": str(raw.get("reason_code") or "M1_M7_RESULT_UNTYPED"),
            "current_activity": str(raw.get("current_activity") or projection["current_activity"]),
            "mailbox_classification": raw.get("mailbox_classification"),
            "activity_results": dict(activity_results),
        },
        "host_action_requests": [dict(item) for item in host_action_requests],
        "controller_exchange_requests": [dict(item) for item in controller_exchange_requests],
        "settlement_requests": [dict(item) for item in settlement_requests],
        "checkpoint_projection": dict(projection),
        "checkpoint_persistence": checkpoint_result,
        "invocation_digest": _digest({
            "envelope": dict(operation_envelope),
            "verdict": dict(projection),
            "checkpoint": checkpoint_result,
        }),
    }


# --------------------------------------------------------------------------
# 3. Structured verdict + exact readback validation
# --------------------------------------------------------------------------

def _forbidden_key_hit(checkpoint: Mapping[str, Any]) -> str | None:
    for key in checkpoint:
        lowered = str(key).lower()
        if key in _FORBIDDEN_CHECKPOINT_KEYS or any(lowered.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES):
            return str(key)
    return None


def validate_verdict_and_readback(
    result: Mapping[str, Any],
    operation_envelope: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the structured verdict and the exact envelope readback.

    Fails closed when the returned checkpoint projection drifts from the
    emitted envelope identity, when a forbidden (browser/secrets) binding
    appears in the projection, or when the verdict has no typed status/reason.
    """
    verdict = result.get("verdict")
    if not isinstance(verdict, Mapping):
        return {"outcome": "FAIL", "readback_verified": False, "reason_code": "VERDICT_MISSING", "verdict": None}
    status = str(verdict.get("status") or "")
    reason_code = str(verdict.get("reason_code") or "")
    if status not in {"CONTINUE", "WAIT", "HOLD", "BLOCKED"} or not reason_code:
        return {"outcome": "FAIL", "readback_verified": False, "reason_code": "VERDICT_STATUS_INVALID", "verdict": status}

    projection = result.get("checkpoint_projection")
    if not isinstance(projection, Mapping):
        return {"outcome": "FAIL", "readback_verified": False, "reason_code": "READBACK_PROJECTION_MISSING", "verdict": status}

    for field in OPERATION_ENVELOPE_FIELDS:
        if projection.get(field) != operation_envelope.get(field):
            return {
                "outcome": "FAIL", "readback_verified": False,
                "reason_code": "VERDICT_ENVELOPE_BINDING_DRIFT",
                "verdict": status, "drift_field": field,
            }

    forbidden = _forbidden_key_hit(projection)
    if forbidden is not None:
        return {
            "outcome": "FAIL", "readback_verified": False,
            "reason_code": "CHECKPOINT_FORBIDDEN_BINDING",
            "verdict": status, "forbidden_key": forbidden,
        }

    return {
        "outcome": "PASS",
        "readback_verified": True,
        "verdict": status,
        "reason_code": reason_code,
        "projection_digest": _digest(projection),
    }


# --------------------------------------------------------------------------
# 4. Exactly-once native settlement entry point (host callback injection)
# --------------------------------------------------------------------------

def settle_exactly_once(
    settlement_request: Mapping[str, Any],
    native_settlement: Any,
    ledger_path: Path | str,
) -> dict[str, Any]:
    """Invoke native LoopManager settlement exactly once for the fired tick.

    ``native_settlement`` is the host-injected native LoopManager settlement
    adapter (Hermes core stays untouched); the durable reconciler ledger makes
    a crash/resume replay a no-op.
    """
    if not isinstance(settlement_request, Mapping):
        raise SettlementReconcilerError("SETTLEMENT_REQUEST_INVALID")
    reconciler = LoopSettlementReconciler(ledger_path)
    return reconciler.settle_exactly_once(settlement_request, native_settlement)


__all__ = [
    "OPERATION_ENVELOPE_FIELDS",
    "PROTOCOL_VERSION",
    "HarnessContractError",
    "emit_operation_envelope",
    "invoke_or_resume",
    "validate_verdict_and_readback",
    "settle_exactly_once",
    "LoopSettlementReconciler",
]