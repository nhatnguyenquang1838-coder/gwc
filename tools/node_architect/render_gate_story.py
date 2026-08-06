#!/usr/bin/env python3
"""Generate a factual G0→G6 story from canonical run graph evidence."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .build_run_graph import GATES

GATE_PURPOSES = {
    "G0_CONTEXT": "xác nhận đúng task, repository, protected base, instruction sources và blocker trước mọi write",
    "G1_ALIGNMENT": "chốt mục tiêu, phương án, scope, risk, acceptance criteria và non-goals có thể kiểm chứng",
    "G2_EXECUTION": "thực thi thay đổi chỉ trong guarded branch và permission envelope đã được duyệt",
    "G3_PR": "đóng gói Draft PR, validation, exact-head review và closure evidence",
    "G4_MERGE": "xác minh human authority và evidence hiện hành trước merge đúng head SHA",
    "G5_DEPLOY": "xác minh trạng thái sau merge cho exact merge SHA; không tự suy diễn deploy authority",
    "G6_PRODUCTION_DATA": "kiểm soát riêng production data/configuration, migration, credential và secret operations",
}
AUTHORITY_NOT_GRANTED = {
    "G0_CONTEXT": ["repository_write", "merge", "deploy", "production_operation"],
    "G1_ALIGNMENT": ["repository_write", "merge", "deploy", "production_operation"],
    "G2_EXECUTION": ["protected_branch_write", "merge", "deploy", "production_operation"],
    "G3_PR": ["merge", "deploy", "production_operation"],
    "G4_MERGE": ["manual_deploy", "release", "runtime_reload", "production_operation"],
    "G5_DEPLOY": ["manual_environment_change_without_g5_authority", "production_operation"],
    "G6_PRODUCTION_DATA": ["actions_outside_exact_g6_scope"],
}


def _digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_gate_status(value: Any) -> str | None:
    if value is None:
        return None
    if value not in {"passed", "executed", "blocked", "not_executed", "not_applicable"}:
        raise ValueError(f"unsupported gate status: {value}")
    return str(value)


def build_gate_story(graph: Mapping[str, Any], *, gate_statuses: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Build a seven-gate story; absent execution is explicit, never implied."""
    statuses = dict(gate_statuses or {})
    unknown = sorted(set(statuses) - set(GATES))
    if unknown:
        raise ValueError(f"unknown gate status keys: {', '.join(unknown)}")
    gates: list[dict[str, Any]] = []
    all_nodes = list(graph.get("nodes", []))
    for gate in GATES:
        participants = [node for node in all_nodes if node.get("gate") == gate]
        explicit = _normalize_gate_status(statuses.get(gate))
        if explicit:
            status = explicit
        elif any(node.get("status") == "blocked" for node in participants):
            status = "blocked"
        elif participants and all(node.get("status") == "not_applicable" for node in participants):
            status = "not_applicable"
        elif participants and all(node.get("status") in {"passed", "executed"} for node in participants):
            status = "passed"
        elif participants:
            status = "executed"
        else:
            status = "not_executed"
        node_ids: list[str] = []
        evidence: set[str] = set()
        descriptions: list[str] = []
        for node in participants:
            canonical = str(node["canonical_id"])
            if canonical not in node_ids:
                node_ids.append(canonical)
            evidence.update(str(item) for item in node.get("entry_evidence", []))
            evidence.update(str(item) for item in node.get("output_evidence", []))
            descriptions.append(
                f"{canonical} ({node['participant_type']}) đọc {', '.join(node.get('entry_evidence', [])) or 'không có entry evidence được ghi nhận'}, "
                f"thực hiện {node['action']}, kết thúc với {node['outcome']} và tạo {', '.join(node.get('output_evidence', [])) or 'không có output evidence được ghi nhận'}"
            )
        purpose = GATE_PURPOSES[gate]
        if not participants:
            narrative = (
                f"{gate} nhằm {purpose}. Run này không có runtime event cho gate; trạng thái được ghi rõ là "
                f"{status}, vì vậy không node hoặc gate action nào được suy diễn là đã chạy."
            )
        else:
            narrative = (
                f"{gate} nhằm {purpose}. Các participant thực tế: {', '.join(node_ids)}. "
                f"{'; '.join(descriptions)}. Gate được ghi nhận {status}; quyết định tiếp tục hoặc dừng phải dựa trên chính evidence này."
            )
        gates.append({
            "gate": gate, "purpose": purpose, "status": status,
            "participating_nodes": node_ids, "narrative": narrative,
            "evidence_refs": sorted(evidence), "authority_not_granted": AUTHORITY_NOT_GRANTED[gate],
        })
    terminal_status = graph.get("terminal_status", "INCOMPLETE")
    story: dict[str, Any] = {
        "schema_version": "1.0", "artifact_type": "gate-story",
        "run_id": graph["run_id"], "task_id": graph["task_id"], "repository": graph["repository"],
        "head_sha": graph["head_sha"], "graph_digest": graph["graph_digest"], "gates": gates,
        "terminal_summary": (
            f"Run {graph['run_id']} cho {graph['task_id']} kết thúc ở trạng thái {terminal_status}. "
            "Story chỉ mô tả node và gate action có canonical event; not_executed và not_applicable không được xem là PASS ngầm định."
        ),
    }
    story["story_digest"] = _digest(story)
    return story


__all__ = ["build_gate_story"]
