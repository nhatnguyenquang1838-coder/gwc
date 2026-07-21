#!/usr/bin/env python3
"""Resolve a typed GWC profile set deterministically and fail closed."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

TYPE_ORDER = {"gate_policy": 0, "agent_runtime": 1, "environment": 2, "risk": 3}
EXPECTED_DIR = {
    "gate_policy": "governance/gate-policy-profiles/",
    "agent_runtime": "governance/agent-runtime-profiles/",
    "environment": "governance/environment-profiles/",
    "risk": "governance/risk-profiles/",
}


class ProfileResolutionError(ValueError):
    """Raised when a profile set cannot be resolved safely."""


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def safe_repo_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in value:
        raise ProfileResolutionError(f"unsafe profile path: {value}")
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise ProfileResolutionError(f"profile path escapes root: {value}")
    return resolved


def validate_schema(instance: Any, schema_path: Path, label: str) -> None:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    if errors:
        details = "; ".join(
            f"{'.'.join(map(str, error.path)) or '<root>'}: {error.message}"
            for error in errors
        )
        raise ProfileResolutionError(f"{label} schema validation failed: {details}")


def profile_references(profile_set: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
    profiles = profile_set["profiles"]
    references = [("gate_policy", profiles["gate_policy"])]
    references.extend(("agent_runtime", item) for item in profiles["agent_runtimes"])
    references.extend(
        [("environment", profiles["environment"]), ("risk", profiles["risk"])]
    )
    return references


def _select_agent_runtime(
    resolved_profiles: list[dict[str, Any]],
    agent_runtime_id: str,
    execution_mode: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    matches = [
        item
        for item in resolved_profiles
        if item["profile_type"] == "agent_runtime"
        and item["profile_id"] == agent_runtime_id
    ]
    if len(matches) != 1:
        raise ProfileResolutionError(
            f"exactly one active agent runtime required for {agent_runtime_id!r}; "
            f"found {len(matches)}"
        )
    selected = matches[0]
    supported_modes = selected["content"].get("execution_modes", [])
    if execution_mode not in supported_modes:
        raise ProfileResolutionError(
            f"execution mode {execution_mode!r} is not supported by "
            f"agent runtime {agent_runtime_id!r}"
        )
    filtered_profiles = [
        item
        for item in resolved_profiles
        if item["profile_type"] != "agent_runtime" or item is selected
    ]
    return filtered_profiles, {
        "agent_runtime_id": agent_runtime_id,
        "execution_mode": execution_mode,
        "profile_path": selected["path"],
    }


def resolve_profile_set(
    root: Path,
    profile_set_path: Path,
    agent_runtime_id: str | None = None,
    execution_mode: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    profile_set_path = profile_set_path.resolve()
    if (agent_runtime_id is None) != (execution_mode is None):
        raise ProfileResolutionError(
            "agent_runtime_id and execution_mode must be provided together"
        )
    profile_set = load_yaml(profile_set_path)
    if not isinstance(profile_set, dict):
        raise ProfileResolutionError("profile set must be an object")
    validate_schema(profile_set, root / "schemas/profile-set.schema.json", "profile set")
    if profile_set.get("status") != "active":
        raise ProfileResolutionError("profile set must be active")

    seen_ids: set[tuple[str, str]] = set()
    seen_paths: set[str] = set()
    resolved_profiles: list[dict[str, Any]] = []

    for expected_type, reference in profile_references(profile_set):
        key = (expected_type, reference["id"])
        if key in seen_ids:
            raise ProfileResolutionError(
                f"duplicate profile reference: {expected_type}/{reference['id']}"
            )
        seen_ids.add(key)

        normalized_path = Path(reference["path"]).as_posix()
        if normalized_path in seen_paths:
            raise ProfileResolutionError(f"duplicate profile path: {normalized_path}")
        seen_paths.add(normalized_path)
        if not normalized_path.startswith(EXPECTED_DIR[expected_type]):
            raise ProfileResolutionError(
                f"profile path does not match type {expected_type}: {normalized_path}"
            )

        path = safe_repo_path(root, normalized_path)
        if not path.is_file():
            raise ProfileResolutionError(
                f"referenced profile does not exist: {normalized_path}"
            )
        content = load_yaml(path)
        if not isinstance(content, dict):
            raise ProfileResolutionError(f"profile must be an object: {normalized_path}")
        if content.get("profile_type") != expected_type:
            raise ProfileResolutionError(
                f"wrong profile type for {normalized_path}: expected {expected_type}, "
                f"got {content.get('profile_type')}"
            )
        if content.get("profile_id") != reference["id"]:
            raise ProfileResolutionError(
                f"wrong profile id for {normalized_path}: expected {reference['id']}, "
                f"got {content.get('profile_id')}"
            )
        if content.get("status") != "active":
            raise ProfileResolutionError(f"profile is not active: {normalized_path}")
        for field in ("schema_version", "profile_type", "profile_id", "status"):
            if field not in content:
                raise ProfileResolutionError(f"missing {field} in {normalized_path}")
        if expected_type == "gate_policy":
            validate_schema(
                content,
                root / "schemas/gate-policy-profile.schema.json",
                normalized_path,
            )
        resolved_profiles.append(
            {
                "profile_type": expected_type,
                "profile_id": reference["id"],
                "path": normalized_path,
                "content": content,
            }
        )

    resolved_profiles.sort(
        key=lambda item: (
            TYPE_ORDER[item["profile_type"]],
            item["profile_id"],
            item["path"],
        )
    )
    selected_runtime: dict[str, str] | None = None
    if agent_runtime_id is not None and execution_mode is not None:
        resolved_profiles, selected_runtime = _select_agent_runtime(
            resolved_profiles, agent_runtime_id, execution_mode
        )

    result = {
        "schema_version": "1.0",
        "artifact_type": "resolved-profile-set",
        "profile_set": {
            "profile_id": profile_set["profile_id"],
            "path": profile_set_path.relative_to(root).as_posix(),
        },
        "resolved_profiles": resolved_profiles,
    }
    if selected_runtime is not None:
        result["selected_runtime"] = selected_runtime
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None)
    parser.add_argument(
        "--profile-set", default="governance/profile-sets/gwc-standard.yaml"
    )
    parser.add_argument(
        "--agent-runtime",
        default=None,
        help="Select exactly one active agent runtime by id, e.g. chatgpt or dwc.",
    )
    parser.add_argument(
        "--execution-mode",
        default=None,
        help="Validate the selected runtime supports this execution mode.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    try:
        result = resolve_profile_set(
            root,
            safe_repo_path(root, args.profile_set),
            agent_runtime_id=args.agent_runtime,
            execution_mode=args.execution_mode,
        )
    except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"outcome": "FAIL", "error": str(exc)})
            if args.json
            else f"FAIL: {exc}"
        )
        return 1
    print(
        json.dumps(result, indent=2, sort_keys=True)
        if args.json
        else f"PASS: resolved {len(result['resolved_profiles'])} profiles for "
        f"{result['profile_set']['profile_id']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
