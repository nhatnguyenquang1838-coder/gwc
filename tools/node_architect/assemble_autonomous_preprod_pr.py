#!/usr/bin/env python3
"""Assemble a Draft PR body for the autonomous pre-prod delivery path.
Wraps the SCRUM-271 graph/story renderer (``render_pr_run_evidence``) to produce
the managed, digest-bounded PR description, and enforces the hard guardrails:
* The PR base must be ``pre-prod``; ``main`` is forbidden.
* The managed block must be bound to the exact current PR head SHA.
* The autonomous route identity is materialized as an exact-head managed marker.
* No deploy, release, or production authority is granted.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .render_pr_run_evidence import (
    BEGIN_MARKER,
    END_MARKER,
    build_managed_block,
    sha256_text,
    upsert_managed_block,
)

FORBIDDEN_BASES = {"main"}
REQUIRED_BASE = "pre-prod"
ROUTE_ID = "AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN"
_ROUTE_RE = re.compile(r"<!-- gwc:autonomous-preprod-route route=[^ ]+ base=[^ ]+ head=[0-9a-f]{40} -->")


def _route_marker(*, base_ref: str, head_sha: str) -> str:
    return f"<!-- gwc:autonomous-preprod-route route={ROUTE_ID} base={base_ref} head={head_sha} -->"


def _upsert_route_marker(existing_body: str | None, marker: str) -> str:
    body = existing_body or ""
    if _ROUTE_RE.search(body):
        return _ROUTE_RE.sub(marker, body, count=1)
    body = body.rstrip()
    sep = "\n\n" if body else ""
    return f"{body}{sep}{marker}\n"


def assemble_pr_body(
    *,
    graph: Mapping[str, Any],
    story: Mapping[str, Any],
    validation: Mapping[str, Any] | None = None,
    g4_readiness: Mapping[str, Any] | None = None,
    existing_body: str | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    base_ref = str(graph.get("base_ref", ""))
    if base_ref != REQUIRED_BASE:
        reasons.append("AUTONOMOUS_PR_BASE_NOT_PREPROD")
    if base_ref in FORBIDDEN_BASES:
        reasons.append("AUTONOMOUS_PR_MAIN_BASE_FORBIDDEN")

    head_sha = str(graph.get("head_sha", ""))
    if not (isinstance(head_sha, str) and len(head_sha) == 40 and all(c in "0123456789abcdef" for c in head_sha)):
        reasons.append("AUTONOMOUS_PR_HEAD_SHA_INVALID")

    block, evidence_digest = build_managed_block(
        graph, story, validation=validation, g4_readiness=g4_readiness
    )
    if BEGIN_MARKER not in block or END_MARKER not in block:
        reasons.append("AUTONOMOUS_PR_BLOCK_INVALID")

    marker = _route_marker(base_ref=base_ref, head_sha=head_sha)
    body_with_route = _upsert_route_marker(existing_body, marker)
    updated_body, body_digest = upsert_managed_block(body_with_route, block)

    if marker not in updated_body:
        reasons.append("AUTONOMOUS_PR_ROUTE_MARKER_MISSING")

    outcome = "PR_BODY_READY" if not reasons else "REJECTED"
    result = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-preprod-pr-body",
        "run_id": graph.get("run_id"),
        "task_id": graph.get("task_id"),
        "route_id": ROUTE_ID,
        "route_marker": marker,
        "base_ref": base_ref,
        "head_sha": head_sha,
        "pr_body": updated_body,
        "pr_body_digest": body_digest,
        "managed_block_digest": graph.get("graph_digest", sha256_text(block)),
        "evidence_digest": evidence_digest,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "outcome": outcome,
        "reason_codes": sorted(set(reasons)) or ["AUTONOMOUS_PR_BODY_SAFE"],
    }
    return result


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--story", type=Path, required=True)
    parser.add_argument("--validation", type=Path)
    parser.add_argument("--g4-readiness", type=Path)
    parser.add_argument("--existing-body", type=Path)
    parser.add_argument("--out", type=Path, help="Write rendered PR body to this path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    graph = _load_json(args.graph)
    story = _load_json(args.story)
    validation = _load_json(args.validation) if args.validation else None
    g4 = _load_json(args.g4_readiness) if args.g4_readiness else None
    existing = args.existing_body.read_text(encoding="utf-8") if args.existing_body else None

    result = assemble_pr_body(graph=graph, story=story, validation=validation, g4_readiness=g4, existing_body=existing)
    if args.out:
        args.out.write_text(result["pr_body"], encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['outcome']}: {', '.join(result['reason_codes'])}")
    return 0 if result["outcome"] == "PR_BODY_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
