#!/usr/bin/env python3
"""Validate canonical G0/G1 artifacts and optional G2 plan handoff."""
from __future__ import annotations
import argparse, json, sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ARTIFACTS = {
    "g0": ("g0/context-snapshot.yaml", "g0-context-snapshot.schema.json"),
    "intake": ("g1/intake/g1-intake-brief.yaml", "g1-intake-brief.schema.json"),
    "preflight": ("g1/preflight/g1-preflight-report.yaml", "g1-preflight-report.schema.json"),
    "options": ("g1/brainstorming/g1-options.yaml", "g1-options.schema.json"),
    "decision": ("g1/decision/g1-decision-record.yaml", "g1-decision-record.schema.json"),
}
GATES = {"G2_EXECUTION": "g2/execution-envelope.yaml", "G3_PR": "g3/delivery-record.yaml", "G4_MERGE": "g4/merge-approval.yaml", "G5_DEPLOY": "g5/deployment-approval.yaml", "G6_PRODUCTION_DATA": "g6/production-approval.yaml"}
REQUIRED_EXCLUSIONS = {"G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION"}
NON_EXECUTABLE = {"UNKNOWN", "HARD_BLOCKED"}; BYPASSABLE = {"OPERATIONAL_ONLY", "MANUAL_CHECKPOINT_ONLY"}
PLAN_REQUIRED = ("canonical_task_uid", "repository", "protected_base_sha", "plan_root", "requirements_path", "design_path", "tasks_path", "plan_revision", "validation_evidence", "generated_by", "generated_at_utc")
PLAN_REF_FIELDS = ("applicability", "source", "canonical_task_uid", "repository", "protected_base_sha", "plan_root", "plan_revision", "validation_evidence")

@dataclass(frozen=True)
class ValidationIssue:
    code: str; artifact: str; location: str; message: str

@dataclass(frozen=True)
class ValidationReport:
    outcome: str; issues: list[ValidationIssue]
    @property
    def valid(self) -> bool: return self.outcome == "PASS" and not self.issues
    def to_dict(self) -> dict[str, Any]: return {"outcome": self.outcome, "valid": self.valid, "issues": [asdict(x) for x in self.issues]}


def _yaml(path: Path) -> Any: return yaml.safe_load(path.read_text(encoding="utf-8"))
def _json(path: Path) -> Any: return json.loads(path.read_text(encoding="utf-8"))
def _issue(code: str, artifact: str, location: str, message: str) -> ValidationIssue: return ValidationIssue(code, artifact, location, message)


def _schema_issues(name: str, value: Any, schema_path: Path) -> list[ValidationIssue]:
    schema = _json(schema_path); Draft202012Validator.check_schema(schema)
    v = Draft202012Validator(schema, format_checker=FormatChecker())
    return [_issue("SCHEMA_VALIDATION_ERROR", name, ".".join(map(str, e.path)) or "<root>", e.message)
            for e in sorted(v.iter_errors(value), key=lambda x: list(x.path))]


def _execution_feasibility_issues(preflight: dict[str, Any]) -> list[ValidationIssue]:
    has_r, has_f = "process_readback" in preflight, "execution_feasibility" in preflight
    if not has_r and not has_f: return []
    if has_r != has_f: return [_issue("G1_EXECUTION_FEASIBILITY_INCOMPLETE", "preflight", "<root>", "process_readback and execution_feasibility must be provided together.")]
    issues: list[ValidationIssue] = []; readback = preflight["process_readback"]; feasibility = preflight["execution_feasibility"]; steps = feasibility.get("route_steps", [])
    if readback.get("status") != "VERIFIED": issues.append(_issue("G1_PROCESS_READBACK_INCOMPLETE", "preflight", "process_readback.status", "G1 PASS requires verified process readback."))
    if not steps: return issues + [_issue("G1_EXECUTION_ROUTE_MISSING", "preflight", "execution_feasibility.route_steps", "An end-to-end route is required.")]
    ids = [s.get("id") for s in steps]
    if len(ids) != len(set(ids)): issues.append(_issue("G1_EXECUTION_ROUTE_DUPLICATE_STEP", "preflight", "execution_feasibility.route_steps", "Route IDs must be unique."))
    unresolved = [s for s in steps if s.get("capability_status") in NON_EXECUTABLE]
    bypass = [s for s in unresolved if s.get("bypass_eligibility") in BYPASSABLE and s.get("fallback_routes")]
    fatal = [s for s in unresolved if s not in bypass]
    if fatal: issues.append(_issue("G1_EXECUTION_CAPABILITY_UNVERIFIED", "preflight", "execution_feasibility.route_steps", "Mandatory route steps are not executable: " + ", ".join(str(s.get("id")) for s in fatal)))
    if any(not str(s.get("continuation", "")).strip() for s in steps) or feasibility.get("continuation_coverage") != "COMPLETE": issues.append(_issue("G1_CONTINUATION_COVERAGE_INCOMPLETE", "preflight", "execution_feasibility.continuation_coverage", "Every route step needs continuation coverage."))
    outcome, human = feasibility.get("outcome"), feasibility.get("human_bypass_required") is True
    if outcome == "NOT_EXECUTABLE": issues.append(_issue("G1_EXECUTION_NOT_FEASIBLE", "preflight", "execution_feasibility.outcome", "G1 cannot PASS when the route is not executable."))
    if (human and outcome != "EXECUTABLE_WITH_HUMAN_BYPASS") or (outcome == "EXECUTABLE_WITH_HUMAN_BYPASS" and not human): issues.append(_issue("G1_HUMAN_BYPASS_OUTCOME_MISMATCH", "preflight", "execution_feasibility", "Human-bypass outcome and flag must match."))
    if outcome == "EXECUTABLE_WITH_HUMAN_BYPASS" and not bypass: issues.append(_issue("G1_HUMAN_BYPASS_STEP_MISSING", "preflight", "execution_feasibility.route_steps", "A human-bypass outcome requires a blocked eligible step."))
    if outcome == "EXECUTABLE" and bypass: issues.append(_issue("G1_HUMAN_BYPASS_REQUIRED", "preflight", "execution_feasibility.outcome", "A blocked eligible step requires human-bypass outcome."))
    return issues


def _implementation_plan_issues(preflight: dict[str, Any], decision: dict[str, Any]) -> list[ValidationIssue]:
    has_plan, has_ref = "implementation_plan" in preflight, "implementation_plan_ref" in decision
    if not has_plan and not has_ref:
        return [_issue("G1_IMPLEMENTATION_PLAN_EVIDENCE_MISSING", "preflight", "implementation_plan", "Plan-aware schema version requires preflight and decision plan evidence.")] if preflight.get("schema_version") == "1.1" or decision.get("schema_version") == "1.1" else []
    if has_plan != has_ref: return [_issue("G1_IMPLEMENTATION_PLAN_EVIDENCE_INCOMPLETE", "preflight", "implementation_plan", "Preflight plan and decision plan reference must be provided together.")]
    plan, ref = preflight["implementation_plan"], decision["implementation_plan_ref"]
    issues: list[ValidationIssue] = []
    if plan.get("applicability") == "not_applicable":
        if plan.get("source") != "plan_not_applicable" or plan.get("validation_status") != "NOT_APPLICABLE": issues.append(_issue("G1_PLAN_NOT_APPLICABLE_INVALID", "preflight", "implementation_plan", "Not-applicable plan evidence is inconsistent."))
    elif plan.get("applicability") == "required":
        missing = [k for k in PLAN_REQUIRED if not plan.get(k)]
        if missing: issues.append(_issue("G1_IMPLEMENTATION_PLAN_MISSING", "preflight", "implementation_plan", "Missing fields: " + ", ".join(missing)))
        if plan.get("validation_status") != "PASS": issues.append(_issue("G1_IMPLEMENTATION_PLAN_NOT_VALIDATED", "preflight", "implementation_plan.validation_status", "Required plan validation must PASS."))
        if plan.get("source") == "task_me" and plan.get("task_me_invoked") is not True: issues.append(_issue("G1_TASK_ME_NOT_INVOKED", "preflight", "implementation_plan.task_me_invoked", "Task Me source requires invocation evidence."))
        if plan.get("task_me_applicable") and plan.get("task_me_available") and not plan.get("task_me_invoked"): issues.append(_issue("G1_TASK_ME_REQUIRED", "preflight", "implementation_plan", "Task Me was applicable and available but not invoked."))
        if plan.get("source") == "generated_kiro" and plan.get("task_me_applicable") and not plan.get("task_me_invoked") and not plan.get("task_me_fallback_reason"): issues.append(_issue("G1_TASK_ME_FALLBACK_REASON_MISSING", "preflight", "implementation_plan.task_me_fallback_reason", "Kiro fallback reason is required."))
    else: issues.append(_issue("G1_PLAN_APPLICABILITY_INVALID", "preflight", "implementation_plan.applicability", "Applicability must be required or not_applicable."))
    for key in PLAN_REF_FIELDS:
        if ref.get(key) != plan.get(key): issues.append(_issue("G1_IMPLEMENTATION_PLAN_REFERENCE_MISMATCH", "decision", f"implementation_plan_ref.{key}", f"Decision plan reference does not match preflight: {key}."))
    trace = preflight.get("trace", {})
    if plan.get("repository") != trace.get("repository"): issues.append(_issue("G1_IMPLEMENTATION_PLAN_REPOSITORY_MISMATCH", "preflight", "implementation_plan.repository", "Plan repository does not match trace."))
    if plan.get("protected_base_sha") != trace.get("base_sha"): issues.append(_issue("G1_IMPLEMENTATION_PLAN_BASE_MISMATCH", "preflight", "implementation_plan.protected_base_sha", "Plan base does not match trace."))
    return issues


def _g2_plan_read_issues(workspace: Path, artifacts: dict[str, Any], envelope: dict[str, Any]) -> list[ValidationIssue]:
    plan = artifacts.get("preflight", {}).get("implementation_plan") or envelope.get("implementation_plan")
    if not plan or plan.get("applicability") == "not_applicable": return []
    issues: list[ValidationIssue] = []
    receipt_path = workspace / "g2/plan-read-receipt.yaml"
    if not receipt_path.is_file(): return [_issue("G2_PLAN_READ_RECEIPT_MISSING", "G2_EXECUTION", "g2/plan-read-receipt.yaml", "G2 must read the approved plan before the first write.")]
    try: receipt = _yaml(receipt_path)
    except Exception as exc: return [_issue("G2_PLAN_READ_EVIDENCE_INVALID", "G2_EXECUTION", "g2/plan-read-receipt.yaml", str(exc))]
    expected_paths = {plan.get("requirements_path"), plan.get("design_path"), plan.get("tasks_path")} - {None}
    observed = set(receipt.get("paths_read", []))
    checks = {
        "canonical_task_uid": receipt.get("canonical_task_uid") == plan.get("canonical_task_uid"),
        "repository": receipt.get("repository") == plan.get("repository"),
        "base_sha": receipt.get("base_sha") == plan.get("protected_base_sha"),
        "plan_revision": receipt.get("plan_revision") == plan.get("plan_revision"),
        "paths_read": expected_paths.issubset(observed),
        "scope_consistency": receipt.get("scope_consistency") == "MATCH",
        "repository_state": receipt.get("repository_state") == "MATCH",
        "status": receipt.get("status") == "VERIFIED",
    }
    for field, ok in checks.items():
        if not ok: issues.append(_issue("G2_PLAN_READ_MISMATCH", "G2_EXECUTION", f"plan-read-receipt.{field}", f"G2 plan read check failed: {field}."))
    return issues


def validate_gate_artifact(workspace: Path, gate: str, artifacts: dict[str, Any] | None = None) -> list[ValidationIssue]:
    rel = GATES.get(gate)
    if not rel: return [_issue("GATE_SEQUENCE_INVALID", gate, "gate", f"Unsupported gate: {gate}")]
    path = workspace / rel
    if not path.is_file(): return [_issue("GATE_ARTIFACT_MISSING", gate, rel, f"Required gate artifact is missing: {path}")]
    try: value = _yaml(path)
    except Exception as exc: return [_issue("GATE_ARTIFACT_INVALID", gate, rel, str(exc))]
    if not isinstance(value, dict) or not value: return [_issue("GATE_ARTIFACT_INVALID", gate, rel, "Gate artifact must be a non-empty YAML object.")]
    return _g2_plan_read_issues(workspace, artifacts or {}, value) if gate == "G2_EXECUTION" else []


def _cross_artifact_issues(a: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []; g0, intake, preflight, options, decision = (a[x] for x in ("g0", "intake", "preflight", "options", "decision"))
    traces = [a[x].get("trace") for x in ("intake", "preflight", "options", "decision")]
    if any(x != traces[0] for x in traces[1:]): issues.append(_issue("TRACE_MISMATCH", "g1", "trace", "All G1 artifacts must use the same trace."))
    trace = traces[0] or {}
    if trace.get("project_id") != g0.get("project", {}).get("id") or trace.get("repository") != g0.get("repository", {}).get("full_name") or trace.get("base_sha") != g0.get("repository", {}).get("base_sha"): issues.append(_issue("G0_G1_CONTEXT_MISMATCH", "g1", "trace", "G1 trace does not match G0."))
    if g0.get("status") != "READY" or g0.get("blockers") or any(x.get("required") and x.get("status") != "AVAILABLE" for x in g0.get("sources", [])): issues.append(_issue("G0_NOT_READY", "g0", "status", "G0 must be READY with no blockers."))
    if intake.get("status") != "READY" or not intake.get("scope", {}).get("in_scope") or not intake.get("scope", {}).get("non_goals") or not intake.get("acceptance_criteria") or intake.get("unresolved_questions"): issues.append(_issue("G1_INTAKE_NOT_READY", "intake", "status", "Intake must be complete."))
    if any(not x.get("verifiable") for x in intake.get("acceptance_criteria", [])): issues.append(_issue("G1_ACCEPTANCE_CRITERIA_NOT_VERIFIABLE", "intake", "acceptance_criteria", "All acceptance criteria must be verifiable."))
    if preflight.get("outcome") != "PASS" or preflight.get("blockers") or any(x.get("status") == "FAIL" for x in preflight.get("checks", [])): issues.append(_issue("G1_PREFLIGHT_NOT_PASS", "preflight", "outcome", "Preflight must PASS."))
    issues.extend(_execution_feasibility_issues(preflight)); issues.extend(_implementation_plan_issues(preflight, decision))
    ids = [x.get("id") for x in options.get("options", [])]
    if options.get("status") != "READY" or not ids: issues.append(_issue("G1_OPTIONS_NOT_READY", "options", "status", "Options must be READY."))
    if len(ids) != len(set(ids)): issues.append(_issue("G1_DUPLICATE_OPTION_ID", "options", "options", "Option IDs must be unique."))
    if options.get("recommended_option_id") not in ids: issues.append(_issue("G1_RECOMMENDED_OPTION_NOT_FOUND", "options", "recommended_option_id", "Recommended option is missing."))
    if decision.get("selected_option_id") not in ids: issues.append(_issue("G1_SELECTED_OPTION_NOT_FOUND", "decision", "selected_option_id", "Selected option is missing."))
    criteria = {x.get("id") for x in intake.get("acceptance_criteria", [])}
    if not set(decision.get("acceptance_criteria_refs", [])).issubset(criteria): issues.append(_issue("G1_ACCEPTANCE_REFERENCE_INVALID", "decision", "acceptance_criteria_refs", "Decision references unknown acceptance criteria."))
    excluded = set(decision.get("authority_boundaries", {}).get("excluded", []))
    if decision.get("status") != "ACCEPTED" or decision.get("g1_gate_outcome") != "PASS" or decision.get("user_decision", {}).get("explicit") is not True or not REQUIRED_EXCLUSIONS.issubset(excluded): issues.append(_issue("G1_DECISION_NOT_ACCEPTED", "decision", "status", "PASS requires accepted explicit decision and G4-G6 exclusions."))
    if decision.get("authority_boundaries", {}).get("grants"): issues.append(_issue("G1_AUTHORITY_GRANT_FORBIDDEN", "decision", "authority_boundaries.grants", "G1 cannot grant authority."))
    return issues


def validate_workspace(repo_root: Path, workspace: Path, gate: str | None = None) -> ValidationReport:
    issues: list[ValidationIssue] = []; artifacts: dict[str, Any] = {}
    for name, (rel, schema) in ARTIFACTS.items():
        path, schema_path = workspace / rel, repo_root / "schemas" / schema
        if not path.is_file(): issues.append(_issue("MISSING_ARTIFACT", name, rel, f"Missing: {path}")); continue
        if not schema_path.is_file(): issues.append(_issue("MISSING_SCHEMA", name, str(schema_path), f"Missing: {schema_path}")); continue
        try: artifacts[name] = _yaml(path); issues.extend(_schema_issues(name, artifacts[name], schema_path))
        except Exception as exc: issues.append(_issue("ARTIFACT_LOAD_ERROR", name, rel, str(exc)))
    if len(artifacts) == len(ARTIFACTS) and not any(x.code == "SCHEMA_VALIDATION_ERROR" for x in issues): issues.extend(_cross_artifact_issues(artifacts))
    if gate: issues.extend(validate_gate_artifact(workspace, gate, artifacts))
    return ValidationReport("PASS" if not issues else "BLOCKED", issues)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--root"); p.add_argument("--workspace", default=".gwc"); p.add_argument("--gate", choices=sorted(GATES)); p.add_argument("--json", action="store_true")
    a = p.parse_args(); root = Path(a.root).resolve() if a.root else Path(__file__).resolve().parents[1]; workspace = Path(a.workspace); workspace = workspace if workspace.is_absolute() else root / workspace
    try: report = validate_workspace(root, workspace.resolve(), a.gate)
    except Exception as exc:
        print(json.dumps({"outcome": "ERROR", "valid": False, "error": str(exc)}) if a.json else f"ERROR: {exc}"); return 2
    print(json.dumps(report.to_dict(), indent=2) if a.json else f"G0/G1 validation outcome: {report.outcome}")
    return 0 if report.valid else 1

if __name__ == "__main__": sys.exit(main())
