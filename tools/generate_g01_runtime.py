#!/usr/bin/env python3
"""Generate canonical G0 context, G1 intake, and G1 preflight artifacts.

The command consumes a versioned, already-observed runtime input document. It
does not call GitHub, DS Admin, or any production system. Missing or
contradictory evidence fails closed.

Exit codes:
- 0: generated artifacts are schema-valid and preflight outcome is PASS.
- 1: generated artifacts are schema-valid but preflight is NEEDS_INPUT/BLOCKED.
- 2: input, schema, configuration, or I/O failure.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

GENERATED_ARTIFACTS: dict[str, tuple[str, str]] = {
    "g0": ("g0/context-snapshot.yaml", "g0-context-snapshot.schema.json"),
    "intake": ("g1/intake/g1-intake-brief.yaml", "g1-intake-brief.schema.json"),
    "preflight": ("g1/preflight/g1-preflight-report.yaml", "g1-preflight-report.schema.json"),
}
HIGH_RISK_CLASSES = {"R2", "R3"}


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _validation_messages(instance: Any, schema_path: Path) -> list[str]:
    schema = _load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    messages: list[str] = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "<root>"
        messages.append(f"{location}: {error.message}")
    return messages


def _blocker(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _check(check_id: str, status: str, code: str, message: str, evidence: list[str]) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "code": code,
        "message": message,
        "evidence": evidence,
    }


def _intake_is_complete(request: dict[str, Any]) -> bool:
    problem = request.get("problem", {})
    return bool(
        problem.get("statement")
        and problem.get("why_now")
        and request.get("desired_outcome")
        and request.get("in_scope")
        and request.get("non_goals")
        and request.get("acceptance_criteria")
        and not request.get("unresolved_questions")
        and all(item.get("verifiable") is True for item in request.get("acceptance_criteria", []))
    )


def generate_artifacts(runtime_input: dict[str, Any]) -> tuple[dict[str, Any], str]:
    generated_at = runtime_input["generated_at"]
    project = runtime_input["project"]
    repository = runtime_input["repository"]
    task = runtime_input["task"]
    request = runtime_input["request"]
    risk = runtime_input["risk"]
    sources = runtime_input["sources"]

    trace = {
        "project_id": project["id"],
        "repository": repository["full_name"],
        "task_id": task["id"],
        "base_sha": repository["base_sha"],
        "g0_snapshot": "../../g0/context-snapshot.yaml",
    }

    g0_blockers: list[dict[str, str]] = []
    if repository["verified"] is not True:
        g0_blockers.append(_blocker(
            "REPOSITORY_NOT_VERIFIED",
            "Repository identity must be verified before G1 can pass.",
        ))
    unavailable_required = [
        source["path"]
        for source in sources
        if source["required"] and source["status"] != "AVAILABLE"
    ]
    if unavailable_required:
        g0_blockers.append(_blocker(
            "REQUIRED_SOURCE_UNAVAILABLE",
            "Required sources are unavailable: " + ", ".join(sorted(unavailable_required)),
        ))

    g0 = {
        "schema_version": "1.0",
        "artifact_type": "g0-context-snapshot",
        "generated_at": generated_at,
        "project": {
            "id": project["id"],
            "name": project["name"],
            "profile_path": project["profile_path"],
        },
        "repository": {
            "full_name": repository["full_name"],
            "base_ref": repository["base_ref"],
            "base_sha": repository["base_sha"],
            "protected_branches": repository["protected_branches"],
            "connector": repository["connector"],
            "write_enabled": repository["write_enabled"],
        },
        "constraints": request["constraints"],
        "applicable_policies": runtime_input["policies"],
        "sources": sources,
        "status": "READY" if not g0_blockers else "BLOCKED",
        "blockers": g0_blockers,
    }

    intake_complete = _intake_is_complete(request)
    intake = {
        "schema_version": "1.0",
        "artifact_type": "g1-intake-brief",
        "generated_at": generated_at,
        "trace": trace,
        "problem": request["problem"],
        "desired_outcome": request["desired_outcome"],
        "stakeholders": {
            "requester": request["requester"],
            "affected": request["affected"],
        },
        "scope": {
            "in_scope": request["in_scope"],
            "non_goals": request["non_goals"],
        },
        "constraints": request["constraints"],
        "assumptions": request["assumptions"],
        "risks": request["risks"],
        "acceptance_criteria": request["acceptance_criteria"],
        "unresolved_questions": request["unresolved_questions"],
        "status": "READY" if intake_complete else "NEEDS_INPUT",
    }

    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, str]] = list(g0_blockers)

    if repository["verified"]:
        checks.append(_check(
            "REPO_IDENTITY", "PASS", "REPOSITORY_VERIFIED",
            "Repository identity and base evidence are verified.",
            [f'{repository["full_name"]}@{repository["base_sha"]}', project["profile_path"]],
        ))
    else:
        checks.append(_check(
            "REPO_IDENTITY", "FAIL", "REPOSITORY_NOT_VERIFIUD",
            "Repository identity is not verified.",
            [project["profile_path"]],
        ))

    if unavailable_required:
        checks.append(_check(
            "REQUIRED_SOURCES", "FAIL", "REQUIRED_SOURCE_UNAVAILABLE",
            "One or more required sources are unavailable.",
            sorted(unavailable_required),
        ))
    else:
        checks.append(_check(
            "REQUIRED_SOURCES", "PASS", "REQUIRED_SOURCES_AVAILABLE",
            "All required sources are available.",
            [source["path"] for source in sources if source["required"]],
        ))

    if task["claimed"]:
        checks.append(_check(
            "TASK_TRACEABILITY", "PASS", "DS_ADMIN_TASK_CLAIMED",
            "The bounded change has a claimed DS Admin task.",
            [task["id"]],
        ))
    else:
        checks.append(_check(
            "TASK_TRACEABILITY", "FAIL", "DS_ADMIN_TASK_NOT_CLAIMED",
            "The DS Admin task is not claimed.",
            [task["id"]],
        ))
        blockers.append(_blocker(
            "DS_ADMIN_TASK_NOT_CLAIMED",
            "A valid task claim is required before G2 execution.",
        ))

    if intake_complete:
        checks.append(_check(
            "INTAKE_COMPLETENESS", "PASS", "G1_INTAKE_READY",
            "Problem, scope, non-goals, and verifiable acceptance criteria are complete.",
            ["g1/intake/g1-intake-brief.yaml"],
        ))
    else:
        checks.append(_check(
            "INTAKE_COMPLETENESS", "FAIL", "G1_INTAKE_NEEDS_INPUT",
            "Intake evidence is incomplete or contains unresolved questions.",
            ["g1/intake/g1-intake-brief.yaml"],
        ))
        blockers.append(_blocker(
            "G1_INTAKE_NEEDS_INPUT",
            "Complete the intake before G1 can pass.",
         ))

    risk_class = risk["class"]
    human_direction = risk["human_direction_confirmed"]
    if risk_class in HIGH_RISK_CLASSES:
        required_gate = "G2_HUMAN_DIRECTION"
        if human_direction:
            checks.append(_check(
                "RISK_GATE", "PASS", "HUMAN_DIRECTION_CONFIRMED",
                "Required human direction is recorded for the high-risk class.",
                [f"risk_class={risk_class}"],
            ))
        else:
            checks.append(_check(
                "RISK_GATE", "FAIL", "HUMAN_DIRECTION_REQUIRED",
                "High-risk work requires explicit human direction.",
                [f"risk_class={risk_class}"],
            ))
            blockers.append(_blocker(
                "HUMAN_DIRECTION_REQUIRED",
                "Explicit human direction is required for R2/R3 work.",
            ))
    else:
        required_gate = "G2_AUTOMATIC_BOUNDED"
        checks.append(_check(
            "RISK_GATE", "PASS", "AUTOMATIC_BOUNDED_ALLOWED",
            "R0/R1 work may proceed through automatic bounded G2.",
            [f"risk_class={risk_class}"],
        ))

    if blockers:
        needs_input_codes = {"G1_INTAKE_NEEDS_INPUT", "HUMAN_DIRECTION_REQUIRED"}
        outcome = (
            "NEEDS_INPUT"
            if {item["code"] for item in blockers}.issubset(needs_input_codes)
            else "BLOCKED"
         )
    else:
        outcome = "PASS"

    preflight = {
        "schema_version": "1.0",
        "artifact_type": "g1-preflight-report",
        "generated_at": generated_at,
        "trace": trace,
        "repository_state": {
            "base_ref": repository["base_ref"],
            "base_sha": repository["base_sha"],
            "profile_path": project["profile_path"],
            "connector": repository["connector"],
        },
        "checks": checks,
        "risk_class": risk_class,
        "required_gate": required_gate,
        "blockers": blockers,
        "outcome": outcome,
    }
    return {"g0": g0, "intake": intake, "preflight": preflight}, outcome


def _write_yaml_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Versioned G01 runtime input YAML.")
    parser.add_argument("--root", default=None, help="Repository root; defaults to the parent of tools/.")
    parser.add_argument("--workspace", default=".gwc", help="Output workspace relative to repository root unless absolute.")
    parser.add_argument("--json", action="store_true", help="Emit a JSON summary.")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = repo_root / input_path
    workspace = Path(args.workspace)
    if not workspace.is_absolute():
        workspace = repo_root / workspace

    try:
        runtime_input = _load_yaml(input_path)
        input_errors = _validation_messages(
            runtime_input,
            repo_root / "schemas" / "g01-runtime-input.schema.json",
        )
        if input_errors:
            raise ValueError("runtime input validation failed: " + " | ".join(input_errors))

        artifacts, outcome = generate_artifacts(runtime_input)
        generated_errors: list[str] = []
        for name, (_, schema_name) in GENERATED_ARTIFACTS.items():
            generated_errors.extend(
                f"{name}: {message}"
                for message in _validation_messages(
                    artifacts[name],
                    repo_root / "schemas" / schema_name,
                )
            )
        if generated_errors:
            raise ValueError("generated artifact validation failed: " + " | ".join(generated_errors))

        for name, (relative_path, _) in GENERATED_ARTIFACTS.items():
            _write_yaml_atomic(workspace / relative_path, artifacts[name])
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError, json.JSONDecodeError) as exc:
        payload = {"outcome": "ERROR", "written": False, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"ERROR: {exc}")
        return 2

    summary = {
        "outcome": outcome,
        "written": True,
        "workspace": str(workspace.resolve()),
        "artifacts": [relative_path for relative_path, _ in GENERATED_ARTIFACTS.values()],
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"G01 runtime preflight outcome: {outcome}")
        for relative_path in summary["artifacts"]:
            print(f"WROTE: {relative_path}")
    return 0 if outcome == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
