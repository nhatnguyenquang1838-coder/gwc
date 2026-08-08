"""Replay-safe research approval -> execution materialization -> existing GWC handoff."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
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


def _result(payload: Mapping[str, Any], cp: Mapping[str, Any], outcome: str, reason: str, **extra: Any) -> dict[str, Any]:
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
        **extra,
    }
    value["decision_digest"] = _digest(value)
    return value


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
        return None, _result(payload, stopped, "STOPPED", reason)
    return materialization, None


def run_research_execution_flow(payload: Mapping[str, Any]) -> dict[str, Any]:
    run_id = str(payload.get("run_id", "")).strip()
    dispatch_id = str(payload.get("dispatch_id", "")).strip()
    trigger_mode = str(payload.get("trigger_mode", "")).strip()
    if not run_id or not dispatch_id:
        raise ValueError("run_id and dispatch_id are required")
    if trigger_mode not in {"immediate_after_approval", "scheduled_poll"}:
        raise ValueError("unsupported trigger_mode")
    cp = _checkpoint(payload.get("checkpoint"), run_id)
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
                cp = {**cp, "revision": int(cp["revision"]) + 1, "stop_reason": code}
                return _result(payload, cp, "STOPPED", code)

    # A replay of the same dispatch after an external effect is fenced. A new dispatch
    # resumes from the durable checkpoint and readbacks without repeating the effect.
    if cp.get("active_dispatch_id") == dispatch_id and cp.get("phase") in {
        "WAIT_PROJECTIONS",
        "WAIT_CLAIM",
        "HANDOFF_GWC",
        "WAIT_G3",
        "HUMAN_G4",
    }:
        return _result(payload, cp, "FENCED", "DUPLICATE_DISPATCH_FENCED")

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
            return _result(payload, cp, "IDLE", "NO_ELIGIBLE_APPROVED_RESEARCH", selection=selection)
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
        return _result(payload, cp, "STOPPED", "RESEARCH_SNAPSHOT_MISSING")

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
            return _result(
                payload,
                cp,
                "STOPPED",
                materialization["reason_code"],
                materialization=materialization,
            )
        if materialization["outcome"] == "RECONCILIATION_REQUIRED":
            return _result(
                payload,
                cp,
                "WAITING",
                materialization["reason_code"],
                materialization=materialization,
            )
        if materialization["outcome"] == "ACTION_REQUIRED":
            providers = [x["provider"] for x in materialization["projection_intents"]]
            cp = {
                **cp,
                "revision": int(cp["revision"]) + 1,
                "materialization_key": materialization["materialization_key"],
                "phase": "WAIT_PROJECTIONS",
                "effects_started": sorted(set(cp.get("effects_started", [])) | set(providers)),
                "active_dispatch_id": dispatch_id,
            }
            return _result(
                payload,
                cp,
                "ACTION_REQUIRED",
                "EXECUTION_PROJECTION_CREATE_REQUIRED",
                materialization=materialization,
                external_actions=materialization["projection_intents"],
            )
        cp = {
            **cp,
            "revision": int(cp["revision"]) + 1,
            "materialization_key": materialization["materialization_key"],
            "phase": "WAIT_CLAIM",
            "effects_started": sorted(set(cp.get("effects_started", [])) | {"github", "jira"}),
            "active_dispatch_id": dispatch_id,
        }
        if not isinstance(payload.get("claim_readback"), Mapping):
            return _result(
                payload,
                cp,
                "ACTION_REQUIRED",
                "EXECUTION_TASK_CLAIM_REQUIRED",
                materialization=materialization,
                external_actions=[materialization["claim_intent"]],
            )

    claim = payload.get("claim_readback")
    if cp["phase"] == "WAIT_CLAIM":
        if not isinstance(claim, Mapping):
            materialization, stopped = _materialize_or_stop(
                payload, cp, research, approval, effects_started=[]
            )
            if stopped is not None:
                return stopped
            assert materialization is not None
            return _result(
                payload,
                cp,
                "ACTION_REQUIRED",
                "EXECUTION_TASK_CLAIM_REQUIRED",
                materialization=materialization,
                external_actions=[materialization["claim_intent"]],
            )
        if claim.get("materialization_key") != cp.get("materialization_key") or claim.get("status") != "CLAIMED":
            return _result(payload, cp, "STOPPED", "EXECUTION_TASK_CLAIM_CONFLICT")
        cp = {
            **cp,
            "revision": int(cp["revision"]) + 1,
            "execution_task_ids": claim.get("execution_task_ids"),
            "phase": "HANDOFF_GWC",
        }

    if cp["phase"] == "HANDOFF_GWC":
        materialization, stopped = _materialize_or_stop(
            payload, cp, research, approval, effects_started=[]
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
            return _result(payload, cp, "HANDOFF", "GWC_RUNTIME_HANDOFF_REQUIRED", gwc_handoff=handoff)
        if runtime.get("materialization_key") != cp["materialization_key"]:
            return _result(payload, cp, "STOPPED", "GWC_RUNTIME_HANDOFF_MISMATCH")
        if runtime.get("status") == "BLOCKED":
            return _result(payload, cp, "STOPPED", str(runtime.get("reason_code") or "TERMINAL_BLOCKER"))
        if runtime.get("status") != "G3_PASS":
            cp = {**cp, "revision": int(cp["revision"]) + 1, "phase": "WAIT_G3"}
            return _result(payload, cp, "WAITING", "WAITING_FOR_G3_EXACT_HEAD", gwc_handoff=handoff)
        cp = {
            **cp,
            "revision": int(cp["revision"]) + 1,
            "phase": "HUMAN_G4",
            "stop_reason": "HUMAN_AUTHORITY_REQUIRED",
        }
        return _result(
            payload,
            cp,
            "HUMAN_REQUIRED",
            "HUMAN_AUTHORITY_REQUIRED",
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
            return _result(payload, cp, "WAITING", "WAITING_FOR_G3_EXACT_HEAD")
        if runtime.get("materialization_key") != cp["materialization_key"]:
            return _result(payload, cp, "STOPPED", "GWC_RUNTIME_HANDOFF_MISMATCH")
        cp = {
            **cp,
            "revision": int(cp["revision"]) + 1,
            "phase": "HUMAN_G4",
            "stop_reason": "HUMAN_AUTHORITY_REQUIRED",
        }
        return _result(
            payload,
            cp,
            "HUMAN_REQUIRED",
            "HUMAN_AUTHORITY_REQUIRED",
            g4_request={
                "gate": "G4_MERGE",
                "task_ids": cp["execution_task_ids"],
                "pr_number": runtime.get("pr_number"),
                "head_sha": runtime.get("head_sha"),
                "scope_hash": runtime.get("scope_hash"),
            },
        )

    return _result(payload, cp, "HUMAN_REQUIRED", "HUMAN_AUTHORITY_REQUIRED")
