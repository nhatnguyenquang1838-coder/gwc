#!/usr/bin/env python3
"""Generate canonical G0/G1 artifacts from observed runtime evidence."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ARTIFACTS = {
    "g0": ("g0/context-snapshot.yaml", "g0-context-snapshot.schema.json"),
    "intake": ("g1/intake/g1-intake-brief.yaml", "g1-intake-brief.schema.json"),
    "preflight": ("g1/preflight/g1-preflight-report.yaml", "g1-preflight-report.schema.json"),
}
HIGH_RISK = {"R2", "R3"}
NON_EXECUTABLE = {"UNKNOWN", "HARD_BLOCKED"}
BYPASSABLE = {"OPERATIONAL_ONLY", "MANUAL_CHECKPOINT_ONLY"}
PLAN_REQUIRED = (
    "canonical_task_uid", "repository", "protected_base_sha", "plan_root",
    "requirements_path", "design_path", "tasks_path", "plan_revision",
    "validation_evidence", "generated_by", "generated_at_utc",
)
DELIVERY_ACTIONS = [
    "create_guarded_branch", "modify_scoped_files", "run_sandboxed_validation",
    "push_working_branch", "open_or_update_draft_pr", "monitor_ci",
    "repair_repository_fixable_ci", "independent_g3_review",
    "mark_pr_ready_for_review_after_g3_pass",
]
DELIVERY_NON_GOALS = [
    "merge", "auto_merge", "deploy", "release", "production_config_change",
    "credential_rotation", "production_data_access",
]
PROCESS_SOURCES = [
    "AGENTS.md", "core/GATE_LIFECYCLE_CONTRACT_v1.0.md",
    "core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md",
    "core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md",
]


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _schema_messages(value: Any, path: Path) -> list[str]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [f"{'.'.join(map(str, e.path)) or '<root>'}: {e.message}"
            for e in sorted(validator.iter_errors(value), key=lambda x: list(x.path))]


def _check(i: str, status: str, code: str, message: str, evidence: list[str]) -> dict[str, Any]:
    return {"id": i, "status": status, "code": code, "message": message, "evidence": evidence}


def _blocker(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _selected_connector_available(runtime: dict[str, Any]) -> bool:
    return any(x.get("connector") == runtime["selected_connector"] and x.get("status") == "AVAILABLE"
               for x in runtime.get("connector_fallback_evidence", []))


def _plan_blockers(plan: dict[str, Any] | None, repo: dict[str, Any]) -> list[dict[str, str]]:
    if plan is None:  # legacy input
        return []
    if plan.get("applicability") == "not_applicable":
        return [] if plan.get("source") == "plan_not_applicable" and plan.get("validation_status") == "NOT_APPLICABLE" else [
            _blocker("G1_PLAN_NOT_APPLICABLE_INVALID", "PLAN_NOT_APPLICABLE requires an explicit reason and NOT_APPLICABLE status.")]
    if plan.get("applicability") != "required":
        return [_blocker("G1_PLAN_APPLICABILITY_INVALID", "Plan applicability must be required or not_applicable.")]
    issues: list[dict[str, str]] = []
    missing = [k for k in PLAN_REQUIRED if not plan.get(k)]
    if missing:
        issues.append(_blocker("G1_IMPLEMENTATION_PLAN_MISSING", "Missing implementation-plan fields: " + ", ".join(missing)))
    if plan.get("validation_status") != "PASS":
        issues.append(_blocker("G1_IMPLEMENTATION_PLAN_NOT_VALIDATED", "A required plan must have validation_status=PASS."))
    if plan.get("repository") != repo.get("full_name"):
        issues.append(_blocker("G1_IMPLEMENTATION_PLAN_REPOSITORY_MISMATCH", "Plan repository does not match G0."))
    if plan.get("protected_base_sha") != repo.get("base_sha"):
        issues.append(_blocker("G1_IMPLEMENTATION_PLAN_BASE_MISMATCH", "Plan base SHA does not match G0."))
    if plan.get("source") == "task_me" and plan.get("task_me_invoked") is not True:
        issues.append(_blocker("G1_TASK_ME_NOT_INVOKED", "Task Me source requires invocation evidence."))
    if plan.get("task_me_applicable") and plan.get("task_me_available") and not plan.get("task_me_invoked"):
        issues.append(_blocker("G1_TASK_ME_REQUIRED", "Task Me was applicable and available but not invoked."))
    if plan.get("source") == "generated_kiro" and plan.get("task_me_applicable") and not plan.get("task_me_invoked") and not plan.get("task_me_fallback_reason"):
        issues.append(_blocker("G1_TASK_ME_FALLBACK_REASON_MISSING", "Kiro fallback requires a Task Me fallback reason."))
    return issues


def _route_steps(repo: dict[str, Any], runtime: dict[str, Any], sources_ready: bool,
                 implementation_plan: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    connector = runtime["selected_connector"]
    available = _selected_connector_available(runtime)
    read = "VERIFIED" if repo["verified"] and sources_ready and available else "HARD_BLOCKED"
    write = "VERIFIED" if repo["verified"] and repo["write_enabled"] and available and connector in runtime["connector_priority"] else "HARD_BLOCKED"
    fallbacks = [x for x in runtime["connector_priority"] if x != connector]
    def step(i, name, gate, actor, action, need, status, route, fallback, continuation, evidence, bypass="FORBIDDEN"):
        return {"id": i, "name": name, "gate": gate, "actor": actor, "action_class": action,
                "capability_required": need, "capability_status": status, "primary_route": route,
                "fallback_routes": fallback, "continuation": continuation,
                "expected_evidence": evidence, "bypass_eligibility": bypass}
    steps = [
        step("STEP-01", "protected-base-and-process-readback", "G1_ALIGNMENT", "agent", "read", "repository_read", read, connector, fallbacks, "immediate", "base SHA and process sources"),
        step("STEP-02", "formal-g01-artifact-generation-and-validation", "G1_ALIGNMENT", "agent", "local_validation", "python_jsonschema_validator", "VERIFIED", "generate_g01_runtime + validate_g01", ["repo CI"], "immediate", "validator receipt"),
    ]
    if implementation_plan is not None:
        steps.append(step("STEP-10", "implementation-plan-discovery-validation-and-handoff", "G1_ALIGNMENT", "agent", "planning_and_validation", "task_me_or_kiro_plan", "VERIFIED" if not _plan_blockers(implementation_plan, repo) else "HARD_BLOCKED", implementation_plan.get("source", "unknown"), ["existing Kiro plan", "Task Me", "generated Kiro plan"], "bind exact revision; return to G1 on drift", str(implementation_plan.get("plan_revision") or implementation_plan.get("reason"))))
    steps.extend([
        step("STEP-03", "guarded-branch-creation", "G2_EXECUTION", "agent_or_human", "repository_write", "guarded_branch_create", write, connector, ["human manual UI action"], "checkpoint and readback", "branch equals approved base", "OPERATIONAL_ONLY"),
        step("STEP-04", "scoped-file-write-and-validation", "G2_EXECUTION", "agent", "repository_write", "guarded_file_write_and_validation", write, connector, ["trusted local agent"], "read exact plan before first write; validate diff", "plan-read receipt and validation"),
        step("STEP-05", "draft-pr-delivery", "G3_PR", "agent_or_human", "repository_metadata_write", "draft_pr_create_or_update", write, connector, ["human manual UI action"], "checkpoint and readback", "PR URL and head SHA", "OPERATIONAL_ONLY"),
        step("STEP-06", "exact-head-ci-continuation", "G3_PR", "agent_or_human", "async_read_and_bounded_repair", "ci_status_and_continuation", "VERIFIED", "CI callback or scheduled continuation", ["manual checkpoint"], "continue to terminal exact-head CI", "current-head checks", "MANUAL_CHECKPOINT_ONLY"),
        step("STEP-07", "independent-g3-review", "G3_PR", "agent", "read_only_review", "independent_review_bundle", "VERIFIED", "independent reviewer", ["fresh-context labelled fallback"], "review exact head", "review closure"),
        step("STEP-08", "ready-for-review-promotion", "G3_PR", "agent_or_human", "repository_metadata_write", "mark_pr_ready_for_review", write, connector, ["human manual UI action"], "checkpoint and exact PR readback", "PR ready and head unchanged", "OPERATIONAL_ONLY"),
        step("STEP-09", "merge", "G4_MERGE", "human_authorized_agent", "protected_action", "exact_g4_authority", "SEPARATE_GATE", "exact G4 approval", [], "stop at human boundary", "merge commit"),
    ])
    return steps


def _classify_execution_feasibility(route_steps: list[dict[str, Any]]) -> dict[str, Any]:
    unresolved = [s for s in route_steps if s.get("capability_status") in NON_EXECUTABLE]
    bypass = [s for s in unresolved if s.get("bypass_eligibility") in BYPASSABLE and s.get("fallback_routes")]
    fatal = [s for s in unresolved if s not in bypass]
    outcome = "NOT_EXECUTABLE" if fatal else "EXECUTABLE_WITH_HUMAN_BYPASS" if bypass else "EXECUTABLE"
    return {"outcome": outcome, "route_steps": route_steps,
            "continuation_coverage": "COMPLETE", "human_bypass_required": bool(bypass)}


def generate_artifacts(data: dict[str, Any]) -> tuple[dict[str, Any], str]:
    now, project, repo, runtime, task, request, risk = (data[k] for k in ("generated_at", "project", "repository", "runtime", "task", "request", "risk"))
    sources = data["sources"]
    plan = data.get("implementation_plan_observation")
    trace = {"project_id": project["id"], "repository": repo["full_name"], "task_id": task["id"], "base_sha": repo["base_sha"], "g0_snapshot": "../../g0/context-snapshot.yaml"}
    runtime_context = {"agent_runtime_id": runtime["agent_runtime_id"], "execution_mode": runtime["execution_mode"], "selected_profile": {"id": runtime["selected_profile"]["id"], "path": runtime["selected_profile"]["path"]}, "selected_connector": runtime["selected_connector"], "connector_priority": runtime["connector_priority"], "required_behavior_contracts": [x["path"] for x in runtime["required_behavior_contracts"]]}
    missing_sources = [x["path"] for x in sources if x["required"] and x["status"] != "AVAILABLE"]
    unavailable_contracts = [x["path"] for x in runtime["required_behavior_contracts"] if x["required"] and x["status"] != "AVAILABLE"]
    execution_supported = runtime["execution_mode"] in runtime["selected_profile"]["supported_execution_modes"]
    connector_declared = runtime["selected_connector"] in runtime["connector_priority"]
    connector_available = _selected_connector_available(runtime)
    blockers: list[dict[str, str]] = []
    if not repo["verified"]: blockers.append(_blocker("REPOSITORY_NOT_VERIFIED", "Repository identity is not verified."))
    if missing_sources: blockers.append(_blocker("REQUIRED_SOURCE_UNAVAILABLE", ", ".join(missing_sources)))
    if not execution_supported: blockers.append(_blocker("EXECUTION_MODE_UNSUPPORTED", "Selected runtime profile does not support this execution mode."))
    if unavailable_contracts: blockers.append(_blocker("BEHAVIOR_CONTRACT_UNAVAILABLE", ", ".join(unavailable_contracts)))
    if not connector_declared: blockers.append(_blocker("CONNECTOR_NOT_DECLARED", "Selected connector is absent from connector_priority."))
    if not connector_available: blockers.append(_blocker("SELECTED_CONNECTOR_UNAVAILABLE", "Selected connector lacks AVAILABLE evidence."))
    if not task["claimed"]: blockers.append(_blocker("DS_ADMIN_TASK_NOT_CLAIMED", "The work-tracking task is not claimed."))
    plan_issues = _plan_blockers(plan, repo)
    blockers.extend(plan_issues)
    high = risk["class"] in HIGH_RISK
    if high and not risk["human_direction_confirmed"]: blockers.append(_blocker("HUMAN_DIRECTION_REQUIRED", "R2/R3 requires explicit human direction."))
    sources_ready = not missing_sources
    route = _route_steps(repo, runtime, sources_ready, plan)
    feasibility = _classify_execution_feasibility(route)
    if feasibility["outcome"] == "NOT_EXECUTABLE": blockers.append(_blocker("EXECUTION_ROUTE_NOT_FEASIBLE", "A mandatory route step is hard blocked."))
    intake_ready = bool(request.get("problem", {}).get("statement") and request.get("problem", {}).get("why_now") and request.get("desired_outcome") and request.get("in_scope") and request.get("non_goals") and request.get("acceptance_criteria") and not request.get("unresolved_questions") and all(x.get("verifiable") is True for x in request["acceptance_criteria"]))
    if not intake_ready: blockers.append(_blocker("G1_INTAKE_NEEDS_INPUT", "Intake is incomplete."))
    g0_blockers = [b for b in blockers if b["code"] in {"REPOSITORY_NOT_VERIFIED", "REQUIRED_SOURCE_UNAVAILABLE", "EXECUTION_MODE_UNSUPPORTED", "BEHAVIOR_CONTRACT_UNAVAILABLE", "CONNECTOR_NOT_DECLARED", "SELECTED_CONNECTOR_UNAVAILABLE"}]
    g0 = {"schema_version": "1.0", "artifact_type": "g0-context-snapshot", "generated_at": now, "project": {"id": project["id"], "name": project["name"], "profile_path": project["profile_path"]}, "repository": {k: repo[k] for k in ("full_name", "base_ref", "base_sha", "protected_branches", "connector", "write_enabled")}, "runtime_context": runtime_context, "constraints": request["constraints"], "applicable_policies": data["policies"], "sources": sources, "status": "BLOCKED" if g0_blockers else "READY", "blockers": g0_blockers}
    delivery = {"authorized_actions": DELIVERY_ACTIONS, "downstream_non_goals": DELIVERY_NON_GOALS, "g3_metadata_completion": {"ready_for_review_after_g3_pass": True, "required_evidence": ["exact head SHA", "required CI", "review closure", "scope match"]}}
    intake = {"schema_version": "1.0", "artifact_type": "g1-intake-brief", "generated_at": now, "trace": trace, "problem": request["problem"], "desired_outcome": request["desired_outcome"], "stakeholders": {"requester": request["requester"], "affected": request["affected"]}, "scope": {"in_scope": request["in_scope"], "non_goals": request["non_goals"]}, "constraints": request["constraints"], "assumptions": request["assumptions"], "risks": request["risks"], "acceptance_criteria": request["acceptance_criteria"], "delivery_lifecycle": delivery, "unresolved_questions": request["unresolved_questions"], "status": "READY" if intake_ready else "NEEDS_INPUT"}
    checks = [
        _check("REPO_IDENTITY", "PASS" if repo["verified"] else "FAIL", "REPOSITORY_VERIFIED" if repo["verified"] else "REPOSITORY_NOT_VERIFIED", "Repository identity and base checked.", [repo["full_name"], repo["base_sha"]]),
        _check("TASK_TRACEABILITY", "PASS" if task["claimed"] else "FAIL", "TASK_CLAIMED" if task["claimed"] else "DS_ADMIN_TASK_NOT_CLAIMED", "Task claim checked.", [task["id"]]),
        _check("EXECUTION_MODE_COMPATIBILITY", "PASS" if execution_supported else "FAIL", "EXECUTION_MODE_SUPPORTED" if execution_supported else "EXECUTION_MODE_UNSUPPORTED", "Execution mode compatibility checked.", [runtime["execution_mode"], runtime["selected_profile"]["id"]]),
        _check("BOOTSTRAP_BEHAVIOR_CONTRACTS", "PASS" if not unavailable_contracts else "FAIL", "BEHAVIOR_CONTRACTS_AVAILABLE" if not unavailable_contracts else "BEHAVIOR_CONTRACT_UNAVAILABLE", "Required behavior contracts checked.", [x["path"] for x in runtime["required_behavior_contracts"]]),
        _check("DELIVERY_LIFECYCLE_SCOPE", "PASS", "DELIVERY_LIFECYCLE_DECLARED", "Non-merge lifecycle actions and exclusions are explicit.", DELIVERY_ACTIONS + DELIVERY_NON_GOALS),
        _check("IMPLEMENTATION_PLAN_HANDOFF", "FAIL" if plan_issues else "PASS", plan_issues[0]["code"] if plan_issues else "PLAN_NOT_APPLICABLE" if plan and plan["applicability"] == "not_applicable" else "IMPLEMENTATION_PLAN_VALIDATED", plan_issues[0]["message"] if plan_issues else "Plan route and evidence are complete.", [str((plan or {}).get("plan_revision") or (plan or {}).get("reason") or "legacy")]),
        _check("EXECUTION_FEASIBILITY", "FAIL" if feasibility["outcome"] == "NOT_EXECUTABLE" else "PASS", "END_TO_END_ROUTE_NOT_EXECUTABLE" if feasibility["outcome"] == "NOT_EXECUTABLE" else "END_TO_END_ROUTE_EXECUTABLE", "Execution route classified.", [s["id"] for s in route]),
    ]
    outcome = "PASS" if not blockers else "NEEDS_INPUT" if {b["code"] for b in blockers}.issubset({"G1_INTAKE_NEEDS_INPUT", "HUMAN_DIRECTION_REQUIRED"}) else "BLOCKED"
    preflight = {"schema_version": "1.1" if plan is not None else "1.0", "artifact_type": "g1-preflight-report", "generated_at": now, "trace": trace, "repository_state": {"base_ref": repo["base_ref"], "base_sha": repo["base_sha"], "profile_path": project["profile_path"], "connector": repo["connector"]}, "checks": checks, "process_readback": {"process_id": "governed-repository-delivery", "terminal_outcome": request["desired_outcome"], "required_sources": PROCESS_SOURCES, "status": "VERIFIED" if sources_ready and repo["verified"] else "INCOMPLETE"}, "execution_feasibility": feasibility, "runtime_context": runtime_context, "risk_class": risk["class"], "required_gate": "G2_HUMAN_DIRECTION" if high else "G2_AUTOMATIC_BOUNDED", "blockers": blockers, "outcome": outcome}
    if plan is not None: preflight["implementation_plan"] = plan
    return {"g0": g0, "intake": intake, "preflight": preflight}, outcome


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True); p.add_argument("--root"); p.add_argument("--workspace", default=".gwc"); p.add_argument("--json", action="store_true")
    a = p.parse_args(); root = Path(a.root).resolve() if a.root else Path(__file__).resolve().parents[1]
    source = Path(a.input); source = source if source.is_absolute() else root / source
    workspace = Path(a.workspace); workspace = workspace if workspace.is_absolute() else root / workspace
    try:
        data = _load_yaml(source)
        errors = _schema_messages(data, root / "schemas/g01-runtime-input.schema.json")
        if errors: raise ValueError("runtime input validation failed: " + " | ".join(errors))
        artifacts, outcome = generate_artifacts(data)
        for name, (_, schema) in ARTIFACTS.items():
            errors = _schema_messages(artifacts[name], root / "schemas" / schema)
            if errors: raise ValueError(f"{name} validation failed: " + " | ".join(errors))
        for name, (rel, _) in ARTIFACTS.items():
            path = workspace / rel; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(artifacts[name], sort_keys=False, allow_unicode=True), encoding="utf-8")
    except Exception as exc:
        print(json.dumps({"outcome": "ERROR", "written": False, "error": str(exc)}, indent=2) if a.json else f"ERROR: {exc}")
        return 2
    result = {"outcome": outcome, "written": True, "workspace": str(workspace.resolve()), "artifacts": [x[0] for x in ARTIFACTS.values()]}
    print(json.dumps(result, indent=2) if a.json else f"G01 runtime preflight outcome: {outcome}")
    return 0 if outcome == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
