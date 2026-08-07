#!/usr/bin/env python3
"""Fixture-safe orchestration skeleton for GWC autonomous pre-prod evidence.

SCRUM-271 intentionally stops before arbitrary Jira task execution, AI coding,
standing-policy authority issuance, branch creation, PR creation, merge, deploy,
or production operations. The runtime consumes canonical events, produces the
run graph, G0→G6 story, and bounded PR-description evidence, and fails closed
when the requested PR base is ``main`` or the manifest identity does not match
the exact repository/base selected by the caller.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from .build_run_graph import RunGraphError, build_run_graph
from .render_gate_story import build_gate_story
from .render_pr_run_evidence import build_managed_block, upsert_managed_block

MAIN_TARGET_FORBIDDEN = "AUTONOMOUS_MAIN_TARGET_FORBIDDEN"
REPOSITORY_BINDING_MISMATCH = "AUTONOMOUS_REPOSITORY_BINDING_MISMATCH"
BASE_SHA_MISMATCH = "AUTONOMOUS_BASE_SHA_MISMATCH"
PASS = "PASS"
BLOCKED = "BLOCKED"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _blocked_result(manifest: Mapping[str, Any], code: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_type": "autonomous-preprod-runtime-result",
        "run_id": manifest.get("run_id"),
        "task_id": manifest.get("task_id"),
        "repository": manifest.get("repository"),
        "status": BLOCKED,
        "terminal_code": code,
        "message": message,
        "side_effects_performed": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def execute_fixture_run(
    manifest: Mapping[str, Any],
    *,
    existing_pr_body: str | None = None,
    expected_repository: str | None = None,
    expected_base_sha: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None, str | None, str | None]:
    """Execute the evidence-only vertical slice and return typed artifacts."""
    if not isinstance(manifest, Mapping):
        result = _blocked_result({}, "AUTONOMOUS_MANIFEST_INVALID", "manifest must be an object")
        return result, None, None, None, None
    if expected_repository is not None and manifest.get("repository") != expected_repository:
        result = _blocked_result(
            manifest,
            REPOSITORY_BINDING_MISMATCH,
            "manifest repository does not match the exact repository selected by the caller",
        )
        return result, None, None, None, None
    if expected_base_sha is not None and manifest.get("base_sha") != expected_base_sha:
        result = _blocked_result(
            manifest,
            BASE_SHA_MISMATCH,
            "manifest base_sha does not match the exact checked-out source SHA",
        )
        return result, None, None, None, None
    pr_base = str(manifest.get("pr_base", "")).strip()
    if pr_base == "main":
        result = _blocked_result(
            manifest,
            MAIN_TARGET_FORBIDDEN,
            "Autonomous runtime must not create, update, or merge a Pull Request targeting main.",
        )
        return result, None, None, None, None
    try:
        graph = build_run_graph(manifest)
        story = build_gate_story(graph, gate_statuses=manifest.get("gate_statuses"))
        block, evidence_digest = build_managed_block(
            graph,
            story,
            validation=manifest.get("validation"),
            g4_readiness=manifest.get("g4_readiness"),
        )
        updated_body, pr_body_digest = upsert_managed_block(existing_pr_body, block)
    except (RunGraphError, ValueError, TypeError, KeyError) as exc:
        code = getattr(exc, "reason_code", "AUTONOMOUS_RUNTIME_INPUT_INVALID")
        result = _blocked_result(manifest, str(code), str(exc))
        return result, None, None, None, None

    result = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-preprod-runtime-result",
        "run_id": graph["run_id"],
        "task_id": graph["task_id"],
        "repository": graph["repository"],
        "status": PASS if graph["terminal_status"] == PASS else graph["terminal_status"],
        "terminal_code": "AUTONOMOUS_EVIDENCE_RENDERED",
        "head_sha": graph["head_sha"],
        "graph_digest": graph["graph_digest"],
        "story_digest": story["story_digest"],
        "evidence_digest": evidence_digest,
        "pr_body_digest": pr_body_digest,
        "side_effects_performed": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    return result, graph, story, updated_body, block


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pr-body-in", type=Path)
    parser.add_argument("--pr-body-out", type=Path)
    parser.add_argument("--expected-repository")
    parser.add_argument("--expected-base-sha")
    args = parser.parse_args(argv)

    manifest = _load_json(args.manifest)
    existing_body = args.pr_body_in.read_text(encoding="utf-8") if args.pr_body_in else None
    result, graph, story, updated_body, block = execute_fixture_run(
        manifest,
        existing_pr_body=existing_body,
        expected_repository=args.expected_repository,
        expected_base_sha=args.expected_base_sha,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "runtime-result.json", result)
    if graph is not None and story is not None and updated_body is not None and block is not None:
        _write_json(args.output_dir / "runtime-graph.json", graph)
        _write_json(args.output_dir / "gate-story.json", story)
        (args.output_dir / "pr-run-evidence.md").write_text(block + "\n", encoding="utf-8")
        target = args.pr_body_out or (args.output_dir / "updated-pr-body.md")
        target.write_text(updated_body, encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
