#!/usr/bin/env python3
"""Generate canonical G0 context, G1 intake, and G1 preflight artifacts.

The command consumes already-observed runtime evidence. It performs no external
side effect. Missing, contradictory, or non-executable evidence fails closed.
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
NON_EXECUTABLE_CAPABILITY_STATES = {"UNKNOWN", "HARD_BLOCKED"}
BYPASS_ELIGIBLE = {"OPERATIONAL_ONLY", "MANUAL_CHECKPOINT_ONLY"}
IMPLEMENTATION_PLAN_REQUIRED_FIELDS = (
    "canonical_task_uid", "repository", "protected_base_sha", "plan_root",
    "requirements_path", "design_path", "tasks_path", "plan_revision",
    "validation_evidence", "generated_by", "generated_at_utc",
)
DELIVERY_LIFECYCLE_ACTIONS = [
    "create_guarded_branch", "modify_scoped_files", "run_sandboxed_validation",
    "push_working_branch", "open_or_update_draft_pr", "monitor_ci",
    "repair_repository_fixable_ci", "independent_g3_review",
    "mark_pr_ready_for_review_after_g3_pass",
]
DELIVERY_NON_GOALS = [
    "merge", "auto_merge", "deploy", "release", "production_config_change",
    "credential_rotation", "production_data_access",
]
G3_READY_FOR_REVIEW_EVIDENCE = [
    "g3_delivery_record_pass", "current_pr_head_sha_match", "required_ci_success",
    "review_closure_non_stale", "scope_drift_false",
]
PROCESS_SOURCES = [
    "AGENTS.md",
    "core/GATE_LIFECYCLE_CONTRACT_v1.0.md",
    "core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md",
    "core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md",
]


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
    return {"id": check_id, "status": status, "code": code, "message": message, "evidence": evidence}


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


def _selected_connector_available(runtime: dict[str, Any]) -> bool:
    selected = runtime["selected_connector"]
    matching = [
        item for item in runtime.get("connector_fallback_evidence", [])
        if item.get("connector") == selected
    ]
    return any(item.get("status") == "AVAILABLE" for item in matching)


def _source_baseline_blockers(
    repository: dict[str, Any],
    runtime: dict[str, Any],
) -> list[dict[str, str]]:
    """Validate claim-time source authority and local-checkout eligibility.

    The generator consumes already-observed evidence; it does not fetch remotes.
    Local mismatch or dirtiness is not a total blocker when authoritative remote
    source is available, but such local state can never be marked eligible for
    trusted analysis.
    """
    baseline = repository.get("source_baseline")
    if baseline is None:
        if runtime.get("execution_mode") == "local_agent":
            return [_blocker(
                "SOURCE_BASELINE_EVIDENCE_REQUIRED",
                "local_agent G0/G1 requires claim-time source-baseline evidence before trusted analysis.",
            )]
        return []

    blockers: list[dict[str, str]] = []
    if baseline.get("observed_sha") != repository.get("base_sha"):
        blockers.append(_blocker(
            "SOURCE_BASELINE_SHA_MISMATCH",
            "Observed authoritative source SHA must match repository.base_sha.",
        ))

    authority = baseline.get("authority")
    if authority == "REMOTE_PROTECTED_BASE" and baseline.get("observed_ref") != repository.get("base_ref"):
        blockers.append(_blocker(
            "SOURCE_BASELINE_REF_MISMATCH",
            "Remote protected-base evidence must match repository.base_ref.",
        ))

    local = baseline.get("local_state", {})
    equivalence = local.get("equivalence")
    eligible = local.get("analysis_eligible") is True
    if eligible and not (
        equivalence == "MATCH"
        and local.get("dirty") is False
        and local.get("head_sha") == baseline.get("observed_sha")
    ):
        blockers.append(_blocker(
            "LOCAL_ANALYSIS_SOURCE_INELIGIBLE",
            "Local state may be eligible for trusted analysis only when clean and exactly equivalent to the authoritative source SHA.",
        ))
    if equivalence == "MATCH" and local.get("head_sha") != baseline.get("observed_sha"):
        blockers.append(_blocker(
            "LOCAL_SOURCE_EQUIVALENCE_INVALID",
            "MATCH local equivalence requires local head SHA to equal the authoritative source SHA.",
        ))
    return blockers


def _source_baseline_check(
    repository: dict[str, Any],
    runtime: dict[str, Any],
    blockers: list[dict[str, str]],
) -> dict[str, Any]:
    baseline = repository.get("source_baseline")
    if baseline is None:
        if runtime.get("execution_mode") == "local_agent":
            return _check(
                "SOURCE_BASELINE", "FAIL", "SOURCE_BASELINE_EVIDENCE_REQUIRED",
                "Claim-time source-baseline evidence is missing for local_agent.",
                [f"execution_mode={runtime.get('execution_mode')}"],
            )
        return _check(
            "SOURCE_BASELINE", "PASS", "CONNECTOR_SOURCE_AUTHORITY",
            "Connector/CI source authority is used; no ambient local checkout is trusted.",
            [runtime.get("selected_connector", "unknown"), repository.get("base_sha", "unknown")],
        )

    evidence = [
        f"authority={baseline.get('authority')}",
        f"provider={baseline.get('provider')}",
        f"ref={baseline.get('observed_ref')}",
        f"sha={baseline.get('observed_sha')}",
        f"local_equivalence={baseline.get('local_state', {}).get('equivalence')}",
        f"local_analysis_eligible={baseline.get('local_state', {}).get('analysis_eligible')}",
    ]
    if blockers:
        return _check(
            "SOURCE_BASELINE", "FAIL", blockers[0]["code"], blockers[0]["message"], evidence
        )
    local = baseline.get("local_state", {})
    if local.get("analysis_eligible") is False and local.get("equivalence") in {"MISMATCH", "UNVERIFIED"}:
        return _check(
            "SOURCE_BASELINE", "PASS", "LOCAL_ANALYSIS_SOURCE_ISOLATED",
            "Authoritative source is verified and ambient local state is explicitly excluded from trusted analysis.",
            evidence,
        )
    return _check(
        "SOURCE_BASELINE", "PASS", "SOURCE_BASELINE_VERIFIED",
        "Claim-time source authority and local analysis eligibility are internally consistent.",
        evidence,
    )


def _implementation_plan_blockers(
    implementation_plan: dict[str, Any] | None,
    repository: dict[str, Any],
) -> list[dict[str, str]]:
    """Validate observed plan-routing evidence without performing side effects."""
    if implementation_plan is None:
        return []

    applicability = implementation_plan.get("applicability")
    if applicability == "not_applicable":
        if (
            implementation_plan.get("source") == "plan_not_applicable"
            and implementation_plan.get("validation_status") == "NOT_APPLICABLE"
            and str(implementation_plan.get("reason", "")).strip()
        ):
            return []
        return [_blocker(
            "G1_PLAN_NOT_APPLICABLE_INVALID",
            "Not-applicable plan evidence requires an explicit reason, plan_not_applicable source, and NOT_APPLICABLE status.",
        )]
    if applicability != "required":
        return [_blocker(
            "G1_PLAN_APPLICABILITY_INVALID",
            "Plan applicability must be required or not_applicable.",
        )]

    blockers: list[dict[str, str]] = []
    missing = [field for field in IMPLEMENTATION_PLAN_REQUIRED_FIELDS if not implementation_plan.get(field)]
    if missing:
        blockers.append(_blocker(
            "G1_IMPLEMENTATION_PLAN_MISSING",
            "Missing implementation-plan fields: " + ", ".join(missing),
        ))
    if implementation_plan.get("validation_status") != "PASS":
        blockers.append(_blocker(
            "G1_IMPLEMENTATION_PLAN_NOT_VALIDATED",
            "A required implementation plan must have validation_status=PASS.",
        ))
    if implementation_plan.get("repository") != repository.get("full_name"):
        blockers.append(_blocker(
            "G1_IMPLEMENTATION_PLAN_REPOSITORY_MISMATCH",
            "Implementation-plan repository does not match the G0 repository.",
        ))
    if implementation_plan.get("protected_base_sha") != repository.get("base_sha"):
        blockers.append(_blocker(
            "G1_IMPLEMENTATION_PLAN_BASE_MISMATCH",
            "Implementation-plan protected base SHA does not match G0.",
        ))
    if implementation_plan.get("source") == "task_me" and implementation_plan.get("task_me_invoked") is not True:
        blockers.append(_blocker(
            "G1_TASK_ME_NOT_INVOKED",
            "Task Me plan source requires invocation evidence.",
        ))
    if (
        implementation_plan.get("task_me_applicable") is True
        and implementation_plan.get("task_me_available") is True
        and implementation_plan.get("task_me_invoked") is not True
    ):
        blockers.append(_blocker(
            "G1_TASK_ME_REQUIRED",
            "Task Me was applicable and available but was not invoked.",
        ))
    if (
        implementation_plan.get("source") == "generated_kiro"
        and implementation_plan.get("task_me_applicable") is True
        and implementation_plan.get("task_me_invoked") is not True
        and not implementation_plan.get("task_me_fallback_reason")
    ):
        blockers.append(_blocker(
            "G1_TASK_ME_FALLBACK_REASON_MISSING",
            "Kiro fallback requires an explicit Task Me fallback reason.",
        ))
    return blockers


def _route_steps(
    repository: dict[str, Any],
    runtime: dict[str, Any],
    sources_ready: bool,
    implementation_plan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    connector = runtime["selected_connector"]
    connector_declared = connector in runtime["connector_priority"]
    connector_available = _selected_connector_available(runtime)
    read_status = "VERIFIED" if repository["verified"] and sources_ready and connector_available else "HARD_BLOCKED"
    write_status = "VERIFIED" if repository["verified"] and repository["write_enabled"] and connector_declared and connector_available else "HARD_BLOCKED"
    fallbacks = [item for item in runtime["connector_priority"] if item != connector]
    route_steps = [
        {"id": "STEP-01", "name": "protected-base-and-process-readback", "gate": "G1_ALIGNMENT", "actor": "agent", "action_class": "read", "capability_required": "repository_read", "capability_status": read_status, "primary_route": connector, "fallback_routes": fallbacks, "continuation": "immediate", "expected_evidence": "protected base SHA and required process sources", "bypass_eligibility": "FORBIDDEN"},
        {"id": "STEP-02", "name": "formal-g01-artifact-generation-and-validation", "gate": "G1_ALIGNMENT", "actor": "agent", "action_class": "local_validation", "capability_required": "python_jsonschema_validator", "capability_status": "VERIFIED", "primary_route": "tools/generate_g01_runtime.py + tools/validate_g01.py", "fallback_routes": ["trusted local agent", "repo CI"], "continuation": "immediate", "expected_evidence": "schema validation and validate_g01 exit code", "bypass_eligibility": "FORBIDDEN"},
        {"id": "STEP-03", "name": "guarded-branch-creation", "gate": "G2_EXECUTION", "actor": "agent_or_human", "action_class": "repository_write", "capability_required": "guarded_branch_create", "capability_status": write_status, "primary_route": connector, "fallback_routes": ["human manual UI action"], "continuation": "checkpoint before side effect and readback after", "expected_evidence": "branch ref equals approved base SHA", "bypass_eligibility": "OPERATIONAL_ONLY"},
        {"id": "STEP-04", "name": "scoped-file-write-and-validation", "gate": "G2_EXECUTION", "actor": "agent", "action_class": "repository_write", "capability_required": "guarded_file_write_and_validation", "capability_status": write_status, "primary_route": connector, "fallback_routes": ["trusted local agent"], "continuation": "checkpoint, exact diff readback, and validator run", "expected_evidence": "approved changed paths and validation results", "bypass_eligibility": "FORBIDDEN"},
        {"id": "STEP-05", "name": "draft-pr-delivery", "gate": "G3_PR", "actor": "agent_or_human", "action_class": "repository_metadata_write", "capability_required": "draft_pr_create_or_update", "capability_status": write_status, "primary_route": connector, "fallback_routes": ["human manual UI action"], "continuation": "checkpoint before human wait and readback after", "expected_evidence": "PR number URL and exact head SHA", "bypass_eligibility": "OPERATIONAL_ONLY"},
        {"id": "STEP-06", "name": "exact-head-ci-continuation", "gate": "G3_PR", "actor": "agent_or_human", "action_class": "async_read_and_bounded_repair", "capability_required": "ci_status_and_continuation", "capability_status": "VERIFIED", "primary_route": "CI callback or scheduled continuation", "fallback_routes": ["local poll", "manual checkpoint"], "continuation": "required until terminal exact-head CI state", "expected_evidence": "required checks for current head and next continuation", "bypass_eligibility": "MANUAL_CHECKPOINT_ONLY"},
        {"id": "STEP-07", "name": "independent-g3-review", "gate": "G3_PR", "actor": "agent", "action_class": "read_only_review", "capability_required": "independent_review_bundle", "capability_status": "VERIFIED", "primary_route": "Context7-compatible review bundle", "fallback_routes": ["offline pinned G3 skill library"], "continuation": "review exact current head and return required changes to G2", "expected_evidence": "seven review lanes and acceptance-criteria closure for exact head", "bypass_eligibility": "FORBIDDEN"},
        {"id": "STEP-08", "name": "ready-for-review-promotion", "gate": "G3_PR", "actor": "agent_or_human", "action_class": "repository_metadata_write", "capability_required": "mark_pr_ready_for_review", "capability_status": write_status, "primary_route": connector, "fallback_routes": ["human manual UI action"], "continuation": "checkpoint before action and exact PR-state readback after", "expected_evidence": "PR is ready, head SHA unchanged, G3 PASS remains current", "bypass_eligibility": "OPERATIONAL_ONLY"},
        {"id": "STEP-09", "name": "merge", "gate": "G4_MERGE", "actor": "human_authorized_agent", "action_class": "protected_action", "capability_required": "exact_g4_authority", "capability_status": "SEPARATE_GATE", "primary_route": "exact G4 approval then guarded merge", "fallback_routes": [], "continuation": "stop at human authority boundary", "expected_evidence": "exact PR head and merge commit", "bypass_eligibility": "FORBIDDEN"},
    ]
    if implementation_plan is not None:
        plan_status = "VERIFIED" if not _implementation_plan_blockers(implementation_plan, repository) else "HARD_BLOCKED"
        route_steps.insert(2, {
            "id": "STEP-10",
            "name": "implementation-plan-discovery-validation-and-handoff",
            "gate": "G1_ALIGNMENT",
            "actor": "agent",
            "action_class": "planning_and_validation",
            "capability_required": "task_me_or_kiro_plan",
            "capability_status": plan_status,
            "primary_route": implementation_plan.get("source", "unknown"),
            "fallback_routes": ["existing Kiro plan", "Task Me", "generated Kiro plan"],
            "continuation": "bind the exact plan revision and return to G1 on drift",
            "expected_evidence": str(implementation_plan.get("plan_revision") or implementation_plan.get("reason")),
            "bypass_eligibility": "FORBIDDEN",
        })
    return route_steps


def _classify_execution_feasibility(route_steps: list[dict[str, Any]]) -> dict[str, Any]:
    unresolved = [
        step for step in route_steps
        if step.get("capability_status") in NON_EXECUTABLE_CAPABILITY_STATES
    ]
    bypass_steps = [
        step for step in unresolved
        if step.get("bypass_eligibility") in BYPASS_ELIGIBLE
        and bool(step.get("fallback_routes"))
    ]
    bypass_ids = {step.get("id") for step in bypass_steps}
    fatal_steps = [step for step in unresolved if step.get("id") not in bypass_ids]

    if fatal_steps:
        outcome = "NOT_EXECUTABLE"
        human_bypass_required = False
    elif bypass_steps:
        outcome = "EXECUTABLE_WITH_HUMAN_BYPASS"
        human_bypass_required = True
    else:
        outcome = "EXECUTABLE"
        human_bypass_required = False

    return {
        "outcome": outcome,
        "route_steps": route_steps,
        "continuation_coverage": "COMPLETE",
        "human_bypass_required": human_bypass_required,
    }


def generate_artifacts(runtime_input: dict[str, Any]) -> tuple[dict[str, Any], str]:
    generated_at = runtime_input["generated_at"]
    project = runtime_input["project"]
    repository = runtime_input["repository"]
    runtime = runtime_input["runtime"]
    task = runtime_input["task"]
    request = runtime_input["request"]
    risk = runtime_input["risk"]
    sources = runtime_input["sources"]
    implementation_plan = runtime_input.get("implementation_plan_observation")

    trace = {"project_id": project["id"], "repository": repository["full_name"], "task_id": task["id"], "base_sha": repository["base_sha"], "g0_snapshot": "../../g0/context-snapshot.yaml"}
    runtime_context = {
        "agent_runtime_id": runtime["agent_runtime_id"],
        "execution_mode": runtime["execution_mode"],
        "selected_profile": {"id": runtime["selected_profile"]["id"], "path": runtime["selected_profile"]["path"]},
        "selected_connector": runtime["selected_connector"],
        "connector_priority": runtime["connector_priority"],
        "required_behavior_contracts": [item["path"] for item in runtime["required_behavior_contracts"]],
    }
    delivery_lifecycle = {"authorized_actions": DELIVERY_LIFECYCLE_ACTIONS, "downstream_non_goals": DELIVERY_NON_GOALS, "g3_metadata_completion": {"ready_for_review_after_g3_pass": True, "required_evidence": G3_READY_FOR_REVIEW_EVIDENCE}}

    unavailable_required = [item["path"] for item in sources if item["required"] and item["status"] != "AVAILABLE"]
    unavailable_contracts = [item["path"] for item in runtime["required_behavior_contracts"] if item["required"] and item["status"] != "AVAILABLE"]
    execution_supported = runtime["execution_mode"] in runtime["selected_profile"]["supported_execution_modes"]
    connector_declared = runtime["selected_connector"] in runtime["connector_priority"]
    connector_available = _selected_connector_available(runtime)

    g0_blockers: list[dict[str, str]] = []
    source_baseline_blockers = _source_baseline_blockers(repository, runtime)
    g0_blockers.extend(source_baseline_blockers)
    if repository["verified"] is not True:
        g0_blockers.append(_blocker("REPOSITORY_NOT_VERIFIED", "Repository identity must be verified before G1 can pass."))
    if unavailable_required:
        g0_blockers.append(_blocker("REQUIRED_SOURCE_UNAVAILABLE", "Required sources are unavailable: " + ", ".join(sorted(unavailable_required))))
    if not execution_supported:
        g0_blockers.append(_blocker("EXECUTION_MODE_UNSUPPORTED", "The selected runtime profile does not support the current execution mode."))
    if not connector_declared:
        g0_blockers.append(_blocker("CONNECTOR_NOT_DECLARED", "The selected connector must be present in connector_priority."))
    if not connector_available:
        g0_blockers.append(_blocker("SELECTED_CONNECTOR_UNAVAILABLE", "The selected connector requires AVAILABLE evidence before G1 can pass."))
    if unavailable_contracts:
        g0_blockers.append(_blocker("BEHAVIOR_CONTRACT_UNAVAILABLE", "Required behavior contracts are unavailable: " + ", ".join(sorted(unavailable_contracts))))

    g0 = {
        "schema_version": "1.0", "artifact_type": "g0-context-snapshot", "generated_at": generated_at,
        "project": {"id": project["id"], "name": project["name"], "profile_path": project["profile_path"]},
        "repository": {"full_name": repository["full_name"], "base_ref": repository["base_ref"], "base_sha": repository["base_sha"], "protected_branches": repository["protected_branches"], "connector": repository["connector"], "write_enabled": repository["write_enabled"]},
        "runtime_context": runtime_context, "constraints": request["constraints"], "applicable_policies": runtime_input["policies"], "sources": sources,
        "status": "READY" if not g0_blockers else "BLOCKED", "blockers": g0_blockers,
    }

    intake_complete = _intake_is_complete(request)
    intake = {
        "schema_version": "1.0", "artifact_type": "g1-intake-brief", "generated_at": generated_at, "trace": trace,
        "problem": request["problem"], "desired_outcome": request["desired_outcome"],
        "stakeholders": {"requester": request["requester"], "affected": request["affected"]},
        "scope": {"in_scope": request["in_scope"], "non_goals": request["non_goals"]},
        "constraints": request["constraints"], "assumptions": request["assumptions"], "risks": request["risks"],
        "acceptance_criteria": request["acceptance_criteria"], "delivery_lifecycle": delivery_lifecycle,
        "unresolved_questions": request["unresolved_questions"], "status": "READY" if intake_complete else "NEEDS_INPUT",
    }

    blockers = list(g0_blockers)
    implementation_plan_blockers = _implementation_plan_blockers(implementation_plan, repository)
    blockers.extend(implementation_plan_blockers)
    checks: list[dict[str, Any]] = [
        _source_baseline_check(repository, runtime, source_baseline_blockers),
        _check("REPO_IDENTITY", "PASS" if repository["verified"] else "FAIL", "REPOSITORY_VERIFIED" if repository["verified"] else "REPOSITORY_NOT_VERIFIED", "Repository identity and base evidence are verified." if repository["verified"] else "Repository identity is not verified.", [f'{repository["full_name"]}@{repository["base_sha"]}', project["profile_path"]]),
        _check("REQUIRED_SOURCES", "FAIL" if unavailable_required else "PASS", "REQUIRED_SOURCE_UNAVAILABLE" if unavailable_required else "REQUIRED_SOURCES_AVAILABLE", "One or more required sources are unavailable." if unavailable_required else "All required sources are available.", sorted(unavailable_required) if unavailable_required else [item["path"] for item in sources if item["required"]]),
        _check("EXECUTION_MODE_COMPATIBILITY", "PASS" if execution_supported else "FAIL", "EXECUTION_MODE_SUPPORTED" if execution_supported else "EXECUTION_MODE_UNSUPPORTED", "The selected runtime profile supports the current execution mode." if execution_supported else "The selected runtime profile does not support the current execution mode.", [runtime["selected_profile"]["path"], f'execution_mode={runtime["execution_mode"]}']),
        _check("SELECTED_CONNECTOR", "PASS" if connector_available else "FAIL", "SELECTED_CONNECTOR_AVAILABLE" if connector_available else "SELECTED_CONNECTOR_UNAVAILABLE", "The selected connector has AVAILABLE evidence." if connector_available else "The selected connector has no AVAILABLE evidence.", [runtime["selected_connector"]]),
        _check("BOOTSTRAP_BEHAVIOR_CONTRACTS", "FAIL" if unavailable_contracts else "PASS", "BEHAVIOR_CONTRACT_UNAVAILABLE" if unavailable_contracts else "BEHAVIOR_CONTRACTS_AVAILABLE", "One or more required behavior contracts are unavailable." if unavailable_contracts else "Required behavior and presentation contracts are available.", sorted(unavailable_contracts) if unavailable_contracts else runtime_context["required_behavior_contracts"]),
        _check("DELIVERY_LIFECYCLE_SCOPE", "PASS", "NON_MERGE_DELIVERY_SCOPE_EXPLICIT", "G1 anticipates guarded delivery through G3 without granting G4 authority.", DELIVERY_LIFECYCLE_ACTIONS),
    ]

    if implementation_plan is not None:
        plan_status = "FAIL" if implementation_plan_blockers else "PASS"
        if implementation_plan_blockers:
            plan_code = implementation_plan_blockers[0]["code"]
            plan_message = implementation_plan_blockers[0]["message"]
        elif implementation_plan.get("applicability") == "not_applicable":
            plan_code = "PLAN_NOT_APPLICABLE"
            plan_message = "Implementation planning is explicitly not applicable."
        else:
            plan_code = "IMPLEMENTATION_PLAN_VALIDATED"
            plan_message = "Implementation-plan routing and validation evidence are complete."
        checks.append(_check(
            "IMPLEMENTATION_PLAN_HANDOFF", plan_status, plan_code, plan_message,
            [str(implementation_plan.get("plan_revision") or implementation_plan.get("reason"))],
        ))

    if task["claimed"]:
        checks.append(_check("TASK_TRACEABILITY", "PASS", "DS_ADMIN_TASK_CLAIMED", "The bounded change has a claimed work-tracking task.", [task["id"]]))
    else:
        checks.append(_check("TASK_TRACEABILITY", "FAIL", "DS_ADMIN_TASK_NOT_CLAIMED", "The work-tracking task is not claimed.", [task["id"]]))
        blockers.append(_blocker("DS_ADMIN_TASK_NOT_CLAIMED", "A valid task claim is required before G2 execution."))

    if intake_complete:
        checks.append(_check("INTAKE_COMPLETENESS", "PASS", "G1_INTAKE_READY", "Problem, scope, non-goals, and verifiable acceptance criteria are complete.", ["g1/intake/g1-intake-brief.yaml"]))
    else:
        checks.append(_check("INTAKE_COMPLETENESS", "FAIL", "G1_INTAKE_NEEDS_INPUT", "Intake evidence is incomplete or contains unresolved questions.", ["g1/intake/g1-intake-brief.yaml"]))
        blockers.append(_blocker("G1_INTAKE_NEEDS_INPUT", "Complete the intake before G1 can pass."))

    risk_class = risk["class"]
    human_direction = risk["human_direction_confirmed"]
    if risk_class in HIGH_RISK_CLASSES:
        required_gate = "G2_HUMAN_DIRECTION"
        checks.append(_check("RISK_GATE", "PASS" if human_direction else "FAIL", "HUMAN_DIRECTION_CONFIRMED" if human_direction else "HUMAN_DIRECTION_REQUIRED", "Required human direction is recorded for the high-risk class." if human_direction else "High-risk work requires explicit human direction.", [f"risk_class={risk_class}"]))
        if not human_direction:
            blockers.append(_blocker("HUMAN_DIRECTION_REQUIRED", "Explicit human direction is required for R2/R3 work."))
    else:
        required_gate = "G2_AUTOMATIC_BOUNDED"
        checks.append(_check("RISK_GATE", "PASS", "AUTOMATIC_BOUNDED_ALLOWED", "R0/R1 work may proceed through automatic bounded G2.", [f"risk_class={risk_class}"]))

    sources_ready = not unavailable_required
    route_steps = _route_steps(repository, runtime, sources_ready, implementation_plan)
    process_readback = {"process_id": "governed-repository-delivery", "terminal_outcome": request["desired_outcome"], "required_sources": PROCESS_SOURCES, "status": "VERIFIED" if sources_ready and repository["verified"] else "INCOMPLETE"}
    execution_feasibility = _classify_execution_feasibility(route_steps)
    feasibility_outcome = execution_feasibility["outcome"]
    route_executable = feasibility_outcome != "NOT_EXECUTABLE"
    checks.append(_check("PROCESS_READBACK", "PASS" if process_readback["status"] == "VERIFIED" else "FAIL", "PROCESS_READBACK_COMPLETE" if process_readback["status"] == "VERIFIED" else "PROCESS_READBACK_INCOMPLETE", "The governing process and requested terminal outcome were read back." if process_readback["status"] == "VERIFIED" else "Required process evidence is incomplete.", PROCESS_SOURCES))
    checks.append(_check(
        "EXECUTION_FEASIBILITY",
        "PASS" if route_executable else "FAIL",
        "END_TO_END_ROUTE_EXECUTABLE_WITH_HUMAN_BYPASS" if feasibility_outcome == "EXECUTABLE_WITH_HUMAN_BYPASS" else ("END_TO_END_ROUTE_EXECUTABLE" if route_executable else "END_TO_END_ROUTE_NOT_EXECUTABLE"),
        "Every mandatory route step is executable." if feasibility_outcome == "EXECUTABLE" else ("Blocked operational steps have bounded HUMAN BYPASS fallbacks." if route_executable else "At least one mandatory route step is hard blocked without a legal fallback."),
        [step["id"] for step in route_steps],
    ))
    if not route_executable:
        blockers.append(_blocker("EXECUTION_ROUTE_NOT_FEASIBLE", "The requested terminal outcome cannot be executed with the verified capabilities."))

    if blockers:
        needs_input_codes = {"G1_INTAKE_NEEDS_INPUT", "HUMAN_DIRECTION_REQUIRED"}
        outcome = "NEEDS_INPUT" if {item["code"] for item in blockers}.issubset(needs_input_codes) else "BLOCKED"
    else:
        outcome = "PASS"

    preflight = {
        "schema_version": "1.1" if implementation_plan is not None else "1.0", "artifact_type": "g1-preflight-report", "generated_at": generated_at, "trace": trace,
        "repository_state": {"base_ref": repository["base_ref"], "base_sha": repository["base_sha"], "profile_path": project["profile_path"], "connector": repository["connector"]},
        "checks": checks, "process_readback": process_readback, "execution_feasibility": execution_feasibility,
        "runtime_context": runtime_context, "risk_class": risk_class, "required_gate": required_gate, "blockers": blockers, "outcome": outcome,
    }
    if implementation_plan is not None:
        preflight["implementation_plan"] = implementation_plan
    return {"g0": g0, "intake": intake, "preflight": preflight}, outcome


def _write_yaml_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")
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
        input_errors = _validation_messages(runtime_input, repo_root / "schemas" / "g01-runtime-input.schema.json")
        if input_errors:
            raise ValueError("runtime input validation failed: " + " | ".join(input_errors))
        artifacts, outcome = generate_artifacts(runtime_input)
        generated_errors: list[str] = []
        for name, (_, schema_name) in GENERATED_ARTIFACTS.items():
            generated_errors.extend(f"{name}: {message}" for message in _validation_messages(artifacts[name], repo_root / "schemas" / schema_name))
        if generated_errors:
            raise ValueError("generated artifact validation failed: " + " | ".join(generated_errors))
        for name, (relative_path, _) in GENERATED_ARTIFACTS.items():
            _write_yaml_atomic(workspace / relative_path, artifacts[name])
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError, json.JSONDecodeError) as exc:
        payload = {"outcome": "ERROR", "written": False, "error": str(exc)}
        print(json.dumps(payload, indent=2) if args.json else f"ERROR: {exc}")
        return 2

    summary = {"outcome": outcome, "written": True, "workspace": str(workspace.resolve()), "artifacts": [path for path, _ in GENERATED_ARTIFACTS.values()]}
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"G01 runtime preflight outcome: {outcome}")
        for relative_path in summary["artifacts"]:
            print(f"WROTE: {relative_path}")
    return 0 if outcome == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
