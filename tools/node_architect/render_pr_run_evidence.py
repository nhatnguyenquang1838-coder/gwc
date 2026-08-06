#!/usr/bin/env python3
"""Render and validate the bounded GWC autonomous-run PR evidence block."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .build_run_graph import render_mermaid

BEGIN_MARKER = "<!-- GWC:AUTONOMOUS-RUN:EVIDENCE:BEGIN -->"
END_MARKER = "<!-- GWC:AUTONOMOUS-RUN:EVIDENCE:END -->"
MACHINE_MARKER_PREFIX = "<!-- gwc:autonomous-run-evidence "
MACHINE_MARKER_RE = re.compile(
    r"<!-- gwc:autonomous-run-evidence "
    r"run_id=([^ ]+) task=([^ ]+) head=([0-9a-f]{40}) "
    r"graph=(sha256:[0-9a-f]{64}) story=(sha256:[0-9a-f]{64}) "
    r"evidence=(sha256:[0-9a-f]{64}) -->"
)


class ManagedBlockError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code
        self.message = message


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def build_managed_block(graph: Mapping[str, Any], story: Mapping[str, Any], *, validation: Mapping[str, Any] | None = None, g4_readiness: Mapping[str, Any] | None = None) -> tuple[str, str]:
    validation_value = dict(validation or {})
    g4_value = dict(g4_readiness or {})
    evidence_digest = _canonical_digest({
        "run_id": graph["run_id"], "task_id": graph["task_id"], "head_sha": graph["head_sha"],
        "graph_digest": graph["graph_digest"], "story_digest": story["story_digest"],
        "validation": validation_value, "g4_readiness": g4_value,
    })
    marker = (
        f"{MACHINE_MARKER_PREFIX}run_id={graph['run_id']} task={graph['task_id']} head={graph['head_sha']} "
        f"graph={graph['graph_digest']} story={story['story_digest']} evidence={evidence_digest} -->"
    )
    lines = [
        BEGIN_MARKER, marker, "## GWC Autonomous Run Evidence", "", "### Run identity", "",
        "| Field | Value |", "|---|---|",
        f"| Run ID | `{_cell(graph['run_id'])}` |",
        f"| Task | `{_cell(graph['task_id'])}` |",
        f"| Repository | `{_cell(graph['repository'])}` |",
        f"| Base | `{_cell(graph['base_ref'])}@{_cell(graph['base_sha'])}` |",
        f"| Head | `{_cell(graph['head_ref'])}@{_cell(graph['head_sha'])}` |",
        f"| Graph revision | `{_cell(graph['graph_revision'])}` |",
        f"| Graph digest | `{_cell(graph['graph_digest'])}` |",
        f"| Story digest | `{_cell(story['story_digest'])}` |",
        f"| Evidence digest | `{evidence_digest}` |",
        "", "### Gate status — G0 to G6", "",
        "| Gate | Status | Purpose | Evidence | Authority explicitly not granted |",
        "|---|---|---|---|---|",
    ]
    for gate in story["gates"]:
        lines.append(
            f"| {_cell(gate['gate'])} | **{_cell(gate['status'])}** | {_cell(gate['purpose'])} | "
            f"{_cell(', '.join(gate['evidence_refs']) or 'none recorded')} | {_cell(', '.join(gate['authority_not_granted']))} |"
        )
    lines.extend(["", "### Node participation", "", "| Seq | Gate | Type | Canonical participant | Purpose | Action | Outcome | Output evidence | Next route |", "|---:|---|---|---|---|---|---|---|---|"])
    for node in graph["nodes"]:
        lines.append(
            f"| {node['sequence']} | {_cell(node['gate'])} | {_cell(node['participant_type'])} | `{_cell(node['canonical_id'])}` | "
            f"{_cell(node['purpose'])} | {_cell(node['action'])} | {_cell(node['outcome'])} | "
            f"{_cell(', '.join(node['output_evidence']) or 'none recorded')} | {_cell(node['next_route'] or 'terminal')} |"
        )
    lines.extend(["", "### Run-scoped Node Architect graph", "", "```mermaid", render_mermaid(graph).rstrip(), "```", "", "### G0→G6 storyteller", ""])
    for gate in story["gates"]:
        lines.extend([f"#### {gate['gate']} — {gate['status']}", "", gate["narrative"], ""])
    lines.extend(["### Validation and review", ""])
    if validation_value:
        lines.extend(["| Field | Value |", "|---|---|"])
        for key in sorted(validation_value):
            lines.append(f"| {_cell(key)} | {_cell(validation_value[key])} |")
    else:
        lines.append("No validation or review evidence was supplied for this rendering.")
    lines.extend(["", "### G4 readiness", ""])
    if g4_value:
        lines.extend(["| Field | Value |", "|---|---|"])
        for key in sorted(g4_value):
            lines.append(f"| {_cell(key)} | {_cell(g4_value[key])} |")
    else:
        lines.append("G4 readiness is not established. Rendering evidence does not grant merge authority.")
    g5 = next(item for item in story["gates"] if item["gate"] == "G5_DEPLOY")
    g6 = next(item for item in story["gates"] if item["gate"] == "G6_PRODUCTION_DATA")
    lines.extend([
        "", "### G5 / G6 treatment", "",
        f"- G5_DEPLOY: **{g5['status']}** — exact merge-SHA verification is required when applicable; rendering does not authorize manual deployment.",
        f"- G6_PRODUCTION_DATA: **{g6['status']}** — absence is not permission and only an exact G6 scope can authorize production operations.",
        "", END_MARKER,
    ])
    return "\n".join(lines), evidence_digest


def _marker_counts(body: str) -> tuple[int, int]:
    return body.count(BEGIN_MARKER), body.count(END_MARKER)


def upsert_managed_block(existing_body: str | None, block: str) -> tuple[str, str]:
    body = existing_body or ""
    begin_count, end_count = _marker_counts(body)
    if begin_count != end_count or begin_count > 1:
        raise ManagedBlockError("AUTONOMOUS_PR_MARKER_MALFORMED", "PR body must contain either zero or one balanced managed evidence block")
    if BEGIN_MARKER not in block or END_MARKER not in block:
        raise ManagedBlockError("AUTONOMOUS_PR_BLOCK_INVALID", "new managed block is missing bounded markers")
    if begin_count == 0:
        updated = body.rstrip()
        if updated:
            updated += "\n\n"
        updated += block.strip() + "\n"
    else:
        start = body.index(BEGIN_MARKER)
        end = body.index(END_MARKER, start) + len(END_MARKER)
        updated = body[:start] + block.strip() + body[end:]
        if not updated.endswith("\n"):
            updated += "\n"
    return updated, sha256_text(updated)


def extract_managed_metadata(body: str) -> dict[str, str]:
    begin_count, end_count = _marker_counts(body)
    if begin_count != 1 or end_count != 1:
        raise ManagedBlockError("AUTONOMOUS_PR_EVIDENCE_MISSING_OR_MALFORMED", "exactly one managed evidence block is required")
    start = body.index(BEGIN_MARKER)
    end = body.index(END_MARKER, start) + len(END_MARKER)
    block = body[start:end]
    match = MACHINE_MARKER_RE.search(block)
    if not match:
        raise ManagedBlockError("AUTONOMOUS_PR_EVIDENCE_MARKER_INVALID", "machine-readable run evidence marker is missing or malformed")
    return {
        "run_id": match.group(1), "task_id": match.group(2), "head_sha": match.group(3),
        "graph_digest": match.group(4), "story_digest": match.group(5), "evidence_digest": match.group(6),
        "managed_block_digest": sha256_text(block), "pr_body_digest": sha256_text(body),
    }


def validate_managed_block(body: str, *, expected_head_sha: str, expected_graph_digest: str | None = None, expected_story_digest: str | None = None, expected_evidence_digest: str | None = None) -> list[str]:
    try:
        metadata = extract_managed_metadata(body)
    except ManagedBlockError as exc:
        return [str(exc)]
    errors: list[str] = []
    if metadata["head_sha"] != expected_head_sha:
        errors.append("AUTONOMOUS_PR_HEAD_DRIFT: managed evidence is not bound to the current PR head")
    for key, expected in (("graph_digest", expected_graph_digest), ("story_digest", expected_story_digest), ("evidence_digest", expected_evidence_digest)):
        if expected and metadata[key] != expected:
            errors.append(f"AUTONOMOUS_PR_EVIDENCE_DRIFT: {key} does not match expected evidence")
    return errors


__all__ = ["BEGIN_MARKER", "END_MARKER", "ManagedBlockError", "build_managed_block", "extract_managed_metadata", "sha256_text", "upsert_managed_block", "validate_managed_block"]
