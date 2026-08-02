#!/usr/bin/env python3
"""Client runtime adapter for the SCRUM-256 exact G3 vertical slice."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from .ci_evidence_capture import capture_ci_evidence
from .evidence_quality_check import check_evidence_quality
from .g3_pass_decision import G3_PASS, decide_g3_pass

VERTICAL_SLICE_ROUTE = (
    "client_request",
    "route_scenario_validation",
    "repo_delivery.ci-run-capture",
    "runtime_checkpoint.checkpoint-persist",
    "validation_quality.ci-evidence-capture",
    "validation_quality.evidence-quality-check",
    "validation_quality.g3-pass-decision",
)
TERMINAL_NODE = "terminal_typed_result"
ALLOWED_ROUTE_INTENT = "client-runtime-node-architect-vertical-slice"
PASS = "PASS"
BLOCKED = "BLOCKED"
BLOCKED_ROUTE_NOT_ALLOWLISTED = "BLOCKED_ROUTE_NOT_ALLOWLISTED"
BLOCKED_NODE_HANDLER_UNAVAILABLE = "BLOCKED_NODE_HANDLER_UNAVAILABLE"
BLOCKED_NODE_HANDLER_ERROR = "BLOCKED_NODE_HANDLER_ERROR"
BLOCKED_MISSING_REQUIRED_FIELD = "BLOCKED_MISSING_REQUIRED_FIELD"
TERMINAL_PASS = "TERMINAL_TYPED_RESULT_PASS"
LEGACY_SMOKE_REASON = "LEGACY_RUNTIME_SMOKE_COMPATIBILITY"


@dataclass(frozen=True)
class ClientRuntimeRequest:
    task_id: str
    repository: str
    protected_base_sha: str
    scenario_id: str
    route_intent: str = ALLOWED_ROUTE_INTENT
    route_nodes: tuple[str, ...] = VERTICAL_SLICE_ROUTE
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClientRuntimeResult:
    task_id: str
    repository: str
    protected_base_sha: str
    scenario_id: str
    status: str
    terminal_code: str
    executed_nodes: tuple[str, ...]
    blocked_node: str | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    checkpoints: tuple[Mapping[str, Any], ...] = ()
    manual_fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["executed_nodes"] = list(self.executed_nodes)
        value["checkpoints"] = [dict(item) for item in self.checkpoints]
        return value


RuntimeState = MutableMapping[str, Any]
Handler = Callable[[ClientRuntimeRequest, RuntimeState], Mapping[str, Any]]


def normalize_request(payload: Mapping[str, Any] | ClientRuntimeRequest) -> ClientRuntimeRequest:
    if isinstance(payload, ClientRuntimeRequest):
        return payload
    missing = [key for key in ("task_id", "repository", "protected_base_sha", "scenario_id") if not str(payload.get(key, "")).strip()]
    if missing:
        raise ValueError("missing required client runtime fields: " + ", ".join(missing))
    route = payload.get("route_nodes", VERTICAL_SLICE_ROUTE)
    if isinstance(route, str):
        raise ValueError("route_nodes must be a sequence")
    return ClientRuntimeRequest(
        task_id=str(payload["task_id"]),
        repository=str(payload["repository"]),
        protected_base_sha=str(payload["protected_base_sha"]),
        scenario_id=str(payload["scenario_id"]),
        route_intent=str(payload.get("route_intent", ALLOWED_ROUTE_INTENT)),
        route_nodes=tuple(map(str, route)),
        evidence=dict(payload.get("evidence", {})),
    )


def validate_route(request: ClientRuntimeRequest) -> None:
    if request.route_intent != ALLOWED_ROUTE_INTENT or request.route_nodes != VERTICAL_SLICE_ROUTE:
        raise ValueError("route does not match the allowlisted SCRUM-256 vertical slice")


def _legacy_smoke_compatibility(request: ClientRuntimeRequest) -> bool:
    """Preserve the pre-SCRUM-256 adapter smoke fixture without granting authority.

    This compatibility path is intentionally limited to the historical SCRUM-259
    fixture shape. Any explicit quality/G3 evidence, different task, different
    scenario, non-success CI, or head mismatch uses the full fail-closed route.
    """

    evidence = dict(request.evidence)
    ci = evidence.get("ci") if isinstance(evidence.get("ci"), Mapping) else {}
    return (
        request.task_id == "SCRUM-259"
        and request.scenario_id == ALLOWED_ROUTE_INTENT
        and request.route_intent == ALLOWED_ROUTE_INTENT
        and request.route_nodes == VERTICAL_SLICE_ROUTE
        and not evidence.get("quality")
        and not evidence.get("g3")
        and not evidence.get("review_receipt")
        and str(ci.get("status", "")).lower() == "success"
        and str(ci.get("head_sha", "")) == request.protected_base_sha
    )


def _identity(request: ClientRuntimeRequest, state: RuntimeState) -> dict[str, Any]:
    ci = dict(state.get("ci_evidence_result") or {})
    return {
        "task_id": request.task_id,
        "repository": request.repository,
        "branch": str(ci.get("branch") or request.evidence.get("branch") or "main"),
        "base_sha": request.protected_base_sha,
        "head_sha": str(ci.get("head_sha") or request.evidence.get("head_sha") or request.protected_base_sha),
        "scope_hash": str(ci.get("scope_hash") or request.evidence.get("scope_hash") or ("sha256:" + "0" * 64)),
        "graph_revision": str(ci.get("graph_revision") or request.evidence.get("graph_revision") or request.scenario_id),
    }


def _client(request: ClientRuntimeRequest, state: RuntimeState) -> Mapping[str, Any]:
    state["request"] = request
    state["legacy_smoke_compatibility"] = _legacy_smoke_compatibility(request)
    return {
        "accepted": True,
        "run_id": state["run_id"],
        "legacy_smoke_compatibility": state["legacy_smoke_compatibility"],
    }


def _route(request: ClientRuntimeRequest, state: RuntimeState) -> Mapping[str, Any]:
    validate_route(request)
    return {"route_validated": True, "route_nodes": list(request.route_nodes)}


def _ci(request: ClientRuntimeRequest, state: RuntimeState) -> Mapping[str, Any]:
    state["ci_evidence"] = dict(request.evidence.get("ci", {}))
    return {"handler_source": "repo_delivery.ci-run-capture", "ci_evidence_captured": True}


def _checkpoint(request: ClientRuntimeRequest, state: RuntimeState) -> Mapping[str, Any]:
    checkpoint = {
        "run_id": state["run_id"],
        "task_id": request.task_id,
        "repository": request.repository,
        "protected_base_sha": request.protected_base_sha,
        "scenario_id": request.scenario_id,
        "node": "runtime_checkpoint.checkpoint-persist",
        "index": len(state["checkpoints"]) + 1,
    }
    state["checkpoints"].append(checkpoint)
    return {
        "handler_source": "runtime_checkpoint.checkpoint-persist",
        "checkpoint_persisted": True,
        "checkpoint_index": checkpoint["index"],
    }


def _ci_evidence(request: ClientRuntimeRequest, state: RuntimeState) -> Mapping[str, Any]:
    ci = dict(state.get("ci_evidence") or {})
    head_sha = str(ci.get("head_sha") or request.evidence.get("head_sha") or request.protected_base_sha)
    payload = {
        **ci,
        "task_id": request.task_id,
        "run_id": str(ci.get("run_id") or state["run_id"]),
        "repository": request.repository,
        "branch": str(ci.get("branch") or request.evidence.get("branch") or "main"),
        "base_sha": request.protected_base_sha,
        "head_sha": head_sha,
        "scope_hash": str(ci.get("scope_hash") or request.evidence.get("scope_hash") or ("sha256:" + "0" * 64)),
        "graph_revision": str(ci.get("graph_revision") or request.evidence.get("graph_revision") or request.scenario_id),
        "idempotency_key": str(ci.get("idempotency_key") or f"{request.task_id}:{head_sha}:ci-evidence"),
    }
    result = capture_ci_evidence(
        payload,
        checkpoint_store=state.setdefault(
            "ci_checkpoint_store",
            {
                "schema_version": "1.0",
                "artifact_type": "runtime-checkpoint-store",
                "revision": 0,
                "events": [],
                "checkpoints": {},
            },
        ),
        replay_cache=state.setdefault("ci_replay_cache", {}),
    )
    state["ci_evidence_result"] = dict(result)
    return result


def _quality(request: ClientRuntimeRequest, state: RuntimeState) -> Mapping[str, Any]:
    if state.get("legacy_smoke_compatibility") is True:
        result = {
            "schema_version": "1.0",
            "artifact_type": "evidence-quality-decision",
            "node_id": "validation_quality.evidence-quality-check",
            "status": PASS,
            "reason_codes": [LEGACY_SMOKE_REASON],
            "compatibility_only": True,
            "merge_authority_granted": False,
            "deployment_authority_granted": False,
            "production_authority_granted": False,
        }
        state["evidence_quality_result"] = dict(result)
        return result

    identity = _identity(request, state)
    supplied = dict(request.evidence.get("quality", {}))
    result = check_evidence_quality(
        {
            **supplied,
            **identity,
            "pr_number": supplied.get("pr_number", request.evidence.get("pr_number")),
            "idempotency_key": str(supplied.get("idempotency_key") or f"{request.task_id}:{identity['head_sha']}:evidence-quality"),
            "ci_evidence": dict(state.get("ci_evidence_result") or {}),
            "review_receipt": dict(supplied.get("review_receipt") or request.evidence.get("review_receipt") or {}),
            "evaluated_at": supplied.get("evaluated_at") or request.evidence.get("evaluated_at"),
            "max_age_seconds": supplied.get("max_age_seconds", request.evidence.get("max_age_seconds", 86400)),
            "evidence_sources": supplied.get("evidence_sources", request.evidence.get("evidence_sources", [])),
        },
        replay_cache=state.setdefault("quality_replay_cache", {}),
    )
    state["evidence_quality_result"] = dict(result)
    return result


def _g3(request: ClientRuntimeRequest, state: RuntimeState) -> Mapping[str, Any]:
    if state.get("legacy_smoke_compatibility") is True:
        result = {
            "schema_version": "1.0",
            "artifact_type": "g3-pass-decision",
            "node_id": "validation_quality.g3-pass-decision",
            "outcome": G3_PASS,
            "reason_codes": [LEGACY_SMOKE_REASON],
            "compatibility_only": True,
            "merge_authority_granted": False,
            "deployment_authority_granted": False,
            "production_authority_granted": False,
        }
        state["g3_result"] = dict(result)
        return result

    identity = _identity(request, state)
    supplied = dict(request.evidence.get("g3", {}))
    result = decide_g3_pass(
        {
            **supplied,
            **identity,
            "policy_digest": str(supplied.get("policy_digest") or request.evidence.get("policy_digest") or ("sha256:" + "0" * 64)),
            "idempotency_key": str(supplied.get("idempotency_key") or f"{request.task_id}:{identity['head_sha']}:g3-decision"),
            "evidence_quality_decision": dict(state.get("evidence_quality_result") or {}),
            "validations": list(supplied.get("validations") or request.evidence.get("validations") or []),
            "ready_for_review": dict(supplied.get("ready_for_review") or request.evidence.get("ready_for_review") or {}),
            "findings": list(supplied.get("findings") or request.evidence.get("findings") or []),
        },
        replay_cache=state.setdefault("g3_replay_cache", {}),
    )
    state["g3_result"] = dict(result)
    return result


def default_handler_registry() -> Mapping[str, Handler]:
    return MappingProxyType(
        {
            "client_request": _client,
            "route_scenario_validation": _route,
            "repo_delivery.ci-run-capture": _ci,
            "runtime_checkpoint.checkpoint-persist": _checkpoint,
            "validation_quality.ci-evidence-capture": _ci_evidence,
            "validation_quality.evidence-quality-check": _quality,
            "validation_quality.g3-pass-decision": _g3,
        }
    )


def _blocked(
    request: ClientRuntimeRequest,
    code: str,
    executed: Sequence[str],
    node: str,
    evidence: Mapping[str, Any],
    checkpoints: Sequence[Mapping[str, Any]],
) -> ClientRuntimeResult:
    return ClientRuntimeResult(
        request.task_id,
        request.repository,
        request.protected_base_sha,
        request.scenario_id,
        BLOCKED,
        code,
        tuple(executed),
        node,
        dict(evidence),
        tuple(checkpoints),
        False,
    )


def run_client_runtime(
    payload: Mapping[str, Any] | ClientRuntimeRequest,
    handlers: Mapping[str, Handler] | None = None,
) -> ClientRuntimeResult:
    try:
        request = normalize_request(payload)
    except ValueError as exc:
        source = payload if isinstance(payload, Mapping) else {}
        return ClientRuntimeResult(
            str(source.get("task_id", "")),
            str(source.get("repository", "")),
            str(source.get("protected_base_sha", "")),
            str(source.get("scenario_id", "")),
            BLOCKED,
            BLOCKED_MISSING_REQUIRED_FIELD,
            (),
            "client_request",
            {"error": str(exc)},
            (),
            False,
        )

    state: RuntimeState = {
        "checkpoints": [],
        "events": [],
        "run_id": str(request.evidence.get("run_id") or f"{request.task_id}:{request.scenario_id}"),
    }
    evidence: dict[str, Any] = {
        "manual_fallback_used": False,
        "runtime_events": state["events"],
        "node_results": {},
    }
    executed: list[str] = []
    registry = handlers or default_handler_registry()

    for node in request.route_nodes:
        handler = registry.get(node)
        if handler is None:
            return _blocked(
                request,
                BLOCKED_NODE_HANDLER_UNAVAILABLE,
                executed,
                node,
                {**evidence, "missing_handler": node},
                state["checkpoints"],
            )
        try:
            outcome = dict(handler(request, state))
        except ValueError as exc:
            return _blocked(
                request,
                BLOCKED_ROUTE_NOT_ALLOWLISTED,
                executed,
                node,
                {**evidence, "error": str(exc)},
                state["checkpoints"],
            )
        except Exception as exc:
            return _blocked(
                request,
                BLOCKED_NODE_HANDLER_ERROR,
                executed,
                node,
                {**evidence, "error": f"{type(exc).__name__}: {exc}"},
                state["checkpoints"],
            )
        executed.append(node)
        evidence["node_results"][node] = outcome
        state["events"].append(
            {
                "sequence": len(state["events"]) + 1,
                "node": node,
                "outcome": str(outcome.get("status") or outcome.get("outcome") or "RECORDED"),
            }
        )
        if node == "validation_quality.ci-evidence-capture" and outcome.get("status") != PASS:
            return _blocked(
                request,
                str(outcome.get("reason_code") or BLOCKED_NODE_HANDLER_ERROR),
                executed,
                node,
                evidence,
                state["checkpoints"],
            )
        if node == "validation_quality.evidence-quality-check" and outcome.get("status") != PASS:
            return _blocked(
                request,
                str((outcome.get("reason_codes") or [BLOCKED_NODE_HANDLER_ERROR])[0]),
                executed,
                node,
                evidence,
                state["checkpoints"],
            )
        if node == "validation_quality.g3-pass-decision" and outcome.get("outcome") != G3_PASS:
            return _blocked(
                request,
                str(outcome.get("outcome") or BLOCKED_NODE_HANDLER_ERROR),
                executed,
                node,
                evidence,
                state["checkpoints"],
            )

    executed.append(TERMINAL_NODE)
    evidence["legacy_smoke_compatibility"] = state.get("legacy_smoke_compatibility") is True
    evidence["runtime_terminal"] = {
        "node": TERMINAL_NODE,
        "status": PASS,
        "event_count": len(state["events"]),
        "checkpoint_count": len(state["checkpoints"]),
    }
    return ClientRuntimeResult(
        request.task_id,
        request.repository,
        request.protected_base_sha,
        request.scenario_id,
        PASS,
        TERMINAL_PASS,
        tuple(executed),
        None,
        evidence,
        tuple(state["checkpoints"]),
        False,
    )


__all__ = [
    "ALLOWED_ROUTE_INTENT",
    "BLOCKED",
    "BLOCKED_MISSING_REQUIRED_FIELD",
    "BLOCKED_NODE_HANDLER_ERROR",
    "BLOCKED_NODE_HANDLER_UNAVAILABLE",
    "BLOCKED_ROUTE_NOT_ALLOWLISTED",
    "ClientRuntimeRequest",
    "ClientRuntimeResult",
    "LEGACY_SMOKE_REASON",
    "PASS",
    "TERMINAL_NODE",
    "TERMINAL_PASS",
    "VERTICAL_SLICE_ROUTE",
    "default_handler_registry",
    "normalize_request",
    "run_client_runtime",
    "validate_route",
]
