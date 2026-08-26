#!/usr/bin/env python3
"""Canonical semantic Node Architect lifecycle: ENTRY -> DO -> READBACK -> EXIT -> NEXT.

This runtime composes existing route packs, the canonical semantic source
resolver, explicit evaluator bindings, canonical readback adapters, and the
existing NodeEvidenceLedger. It lazy-resolves one current node at a time and
stops immediately on missing semantics, readback, graph safety, provider block,
or evidence conflict. It never grants authority itself.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from .gate_node_routes import ordered_nodes_for_event, select_route_pack
from .node_evidence_ledger import EvidenceConflict, NodeEvidenceLedger, digest_payload
from .semantic_dispatcher import SemanticEvaluatorBinding, dispatch_semantic_node
from .semantic_source_resolver import resolve_semantic_source

ReadbackHandler = Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]
SourceResolver = Callable[..., Mapping[str, Any]]

_REQUIRED_EVENT_FIELDS = (
    "task_id",
    "run_id",
    "gate",
    "scenario",
    "repository",
    "branch",
    "base_sha",
    "exact_revision",
    "scope_hash",
    "idempotency_key",
    "occurred_at",
)


def _terminal(
    *,
    status: str,
    reason_code: str,
    route_pack: str | None,
    visited: list[str] | None = None,
    executed: list[str] | None = None,
    node_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "reason_code": reason_code,
        "route_pack": route_pack,
        "visited_node_ids": list(visited or []),
        "semantic_executed_node_ids": list(executed or []),
        "node_results": list(node_results or []),
        "authority_granted": False,
        "executed_effects": [],
    }


def _runtime_disposition_block_reason(semantic_result: Mapping[str, Any]) -> str | None:
    nested = semantic_result.get("result")
    if not isinstance(nested, Mapping):
        return None
    disposition = nested.get("runtime_disposition")
    if disposition in (None, "CONTINUE"):
        return None
    return str(nested.get("reason_code") or "SEMANTIC_RUNTIME_DISPOSITION_BLOCKED")


def _normalize_readback(
    node: Mapping[str, Any],
    semantic_result: Mapping[str, Any],
    event: Mapping[str, Any],
    handler: ReadbackHandler | None,
) -> dict[str, Any]:
    if semantic_result.get("semantic_execution") is not True:
        return {
            "status": "NOT_RUN",
            "reason_code": str(semantic_result.get("reason_code") or "SEMANTIC_EXECUTION_BLOCKED"),
        }
    disposition_reason = _runtime_disposition_block_reason(semantic_result)
    if disposition_reason is not None:
        return {
            "status": "NOT_RUN",
            "reason_code": disposition_reason,
        }
    if handler is None:
        return {
            "status": "BLOCKED",
            "reason_code": "SEMANTIC_READBACK_UNAVAILABLE",
        }
    try:
        raw = handler(node, semantic_result, event)
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "reason_code": "SEMANTIC_READBACK_ERROR",
            "error": f"{type(exc).__name__}: {exc}",
        }
    if not isinstance(raw, Mapping):
        return {
            "status": "BLOCKED",
            "reason_code": "SEMANTIC_READBACK_INVALID_RESULT",
        }
    result = dict(raw)
    if result.get("status") != "VERIFIED":
        return {
            **result,
            "status": "BLOCKED",
            "reason_code": str(result.get("reason_code") or "SEMANTIC_READBACK_NOT_VERIFIED"),
        }
    return result


def _ledger_for(
    *,
    root: Path,
    event: Mapping[str, Any],
    node_id: str,
) -> NodeEvidenceLedger:
    return NodeEvidenceLedger(
        root=root,
        task_id=str(event["task_id"]),
        run_id=str(event["run_id"]),
        node_id=node_id,
        repository=str(event["repository"]),
        branch=str(event["branch"]),
        base_sha=str(event["base_sha"]),
        head_sha=str(event["exact_revision"]),
        scope_hash=str(event["scope_hash"]),
        idempotency_key=f"{event['idempotency_key']}:{node_id}",
        occurred_at=str(event["occurred_at"]),
    )


def _record_node_lifecycle(
    *,
    ledger: NodeEvidenceLedger,
    event: Mapping[str, Any],
    route_pack: str,
    source: Mapping[str, Any],
    semantic_result: Mapping[str, Any],
    readback: Mapping[str, Any],
    blocked_reason: str | None,
    next_node_id: str | None,
) -> None:
    input_payload = event.get("input_payload") if isinstance(event.get("input_payload"), Mapping) else {}
    ledger.record_start({
        "stage": "ENTRY",
        "gate": event["gate"],
        "scenario": event["scenario"],
        "route_pack": route_pack,
        "exact_revision": event["exact_revision"],
        "input_digest": digest_payload(dict(input_payload)),
    })
    ledger.record_decision({
        "stage": "ENTRY_DECISION",
        "semantic_source": dict(source),
        "decision": "BLOCK" if source.get("runtime_eligible") is not True else "DISPATCH",
    })
    ledger.record_result({
        "stage": "DO",
        "semantic_result": dict(semantic_result),
    })
    ledger.record_readback({
        "stage": "READBACK",
        **dict(readback),
    })
    ledger.record_checkpoint({
        "stage": "EXIT",
        "status": "BLOCKED" if blocked_reason else "COMPLETE",
        "reason_code": blocked_reason or "SEMANTIC_NODE_COMPLETE",
        "exact_revision": event["exact_revision"],
    })
    ledger.record_next_route({
        "stage": "NEXT",
        "decision": "STOP" if blocked_reason else ("CONTINUE" if next_node_id else "COMPLETE"),
        "next_node_id": next_node_id if not blocked_reason else None,
        "reason_code": blocked_reason or ("SEMANTIC_NEXT_NODE" if next_node_id else "SEMANTIC_ROUTE_COMPLETE"),
    })


def run_semantic_route_event(
    event: Mapping[str, Any],
    registry: Mapping[str, Any],
    graph: Mapping[str, Any],
    *,
    bindings: Mapping[str, SemanticEvaluatorBinding],
    readback_handlers: Mapping[str, ReadbackHandler],
    source_root: Path | str = Path("."),
    evidence_root: Path | str = Path("."),
    source_resolver: SourceResolver = resolve_semantic_source,
) -> dict[str, Any]:
    """Run one route event through lazy semantic node lifecycle execution."""
    missing = [field for field in _REQUIRED_EVENT_FIELDS if not event.get(field)]
    if missing:
        return _terminal(
            status="SEMANTIC_INVALID_EVENT",
            reason_code="SEMANTIC_EVENT_IDENTITY_MISSING:" + ",".join(missing),
            route_pack=None,
        )

    route_pack = select_route_pack(str(event["scenario"]))
    if route_pack is None:
        return _terminal(
            status="SEMANTIC_NO_APPLICABLE_ROUTE",
            reason_code="SEMANTIC_ROUTE_UNKNOWN_SCENARIO",
            route_pack=None,
        )
    if not isinstance(graph, Mapping):
        return _terminal(
            status="SEMANTIC_ROUTE_BLOCKED",
            reason_code="SEMANTIC_RUNTIME_GRAPH_MISSING",
            route_pack=route_pack,
        )

    try:
        ordered = ordered_nodes_for_event(
            registry,
            gate=str(event["gate"]),
            scenario=str(event["scenario"]),
            graph=graph,
        )
    except ValueError as exc:
        return _terminal(
            status="SEMANTIC_ROUTE_BLOCKED",
            reason_code=str(exc),
            route_pack=route_pack,
        )

    if not ordered:
        return _terminal(
            status="SEMANTIC_NO_APPLICABLE_NODES",
            reason_code="SEMANTIC_ROUTE_HAS_NO_GATE_APPLICABLE_NODES",
            route_pack=route_pack,
        )

    by_id = {
        str(node.get("id")): node
        for node in registry.get("nodes", [])
        if isinstance(node, Mapping) and isinstance(node.get("id"), str)
    }
    visited: list[str] = []
    semantic_executed: list[str] = []
    node_results: list[dict[str, Any]] = []
    source_root_path = Path(source_root)
    evidence_root_path = Path(evidence_root)
    input_payload = event.get("input_payload") if isinstance(event.get("input_payload"), Mapping) else {}

    for index, node_id in enumerate(ordered):
        node = by_id[node_id]
        visited.append(node_id)
        next_node_id = ordered[index + 1] if index + 1 < len(ordered) else None
        try:
            source = dict(source_resolver(node, root=source_root_path))
        except Exception as exc:
            source = {
                "status": "INVALID_SOURCE_BINDING",
                "runtime_eligible": False,
                "reason_code": "SEMANTIC_SOURCE_RESOLUTION_ERROR",
                "evaluator_path": None,
                "error": f"{type(exc).__name__}: {exc}",
            }

        semantic_result = dispatch_semantic_node(
            node,
            source,
            dict(input_payload),
            bindings=bindings,
        )
        if semantic_result.get("semantic_execution") is True:
            semantic_executed.append(node_id)

        disposition_reason = _runtime_disposition_block_reason(semantic_result)
        readback = _normalize_readback(
            node,
            semantic_result,
            event,
            readback_handlers.get(node_id),
        )
        blocked_reason: str | None = None
        if semantic_result.get("semantic_execution") is not True:
            blocked_reason = str(semantic_result.get("reason_code") or "SEMANTIC_EXECUTION_BLOCKED")
        elif disposition_reason is not None:
            blocked_reason = disposition_reason
        elif readback.get("status") != "VERIFIED":
            blocked_reason = str(readback.get("reason_code") or "SEMANTIC_READBACK_NOT_VERIFIED")

        try:
            _record_node_lifecycle(
                ledger=_ledger_for(root=evidence_root_path, event=event, node_id=node_id),
                event=event,
                route_pack=route_pack,
                source=source,
                semantic_result=semantic_result,
                readback=readback,
                blocked_reason=blocked_reason,
                next_node_id=next_node_id,
            )
        except EvidenceConflict as exc:
            return _terminal(
                status="SEMANTIC_ROUTE_BLOCKED",
                reason_code="SEMANTIC_EVIDENCE_CONFLICT",
                route_pack=route_pack,
                visited=visited,
                executed=semantic_executed,
                node_results=node_results + [{
                    "node_id": node_id,
                    "semantic_source": source,
                    "semantic_result": semantic_result,
                    "readback": readback,
                    "evidence_error": str(exc),
                }],
            )

        node_results.append({
            "node_id": node_id,
            "semantic_source": source,
            "semantic_result": semantic_result,
            "readback": readback,
        })
        if blocked_reason:
            return _terminal(
                status="SEMANTIC_ROUTE_BLOCKED",
                reason_code=blocked_reason,
                route_pack=route_pack,
                visited=visited,
                executed=semantic_executed,
                node_results=node_results,
            )

    return _terminal(
        status="SEMANTIC_ROUTE_COMPLETE",
        reason_code="SEMANTIC_ROUTE_COMPLETE",
        route_pack=route_pack,
        visited=visited,
        executed=semantic_executed,
        node_results=node_results,
    )


__all__ = [
    "ReadbackHandler",
    "SourceResolver",
    "run_semantic_route_event",
]
