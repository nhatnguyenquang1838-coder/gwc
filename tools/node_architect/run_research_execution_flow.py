"""Replay-safe research approval -> execution materialization -> existing GWC handoff."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from .select_approved_research import select_approved_research
    from .materialize_research_execution import materialize_research_execution
except ImportError:  # pragma: no cover
    from select_approved_research import select_approved_research
    from materialize_research_execution import materialize_research_execution


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _checkpoint(value: Any, run_id: str) -> dict[str, Any]:
    cp = dict(value) if isinstance(value, Mapping) else {}
    cp.setdefault("schema_version", "1.0")
    cp.setdefault("artifact_type", "research-execution-flow-checkpoint")
    cp.setdefault("run_id", run_id)
    cp.setdefault("revision", 0)
    cp.setdefault("active_research_ref", None)
    cp.setdefault("active_approval_id", None)
    cp.setdefault("materialization_key", None)
    cp.setdefault("phase", "SELECT_RESEARCH")
    cp.setdefault("effects_started", [])
    cp.setdefault("execution_task_ids", None)
    cp.setdefault("stop_reason", None)
    return cp


def _store_config(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    config = payload.get("checkpoint_store")
    if config is None:
        return None
    if not isinstance(config, Mapping):
        raise ValueError("checkpoint_store must be an object")
    required = (
        "path",
        "controller_task_id",
        "repository",
        "branch",
        "base_sha",
        "head_sha",
        "scope_hash",
    )
    missing = [field for field in required if not str(config.get(field, "")).strip()]
    if missing:
        raise ValueError(f"checkpoint_store missing fields: {','.join(missing)}")
    return config


def _checkpoint_api():
    from tools.node_architect import checkpoint_store

    return checkpoint_store


def _load_durable_checkpoint(
    payload: Mapping[str, Any], run_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = _store_config(payload)
    if config is None:
        return _checkpoint(payload.get("checkpoint"), run_id), {
            "checkpoint_persisted": False,
            "checkpoint_store_revision": None,
            "checkpoint_store_digest": None,
        }
    api = _checkpoint_api()
    path = Path(str(config["path"]))
    store = api.load_store(path)
    node_id = str(config.get("node_id") or "research-review-to-execution")
    record = api.replay_checkpoint(
        store, str(config["controller_task_id"]), run_id, node_id
    )
    state = record.get("state") if isinstance(record, Mapping) else payload.get("checkpoint")
    cp = _checkpoint(state, run_id)
    return cp, {
        "checkpoint_persisted": isinstance(record, Mapping),
        "checkpoint_store_revision": int(store.get("revision", 0)),
        "checkpoint_store_digest": store.get("store_digest"),
    }


def _persist_durable_checkpoint(
    payload: Mapping[str, Any], cp: Mapping[str, Any]
) -> dict[str, Any]:
    config = _store_config(payload)
    if config is None:
        return {
            "checkpoint_persisted": False,
            "checkpoint_store_revision": None,
            "checkpoint_store_digest": None,
        }
    api = _checkpoint_api()
    path = Path(str(config["path"]))
    store = api.load_store(path)
    node_id = str(config.get("node_id") or "research-review-to-execution")
    controller_task_id = str(config["controller_task_id"])
    existing = api.replay_checkpoint(
        store, controller_task_id, str(cp["run_id"]), node_id
    )
    if isinstance(existing, Mapping) and existing.get("state") == dict(cp):
        return {
            "checkpoint_persisted": True,
            "checkpoint_store_revision": int(store.get("revision", 0)),
            "checkpoint_store_digest": store.get("store_digest"),
        }
    item = api.CheckpointInput(
        task_id=controller_task_id,
        run_id=str(cp["run_id"]),
        node_id=node_id,
        repository=str(config["repository"]),
        branch=str(config["branch"]),
        base_sha=str(config["base_sha"]),
        head_sha=str(config["head_sha"]),
        scope_hash=str(config["scope_hash"]),
        state=dict(cp),
        expected_revision=int(store.get("revision", 0)),
        graph_revision=(
            str(config.get("graph_revision"))
            if config.get("graph_revision")
            else None
        ),
    )
    updated = api.persist_to_file(path, item)
    readback = api.load_store(path)
    record = api.replay_checkpoint(
        readback, controller_task_id, str(cp["run_id"]), node_id
    )
    if not isinstance(record, Mapping) or record.get("state") != dict(cp):
        raise RuntimeError("CHECKPOINT_READBACK_MISMATCH")
    return {
        "checkpoint_persisted": True,
        "checkpoint_store_revision": int(updated.get("revision", 0)),
        "checkpoint_store_digest": updated.get("store_digest"),
    }


def _result(
    payload: Mapping[str, Any],
    cp: Mapping[str, Any],
    outcome: str,
    reason: str,
    *,
    persistence: Mapping[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    value = {
        "schema_version": "1.0",
        "artifact_type": "research-execution-flow-decision",
        "run_id": str(payload["run_id"]),
        "dispatch_id": str(payload["dispatch_id"]),
        "trigger_mode": str(payload["trigger_mode"]),
        "outcome": outcome,
        "reason_code": reason,
        "checkpoint": dict(cp),
        "parallel_execution_allowed": False,
        "g4_g5_g6_authority_granted": False,
        **(
            dict(persistence)
            if persistence is not None
            else {
                "checkpoint_persisted": False,
                "checkpoint_store_revision": None,
                "checkpoint_store_digest": None,
            }
        ),
        **extra,
    }
    value["decision_digest"] = _digest(value)
    return value


def _persist_before_effect(
    payload: Mapping[str, Any], cp: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Persist exact effect-intent state or fail closed before emitting the effect."""
    if _store_config(payload) is None:
        return None
    return _persist_durable_checkpoint(payload, cp)


def _materialize_or_stop(
    payload: Mapping[str, Any],
    cp: Mapping[str, Any],
    research: Mapping[str, Any],
    approval: Mapping[str, Any],
    *,
    effects_started: list[str] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        materialization = materialize_research_execution(
            research,
            approval,
            payload.get("projection_readbacks", {}),
            effects_started=effects_started,
        )
    except (ValueError, TypeError, KeyError) as exc:
        reason = str(exc).strip() or "RESEARCH_APPROVAL_INVALID"
        stopped = {
            **cp,
            "revision": int(cp.get("revision", 0)) + 1,
            "stop_reason": reason,
        }
        persistence = _persist_durable_checkpoint(payload, stopped)
        return None, _result(
            payload, stopped, "STOPPED", reason, persistence=persistence
        )
    return materialization, None


def run_research_execution_flow(payload: Mapping[str, Any]) -> dict[str, Any]:
    run_id = str(payload.get("run_id", "")).strip()
    dispatch_id = str(payload.get("dispatch_id", "")).strip()
    trigger_mode = str(payload.get("trigger_mode", "")).strip()
    if not run_id or not dispatch_id:
        raise ValueError("run_id and dispatch_id are required")
    if trigger_mode not in {"immediate_after_approval", "scheduled_poll"}:
        raise ValueError("unsupported trigger_mode")
    cp, loaded_persistence = _load_durable_checkpoint(payload, run_id)
    if cp["run_id"] != run_id:
        raise ValueError("checkpoint run_id mismatch")

    stop = payload.get("stop_conditions", {})
    if isinstance(stop, Mapping):
        for field, code in (
            ("terminal_blocker", "TERMINAL_BLOCKER"),
            ("human_authority_required", "HUMAN_AUTHORITY_REQUIRED"),
            ("approval_expired", "RESEARCH_APPROVAL_EXPIRED"),
            ("scope_drift", "RESEARCH_SCOPE_DRIFT"),
        ):
            if stop.get(field) is True:
                cp = {
                    **cp,
                    "revision": int(cp["revision"]) + 1,
                    "stop_reason": code,
                }
                persistence = _persist_durable_checkpoint(payload, cp)
                return _result(
                    payload,
                    cp,
                    "STOPPED",
                    code,
                    persistence=persistence,
                )

    # A replay of the same dispatch after an external effect is fenced. A new dispatch
    # resumes from the durable checkpoint and readbacks without repeating the effect.
    if cp.get("active_dispatch_id") == dispatch_id and cp.get("phase") in {
        "WAIT_PROJECTIONS",
        "WAIT_CLAIM",
        "HANDOFF_GWC",
        "WAIT_G3",
        "HUMAN_G4",
    }:
        return _result(
            payload,
            cp,
            "FENCED",
            "DUPLICATE_DISPATCH_FENCED",
            persistence=loaded_persistence,
        )

    records = payload.get("research_records", [])
    approvals = payload.get("approvals", [])
    if cp["phase"] == "SELECT_RESEARCH":
        selector_input = {
            "run_id": run_id,
            "trigger_mode": trigger_mode,
            "active_lane": payload.get("active_lane"),
            "excluded_lanes": payload.get("excluded_lanes", []),
            "research_records": records,
            "approvals": approvals,
            "dependency_evidence": payload.get("dependency_evidence", {}),
        }
        selection = select_approved_research(selector_input)
        ref = selection.get("selected_research")
        if not ref:
            return _result(
                payload,
                cp,
                "IDLE",
                "NO_ELIGIBLE_APPROVED_RESEARCH",
                persistence=loaded_persistence,
                selection=selection,
            )
        approval_id = selection.get("selected_approval_id")
        cp = {
            **cp,
            "revision": int(cp["revision"]) + 1,
            "active_research_ref": ref,
            "active_approval_id": approval_id,
            "active_dispatch_id": dispatch_id,
            "phase": "MATERIALIZE",
            "stop_reason": None,
        }

    by_ref = {
        str(x.get("research_ref")): x
        for x in records
        if isinstance(x, Mapping) and x.get("research_ref")
    }
    approvals_by_id = {
        str(x.get("approval_id")): x
        for x in approvals
        if isinstance(x, Mapping) and x.get("approval_id")
    }
    research = by_ref.get(str(cp.get("active_research_ref")))
    approval = approvals_by_id.get(str(cp.get("active_approval_id")))
    if not isinstance(research, Mapping) or not isinstance(approval, Mapping):
        cp = {
            **cp,
            "revision": int(cp.get("revision", 0)) + 1,
            "stop_reason": "RESEARCH_SNAPSHOT_MISSING",
        }
        persistence = _persist_durable_checkpoint(payload, cp)
        return _result(
            payload,
            cp,
            "STOPPED",
            "RESEARCH_SNAPSHOT_MISSING",
            persistence=persistence,
        )

    if cp["phase"] in {"MATERIALIZE", "WAIT_PROJECTIONS"}:
        materialization, stopped = _materialize_or_stop(
            payload,
            cp,
            research,
            approval,
            effects_started=list(cp.get("effects_started", [])),
        )
        if stopped is not None:
            return stopped
        assert materialization is not None
        if materialization["outcome"] == "CONFLICT":
            cp = {
                **cp,
                "revision": int(cp.get("revision", 0)) + 1,
                "stop_reason": materialization["reason_code"],
            }
            persistence = _persist_durable_checkpoint(payload, cp)
            return _result(
                payload,
                cp,
                "STOPPED",
                materialization["reason_code"],
                persistence=persistence,
                materialization=materialization,
            )
        if materialization["outcome"] == "RECONCILIATION_REQUIRED":
            return _result(
                payload,
                cp,
                "WAITING",
                materialization["reason_code"],
                persistence=loaded_persistence,
                materialization=materialization,
            )
        if materialization["outcome"] == "ACTION_REQUIRED":
            providers = [x["provider"] for x in materialization["projection_intents"]]
            cp = {
                **cp,
                "revision": int(cp["revision"]) + 1,
                "materialization_key": materialization["materialization_key"],
                "phase": "WAIT_PROJECTIONS",
                "effects_started": sorted(
                    set(cp.get("effects_started", [])) | set(providers)
                ),
                "active_dispatch_id": dispatch_id,
            }
            persistence = _persist_before_effect(payload, cp)
            if persistence is None:
                return _result(
                    payload,
                    cp,
                    "STOPPED",
                    "DURABLE_CHECKPOINT_STORE_REQUIRED",
                )
            return _result(
                payload,
                cp,
                "ACTION_REQUIRED",
                "EXECUTION_PROJECTION_CREATE_REQUIRED",
                persistence=persistence,
                materialization=materialization,
                external_actions=materialization["projection_intents"],
            )

        cp = {
            **cp,
            "revision": int(cp["revision"]) + 1,
            "materialization_key": materialization["materialization_key"],
            "phase": "WAIT_CLAIM",
            "effects_started": sorted(
                set(cp.get("effects_started", [])) | {"github", "jira"}
            ),
            "active_dispatch_id": dispatch_id,
        }
        if not isinstance(payload.get("claim_readback"), Mapping):
            if "claim" in set(cp.get("effects_started", [])):
                persistence = _persist_durable_checkpoint(payload, cp)
                return _result(
                    payload,
                    cp,
                    "WAITING",
                    "EXECUTION_TASK_CLAIM_RECONCILIATION_REQUIRED",
                    persistence=persistence,
                    materialization=materialization,
                )
            cp = {
                **cp,
                "revision": int(cp["revision"]) + 1,
                "effects_started": sorted(
                    set(cp.get("effects_started", [])) | {"claim"}
                ),
                "active_dispatch_id": dispatch_id,
            }
            persistence = _persist_before_effect(payload, cp)
            if persistence is None:
                return _result(
                    payload,
                    cp,
                    "STOPPED",
                    "DURABLE_CHECKPOINT_STORE_REQUIRED",
                    materialization=materialization,
                )
            return _result(
                payload,
                cp,
                "ACTION_REQUIRED",
                "EXECUTION_TASK_CLAIM_REQUIRED",
                persistence=persistence,
                materialization=materialization,
                external_actions=[materialization["claim_intent"]],
            )

    claim = payload.get("claim_readback")
    if cp["phase"] == "WAIT_CLAIM":
        if not isinstance(claim, Mapping):
            materialization, stopped = _materialize_or_stop(
                payload,
                cp,
                research,
                approval,
                effects_started=list(cp.get("effects_started", [])),
            )
            if stopped is not None:
                return stopped
            assert materialization is not None
            if materialization["outcome"] != "READY":
                return _result(
                    payload,
                    cp,
                    "WAITING",
                    materialization["reason_code"],
                    persistence=loaded_persistence,
                    materialization=materialization,
                )
            if "claim" in set(cp.get("effects_started", [])):
                persistence = _persist_durable_checkpoint(payload, cp)
                return _result(
                    payload,
                    cp,
                    "WAITING",
                    "EXECUTION_TASK_CLAIM_RECONCILIATION_REQUIRED",
                    persistence=persistence,
                    materialization=materialization,
                )
            cp = {
                **cp,
                "revision": int(cp["revision"]) + 1,
                "effects_started": sorted(
                    set(cp.get("effects_started", [])) | {"claim"}
                ),
                "active_dispatch_id": dispatch_id,
            }
            persistence = _persist_before_effect(payload, cp)
            if persistence is None:
                return _result(
                    payload,
                    cp,
                    "STOPPED",
                    "DURABLE_CHECKPOINT_STORE_REQUIRED",
                    materialization=materialization,
                )
            return _result(
                payload,
                cp,
                "ACTION_REQUIRED",
                "EXECUTION_TASK_CLAIM_REQUIRED",
                persistence=persistence,
                materialization=materialization,
                external_actions=[materialization["claim_intent"]],
            )
        if (
            claim.get("materialization_key") != cp.get("materialization_key")
            or claim.get("status") != "CLAIMED"
        ):
            cp = {
                **cp,
                "revision": int(cp.get("revision", 0)) + 1,
                "stop_reason": "EXECUTION_TASK_CLAIM_CONFLICT",
            }
            persistence = _persist_durable_checkpoint(payload, cp)
            return _result(
                payload,
                cp,
                "STOPPED",
                "EXECUTION_TASK_CLAIM_CONFLICT",
                persistence=persistence,
            )
        cp = {
            **cp,
            "revision": int(cp["revision"]) + 1,
            "execution_task_ids": claim.get("execution_task_ids"),
            "phase": "HANDOFF_GWC",
            "active_dispatch_id": dispatch_id,
        }
        loaded_persistence = _persist_durable_checkpoint(payload, cp)

    if cp["phase"] == "HANDOFF_GWC":
        materialization, stopped = _materialize_or_stop(
            payload,
            cp,
            research,
            approval,
            effects_started=list(cp.get("effects_started", [])),
        )
        if stopped is not None:
            return stopped
        assert materialization is not None
        spec = materialization["execution_task_spec"]
        handoff = {
            "action": "enter_existing_gwc_task_runtime",
            "task_ids": cp["execution_task_ids"],
            "materialization_key": cp["materialization_key"],
            "execution_task_spec_digest": spec["spec_digest"],
            "g2_authority": spec["child_authority"]["g2"],
            "g3_authority": spec["child_authority"]["g3"],
            "required_runtime_invariants": [
                "MODE_DOES_NOT_BYPASS_NODE_RUNTIME",
                "EXACT_HEAD_CI_REQUIRED",
                "REVIEW_STALE_AFTER_HEAD_CHANGE",
            ],
            "stop_before": "G4_MERGE",
        }
        runtime = payload.get("gwc_runtime_readback")
        if not isinstance(runtime, Mapping):
            if "gwc_handoff" in set(cp.get("effects_started", [])):
                return _result(
                    payload,
                    cp,
                    "WAITING",
                    "GWC_RUNTIME_HANDOFF_RECONCILIATION_REQUIRED",
                    persistence=loaded_persistence,
                    gwc_handoff=handoff,
                )
            cp = {
                **cp,
                "revision": int(cp["revision"]) + 1,
                "effects_started": sorted(
                    set(cp.get("effects_started", [])) | {"gwc_handoff"}
                ),
                "active_dispatch_id": dispatch_id,
            }
            persistence = _persist_before_effect(payload, cp)
            if persistence is None:
                return _result(
                    payload,
                    cp,
                    "STOPPED",
                    "DURABLE_CHECKPOINT_STORE_REQUIRED",
                    gwc_handoff=handoff,
                )
            return _result(
                payload,
                cp,
                "HANDOFF",
                "GWC_RUNTIME_HANDOFF_REQUIRED",
                persistence=persistence,
                gwc_handoff=handoff,
            )
        if runtime.get("materialization_key") != cp["materialization_key"]:
            cp = {
                **cp,
                "revision": int(cp.get("revision", 0)) + 1,
                "stop_reason": "GWC_RUNTIME_HANDOFF_MISMATCH",
            }
            persistence = _persist_durable_checkpoint(payload, cp)
            return _result(
                payload,
                cp,
                "STOPPED",
                "GWC_RUNTIME_HANDOFF_MISMATCH",
                persistence=persistence,
            )
        if runtime.get("status") == "BLOCKED":
            reason = str(runtime.get("reason_code") or "TERMINAL_BLOCKER")
            cp = {
                **cp,
                "revision": int(cp.get("revision", 0)) + 1,
                "stop_reason": reason,
            }
            persistence = _persist_durable_checkpoint(payload, cp)
            return _result(
                payload,
                cp,
                "STOPPED",
                reason,
                persistence=persistence,
            )
        if runtime.get("status") != "G3_PASS":
            cp = {
                **cp,
                "revision": int(cp["revision"]) + 1,
                "phase": "WAIT_G3",
                "active_dispatch_id": dispatch_id,
            }
            persistence = _persist_durable_checkpoint(payload, cp)
            return _result(
                payload,
                cp,
                "WAITING",
                "WAITING_FOR_G3_EXACT_HEAD",
                persistence=persistence,
                gwc_handoff=handoff,
            )
        cp = {
            **cp,
            "revision": int(cp["revision"]) + 1,
            "phase": "HUMAN_G4",
            "stop_reason": "HUMAN_AUTHORITY_REQUIRED",
            "active_dispatch_id": dispatch_id,
        }
        persistence = _persist_durable_checkpoint(payload, cp)
        return _result(
            payload,
            cp,
            "HUMAN_REQUIRED",
            "HUMAN_AUTHORITY_REQUIRED",
            persistence=persistence,
            g4_request={
                "gate": "G4_MERGE",
                "task_ids": cp["execution_task_ids"],
                "pr_number": runtime.get("pr_number"),
                "head_sha": runtime.get("head_sha"),
                "scope_hash": runtime.get("scope_hash"),
            },
        )

    if cp["phase"] == "WAIT_G3":
        runtime = payload.get("gwc_runtime_readback")
        if not isinstance(runtime, Mapping) or runtime.get("status") != "G3_PASS":
            return _result(
                payload,
                cp,
                "WAITING",
                "WAITING_FOR_G3_EXACT_HEAD",
                persistence=loaded_persistence,
            )
        if runtime.get("materialization_key") != cp["materialization_key"]:
            cp = {
                **cp,
                "revision": int(cp.get("revision", 0)) + 1,
                "stop_reason": "GWC_RUNTIME_HANDOFF_MISMATCH",
            }
            persistence = _persist_durable_checkpoint(payload, cp)
            return _result(
                payload,
                cp,
                "STOPPED",
                "GWC_RUNTIME_HANDOFF_MISMATCH",
                persistence=persistence,
            )
        cp = {
            **cp,
            "revision": int(cp["revision"]) + 1,
            "phase": "HUMAN_G4",
            "stop_reason": "HUMAN_AUTHORITY_REQUIRED",
            "active_dispatch_id": dispatch_id,
        }
        persistence = _persist_durable_checkpoint(payload, cp)
        return _result(
            payload,
            cp,
            "HUMAN_REQUIRED",
            "HUMAN_AUTHORITY_REQUIRED",
            persistence=persistence,
            g4_request={
                "gate": "G4_MERGE",
                "task_ids": cp["execution_task_ids"],
                "pr_number": runtime.get("pr_number"),
                "head_sha": runtime.get("head_sha"),
                "scope_hash": runtime.get("scope_hash"),
            },
        )

    return _result(
        payload,
        cp,
        "HUMAN_REQUIRED",
        "HUMAN_AUTHORITY_REQUIRED",
        persistence=loaded_persistence,
    )
