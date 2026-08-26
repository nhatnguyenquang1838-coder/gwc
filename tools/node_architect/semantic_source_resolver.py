#!/usr/bin/env python3
"""Canonical semantic source resolution for Node Architect runtime nodes.

Resolution is deterministic and filesystem-bounded:
1. a descriptor-declared evaluator wins when present and valid;
2. otherwise an exact named Node Architect tool may satisfy the node;
3. otherwise the node remains DESCRIPTOR_ONLY and is not runtime-eligible.

A declared evaluator is an explicit binding. If that binding is unsafe, missing,
or malformed, resolution fails closed instead of silently falling back to a
heuristic named tool.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

SOURCE_RESOLVED_EVALUATOR = "SOURCE_RESOLVED_EVALUATOR"
NAMED_TOOL_PRESENT = "NAMED_TOOL_PRESENT"
DESCRIPTOR_ONLY = "DESCRIPTOR_ONLY"
INVALID_SOURCE_BINDING = "INVALID_SOURCE_BINDING"
NOT_RUNTIME_EXECUTABLE = "NOT_RUNTIME_EXECUTABLE"


def _safe_repo_relative(value: str) -> bool:
    if not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def _result(
    *,
    status: str,
    runtime_eligible: bool,
    reason_code: str,
    evaluator_path: str | None = None,
    descriptor_path: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "runtime_eligible": runtime_eligible,
        "reason_code": reason_code,
        "evaluator_path": evaluator_path,
        "descriptor_path": descriptor_path,
    }


def _load_descriptor(root: Path, descriptor_path: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not _safe_repo_relative(descriptor_path):
        return None, _result(
            status=INVALID_SOURCE_BINDING,
            runtime_eligible=False,
            reason_code="SEMANTIC_DESCRIPTOR_PATH_UNSAFE",
            descriptor_path=descriptor_path,
        )
    path = root / descriptor_path
    if not path.is_file():
        return None, None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, _result(
            status=INVALID_SOURCE_BINDING,
            runtime_eligible=False,
            reason_code="SEMANTIC_DESCRIPTOR_INVALID",
            descriptor_path=descriptor_path,
        )
    if not isinstance(loaded, dict):
        return None, _result(
            status=INVALID_SOURCE_BINDING,
            runtime_eligible=False,
            reason_code="SEMANTIC_DESCRIPTOR_INVALID",
            descriptor_path=descriptor_path,
        )
    return loaded, None


def resolve_semantic_source(node: Mapping[str, Any], *, root: Path | str = Path(".")) -> dict[str, Any]:
    """Resolve one node to an executable semantic source without importing it.

    This function only establishes a safe, exact source binding. Importing and
    invoking the evaluator is the responsibility of the semantic dispatcher.
    """
    node_id = node.get("id")
    if not isinstance(node_id, str) or not node_id:
        return _result(
            status=INVALID_SOURCE_BINDING,
            runtime_eligible=False,
            reason_code="SEMANTIC_NODE_ID_MISSING",
        )

    if node.get("runtime_executable") is False:
        return _result(
            status=NOT_RUNTIME_EXECUTABLE,
            runtime_eligible=False,
            reason_code="NODE_NOT_RUNTIME_EXECUTABLE",
        )

    repo_root = Path(root).resolve()
    provenance = node.get("provenance") if isinstance(node.get("provenance"), Mapping) else {}
    descriptor_path = provenance.get("source_path")
    descriptor: dict[str, Any] | None = None

    if isinstance(descriptor_path, str) and descriptor_path:
        descriptor, error = _load_descriptor(repo_root, descriptor_path)
        if error is not None:
            return error

    if descriptor is not None:
        resolution = descriptor.get("source_resolution")
        if isinstance(resolution, Mapping) and "evaluator" in resolution:
            evaluator = resolution.get("evaluator")
            if not isinstance(evaluator, str) or not _safe_repo_relative(evaluator):
                return _result(
                    status=INVALID_SOURCE_BINDING,
                    runtime_eligible=False,
                    reason_code="SEMANTIC_EVALUATOR_PATH_UNSAFE",
                    descriptor_path=descriptor_path,
                )
            if not (repo_root / evaluator).is_file():
                return _result(
                    status=INVALID_SOURCE_BINDING,
                    runtime_eligible=False,
                    reason_code="SEMANTIC_EVALUATOR_NOT_FOUND",
                    evaluator_path=evaluator,
                    descriptor_path=descriptor_path,
                )
            return _result(
                status=SOURCE_RESOLVED_EVALUATOR,
                runtime_eligible=True,
                reason_code="SEMANTIC_EVALUATOR_BOUND",
                evaluator_path=evaluator,
                descriptor_path=descriptor_path,
            )

    slug = node_id.split(".", 1)[-1].replace("-", "_")
    candidate = f"tools/node_architect/{slug}.py"
    if (repo_root / candidate).is_file():
        return _result(
            status=NAMED_TOOL_PRESENT,
            runtime_eligible=True,
            reason_code="SEMANTIC_NAMED_TOOL_BOUND",
            evaluator_path=candidate,
            descriptor_path=descriptor_path if isinstance(descriptor_path, str) else None,
        )

    return _result(
        status=DESCRIPTOR_ONLY,
        runtime_eligible=False,
        reason_code="SEMANTIC_EVALUATOR_MISSING",
        descriptor_path=descriptor_path if isinstance(descriptor_path, str) else None,
    )
