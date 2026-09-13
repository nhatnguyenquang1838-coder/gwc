#!/usr/bin/env python3
"""Validate canonical G0/G1 lifecycle artifacts.

Exit codes:
- 0: artifacts are valid and the G1 gate evaluates to PASS.
- 1: artifacts are present but invalid, inconsistent, or blocked.
- 2: validator configuration or I/O failed.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ARTIFACTS: dict[str, tuple[str, str]] = {
    "g0": ("g0/context-snapshot.yaml", "g0-context-snapshot.schema.json"),
    "intake": ("g1/intake/g1-intake-brief.yaml", "g1-intake-brief.schema.json"),
    "preflight": ("g1/preflight/g1-preflight-report.yaml", "g1-preflight-report.schema.json"),
    "options": ("g1/brainstorming/g1-options.yaml", "g1-options.schema.json"),
    "decision": ("g1/decision/g1-decision-record.yaml", "g1-decision-record.schema.json"),
}

REQUIRED_EXCLUDED_AUTHORITIES = {"G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION"}
GATE_ARTIFACTS: dict[str, str] = {
    "G2_EXECUTION": "g2/execution-envelope.yaml",
    "G3_PR": "g3/delivery-record.yaml",
    "G4_MERGE": "g4/merge-approval.yaml",
    "G5_DEPLOY": "g5/deployment-approval.yaml",
    "G6_PRODUCTION_DATA": "g6/production-approval.yaml",
}
G2_ENVELOPE_SCHEMA = "g2-execution-envelope.schema.json"
LEGACY_UNVERSIONED_ACTIONS = frozenset({
    "modify_approved_files",
    "run_sandboxed_validation",
    "stage",
    "create_commit",
    "push_working_branch",
})

# Exact historical compatibility registry.  The 14 structural profiles below
# were generated from the 21 committed mapping artifacts in the G2 inventory;
# the remaining 55 committed artifacts were parse failures or non-mappings and
# are intentionally absent.  Each record fingerprint covers the complete YAML
# mapping, so identity, scope, risk, approval, and action fields cannot drift.
LEGACY_UNVERSIONED_PROFILE_REGISTRY = (
    {"allowed_keys":["allowed_paths","approval_command","approved_at","base_sha","branch","excluded_actions","gate","scope_hash","status","task_id"],"paths":[".gwc/tasks/GWC-P1-FOLLOWUP-GRAPH-REVISION/g2/execution-envelope.yaml"],"profile_id":"profile-1","records":[{"fingerprint":"sha256:ff58d37f9916b6cba4cbde901e1ccc0580c599e972683b0c715dabae59a50d63","source_path":".gwc/tasks/GWC-P1-FOLLOWUP-GRAPH-REVISION/g2/execution-envelope.yaml","task_id":"GWC-P1-FOLLOWUP-GRAPH-REVISION"}]},
    {"allowed_keys":["approved_modules","authorized_actions","base_ref","base_sha","excluded_actions","expected_head_sha","expires_at","gate","issued_at","repository","required_checks","risk_class","scope_hash","scope_version","task_id","working_branch"],"paths":[".gwc/tasks/SCRUM-104/g2/execution-envelope.yaml"],"profile_id":"profile-2","records":[{"fingerprint":"sha256:f071ba56bb16208b9979ad4d8702a713e587e0f8c8de6634896408165cdbb180","source_path":".gwc/tasks/SCRUM-104/g2/execution-envelope.yaml","task_id":"SCRUM-104"}]},
    {"allowed_keys":["approval_command","approval_command_format","approval_id","approval_required","artifact_hashes","authority_gate","authorized_actions","base_ref","base_sha","excluded_actions","execution_mode","expires_at","gates_excluded_after_g2","issued_at","modules_or_files","notes","repository","risk_class","scope_hash","scope_hash_16","scope_version","source_instruction","task_id","working_branch"],"paths":[".gwc/tasks/SCRUM-108/g2/execution-envelope.yaml"],"profile_id":"profile-3","records":[{"fingerprint":"sha256:1e56e48415343087ec00a7d0354cdbe1fff06848533987a2f4ffa15df4442dcb","source_path":".gwc/tasks/SCRUM-108/g2/execution-envelope.yaml","task_id":"SCRUM-108"}]},
    {"allowed_keys":["approval_id","approval_readback","approved_at","approved_command","authority_gate","authorized_actions","base_ref","base_sha","excluded_actions","expires_at","issued_at","modules_or_files","repository","risk_class","scope_hash","scope_version","task_id","working_branch"],"paths":[".gwc/tasks/SCRUM-109/g2/execution-envelope.yaml"],"profile_id":"profile-4","records":[{"fingerprint":"sha256:72c8d21208ada6fbe3799ec10b49a9b0b92fbe3ee8be33f2552f9e616b031d33","source_path":".gwc/tasks/SCRUM-109/g2/execution-envelope.yaml","task_id":"SCRUM-109"}]},
    {"allowed_keys":["approval_request_id","approved_modules","authorized_actions","base_ref","base_sha","excluded_actions","expected_head_sha","expires_at","gate","implementation_plan_ref","issued_at","repository","required_checks","risk_class","scope_hash","scope_version","selected_option_id","task_id","working_branch"],"paths":[".gwc/tasks/SCRUM-115/g2/execution-envelope.yaml"],"profile_id":"profile-5","records":[{"fingerprint":"sha256:2850f2d58ac57537d87eaf8cd310fc98a01237fe35ff876ee24f5825e07d56aa","source_path":".gwc/tasks/SCRUM-115/g2/execution-envelope.yaml","task_id":"SCRUM-115"}]},
    {"allowed_keys":["approval_command_format","approval_id","approval_request_id","approval_required","approved_modules","artifact_hashes","authorized_actions","base_ref","base_sha","excluded_actions","execution_mode","expected_head_sha","expires_at","g0_context_ref","g1_decision_ref","gate","gates_excluded_after_g2","implementation_plan_ref","issued_at","notes","plan_read_precondition","repository","required_checks","risk_class","scope_hash","scope_hash_16","scope_version","selected_option_id","source_instruction","task_id","working_branch"],"paths":[".gwc/tasks/SCRUM-116/g2/execution-envelope.yaml"],"profile_id":"profile-6","records":[{"fingerprint":"sha256:f7cd4c9ddfe969f7693490e4c5103ad33bca7b86f3a9d86542c5b211cf645993","source_path":".gwc/tasks/SCRUM-116/g2/execution-envelope.yaml","task_id":"SCRUM-116"}]},
    {"allowed_keys":["approval_request_id","approved_modules","authorized_actions","base_ref","base_sha","excluded_actions","expires_at","gate","issued_at","repository","risk_class","scope_hash","scope_hash_16","status","task_id","working_branch"],"paths":[".gwc/tasks/SCRUM-117/g2/execution-envelope.yaml"],"profile_id":"profile-7","records":[{"fingerprint":"sha256:397e4415ccf13264f3adabcf2a05cdd5eb941042fce78b1bfdcbfdfdbc42d05b","source_path":".gwc/tasks/SCRUM-117/g2/execution-envelope.yaml","task_id":"SCRUM-117"}]},
    {"allowed_keys":["accepted_scrum_117_contract_digest","approval_request_id","approved_modules","authorized_actions","base_ref","base_sha","excluded_actions","expires_at","gate","issued_at","repository","risk_class","scope_hash","scope_hash_16","status","task_id","working_branch"],"paths":[".gwc/tasks/SCRUM-118/g2/execution-envelope.yaml"],"profile_id":"profile-8","records":[{"fingerprint":"sha256:94a83eea64f7480ea20f87df3f8f087b646f2394d21102c277dde213957e53c7","source_path":".gwc/tasks/SCRUM-118/g2/execution-envelope.yaml","task_id":"SCRUM-118"}]},
    {"allowed_keys":["approval_id","approved_files","authority_gate","authorized_actions","base_sha","excluded_actions","expires_at","issued_at","repository","risk_class","scope_hash","task_id","working_branch"],"paths":[".gwc/tasks/SCRUM-138/g2/execution-envelope.yaml",".gwc/tasks/SCRUM-139/g2/execution-envelope.yaml",".gwc/tasks/SCRUM-140/g2/execution-envelope.yaml",".gwc/tasks/SCRUM-143/g2/execution-envelope.yaml"],"profile_id":"profile-9","records":[{"fingerprint":"sha256:445330770fb2b3be911c230d238880f0d5acb74ccc7677b2b81aaa6d82bd681a","source_path":".gwc/tasks/SCRUM-138/g2/execution-envelope.yaml","task_id":"SCRUM-138"},{"fingerprint":"sha256:cfd9eeef8801c69e4424ce5cf20163e5af9eb78b772718c8f92b5f883cec9064","source_path":".gwc/tasks/SCRUM-139/g2/execution-envelope.yaml","task_id":"SCRUM-139"},{"fingerprint":"sha256:0d8a995f1553e1f38dcd55d1974744dae56da2e78901536415f230e6e8157b3a","source_path":".gwc/tasks/SCRUM-140/g2/execution-envelope.yaml","task_id":"SCRUM-140"},{"fingerprint":"sha256:093b00ab86b63b98d76db8fdcb197f10c1d978255917b28e689496b68cc4c48c","source_path":".gwc/tasks/SCRUM-143/g2/execution-envelope.yaml","task_id":"SCRUM-143"}]},
    {"allowed_keys":["approval_command","approval_id","authority_gate","authorized_actions","base_ref","base_sha","excluded_actions","expires_at","head_sha","issued_at","modules_or_files","prior_base_sha","prior_head_sha","project_profile","repository","risk_class","scope_hash","scope_hash_16","scope_version","task_id","work_item","working_branch"],"paths":[".gwc/tasks/SCRUM-185/g2/execution-envelope.yaml",".gwc/tasks/SCRUM-186/g2/execution-envelope.yaml",".gwc/tasks/SCRUM-188/g2/execution-envelope.yaml"],"profile_id":"profile-10","records":[{"fingerprint":"sha256:09e5ed212f84d032eac9110223cc443eb9bccc9df15b380014be9700624bc7bb","source_path":".gwc/tasks/SCRUM-185/g2/execution-envelope.yaml","task_id":"SCRUM-185"},{"fingerprint":"sha256:c950f7ad7241f4d69bc78afa0587ceb0ce605993bf76e23dcfe0001e1328349e","source_path":".gwc/tasks/SCRUM-186/g2/execution-envelope.yaml","task_id":"SCRUM-186"},{"fingerprint":"sha256:ebff839a232dab5d8056b0733a4abb1a996dc3efa279396fa5efbd14ce6aaa9e","source_path":".gwc/tasks/SCRUM-188/g2/execution-envelope.yaml","task_id":"SCRUM-188"}]},
    {"allowed_keys":["approval_command","approval_id","authority_gate","authorized_actions","base_sha","excluded_actions","execution_policy","expires_at","governance","head_sha","issued_at","modules_or_files","prior_base_sha","prior_head_sha","repository","risk_class","scope_hash_16","scope_version","status","task_id","working_branch"],"paths":[".gwc/tasks/SCRUM-190/g2/execution-envelope.yaml",".gwc/tasks/SCRUM-191/g2/execution-envelope.yaml",".gwc/tasks/SCRUM-192/g2/execution-envelope.yaml"],"profile_id":"profile-11","records":[{"fingerprint":"sha256:0f5741f51d932f81c8ef6c3eda8914125d489379692637ff752eb5f199167e79","source_path":".gwc/tasks/SCRUM-190/g2/execution-envelope.yaml","task_id":"SCRUM-190"},{"fingerprint":"sha256:43b9507100bfedeace2ceff12b8238e34e95100474a383f192584a8b7463ba65","source_path":".gwc/tasks/SCRUM-191/g2/execution-envelope.yaml","task_id":"SCRUM-191"},{"fingerprint":"sha256:8ac8897d7dc5890fde9aac7764a67e1f865cc7114fca57e81d9f4f28c1eb3bea","source_path":".gwc/tasks/SCRUM-192/g2/execution-envelope.yaml","task_id":"SCRUM-192"}]},
    {"allowed_keys":["approval_command","approval_id","authority_gate","authorized_actions","base_ref","base_sha","excluded_actions","expires_at","issued_at","modules_or_files","repository","risk_class","scope_hash","scope_hash_16","task_id","working_branch"],"paths":[".gwc/tasks/SCRUM-208/g2/execution-envelope.yaml"],"profile_id":"profile-12","records":[{"fingerprint":"sha256:4bc2cf345af550934aa46d2f957f6befb656539e23d88a7812dd8afd57804759","source_path":".gwc/tasks/SCRUM-208/g2/execution-envelope.yaml","task_id":"SCRUM-208"}]},
    {"allowed_keys":["approval_command","approval_id","authority_gate","authorized_actions","base_ref","base_sha","excluded_actions","expires_at","issued_at","modules_or_files","repository","risk_class","scope_hash","scope_hash_16","subtasks","supersede_reason","supersedes","task_id","working_branch"],"paths":[".gwc/tasks/SCRUM-230/g2/execution-envelope.yaml"],"profile_id":"profile-13","records":[{"fingerprint":"sha256:30edade5d8f93e55fb260d0fd087d492958ea4579d76b299e3407ec694a6ff5f","source_path":".gwc/tasks/SCRUM-230/g2/execution-envelope.yaml","task_id":"SCRUM-230"}]},
    {"allowed_keys":["approval_command","approval_id","authority_gate","authorized_actions","base_ref","base_sha","excluded_actions","expires_at","issued_at","modules_or_files","repository","risk_class","scope_hash","scope_hash_16","subtasks","task_id","working_branch"],"paths":[".gwc/tasks/SCRUM-232/g2/execution-envelope.yaml"],"profile_id":"profile-14","records":[{"fingerprint":"sha256:e6d79bbd858a50df18d053fa083a553fefbf88e675aae7ef3a6da8aebb3be046","source_path":".gwc/tasks/SCRUM-232/g2/execution-envelope.yaml","task_id":"SCRUM-232"}]},
)
NON_EXECUTABLE_CAPABILITY_STATES = {"UNKNOWN", "HARD_BLOCKED"}
BYPASS_ELIGIBLE = {"OPERATIONAL_ONLY", "MANUAL_CHECKPOINT_ONLY"}
IMPLEMENTATION_PLAN_REQUIRED_FIELDS = (
    "canonical_task_uid", "repository", "protected_base_sha", "plan_root",
    "requirements_path", "design_path", "tasks_path", "plan_revision",
    "validation_evidence", "generated_by", "generated_at_utc",
)
PLAN_REF_FIELDS = (
    "applicability", "source", "canonical_task_uid", "repository",
    "protected_base_sha", "plan_root", "plan_revision", "validation_evidence",
)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    artifact: str
    location: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    outcome: str
    issues: list[ValidationIssue]

    @property
    def valid(self) -> bool:
        return not self.issues and self.outcome == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "valid": self.valid,
            "issues": [asdict(issue) for issue in self.issues],
        }


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _issue(code: str, artifact: str, location: str, message: str) -> ValidationIssue:
    return ValidationIssue(code=code, artifact=artifact, location=location, message=message)


def _schema_issues(artifact_name: str, instance: Any, schema_path: Path) -> list[ValidationIssue]:
    schema = _load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[ValidationIssue] = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "<root>"
        issues.append(_issue("SCHEMA_VALIDATION_ERROR", artifact_name, location, error.message))
    return issues


def _legacy_canonical_value(value: Any) -> Any:
    """Convert YAML values into the stable JSON form used by the registry."""
    if isinstance(value, dict):
        return {str(key): _legacy_canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_legacy_canonical_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"unsupported legacy YAML value: {type(value).__name__}")


def _legacy_mapping_fingerprint(artifact: dict[str, Any]) -> str | None:
    """Return the exact registry fingerprint, or None for malformed values."""
    try:
        canonical = json.dumps(
            _legacy_canonical_value(artifact),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _legacy_profile_matches(artifact: dict[str, Any]) -> bool:
    """Match only one of the observed, exact historical mapping profiles."""
    fingerprint = _legacy_mapping_fingerprint(artifact)
    if fingerprint is None:
        return False
    keys = frozenset(artifact.keys())
    for profile in LEGACY_UNVERSIONED_PROFILE_REGISTRY:
        if keys != frozenset(profile["allowed_keys"]):
            continue
        for record in profile["records"]:
            if (
                artifact.get("task_id") == record["task_id"]
                and fingerprint == record["fingerprint"]
            ):
                return True
    return False


def _legacy_unversioned_g2_issues(artifact: Any) -> list[ValidationIssue]:
    """Validate only the explicit, observed pre-versioned G2 signatures."""
    if isinstance(artifact, dict) and _legacy_profile_matches(artifact):
        return []
    return [_issue(
        "G2_LEGACY_UNVERSIONED_SIGNATURE_INVALID",
        "G2_EXECUTION",
        "<root>",
        "Unversioned artifact does not exactly match an observed historical G2 mapping profile.",
    )]


def _implementation_plan_issues(
    preflight: dict[str, Any],
    decision: dict[str, Any],
) -> list[ValidationIssue]:
    """Validate the G1 plan-evidence pair while preserving legacy pair absence."""
    has_plan = "implementation_plan" in preflight
    has_reference = "implementation_plan_ref" in decision
    plan_aware = (
        preflight.get("schema_version") == "1.1"
        or decision.get("schema_version") == "1.1"
    )

    if not has_plan and not has_reference:
        if plan_aware:
            return [_issue(
                "G1_IMPLEMENTATION_PLAN_EVIDENCE_MISSING",
                "preflight",
                "implementation_plan",
                "Plan-aware G1 artifacts require preflight plan evidence and a decision plan reference.",
            )]
        return []
    if has_plan != has_reference:
        return [_issue(
            "G1_IMPLEMENTATION_PLAN_EVIDENCE_INCOMPLETE",
            "preflight",
            "implementation_plan",
            "Preflight implementation_plan and decision implementation_plan_ref must be provided together.",
        )]

    plan = preflight.get("implementation_plan", {})
    reference = decision.get("implementation_plan_ref", {})
    issues: list[ValidationIssue] = []
    applicability = plan.get("applicability")

    if applicability == "not_applicable":
        if (
            plan.get("source") != "plan_not_applicable"
            or plan.get("validation_status") != "NOT_APPLICABLE"
            or not str(plan.get("reason", "")).strip()
        ):
            issues.append(_issue(
                "G1_PLAN_NOT_APPLICABLE_INVALID",
                "preflight",
                "implementation_plan",
                "Not-applicable plan evidence requires an explicit reason, plan_not_applicable source, and NOT_APPLICABLE status.",
            ))
    elif applicability == "required":
        missing = [field for field in IMPLEMENTATION_PLAN_REQUIRED_FIELDS if not plan.get(field)]
        if missing:
            issues.append(_issue(
                "G1_IMPLEMENTATION_PLAN_MISSING",
                "preflight",
                "implementation_plan",
                "Missing implementation-plan fields: " + ", ".join(missing),
            ))
        if plan.get("validation_status") != "PASS":
            issues.append(_issue(
                "G1_IMPLEMENTATION_PLAN_NOT_VALIDATED",
                "preflight",
                "implementation_plan.validation_status",
                "A required implementation plan must have validation_status=PASS.",
            ))
        if plan.get("source") == "task_me" and plan.get("task_me_invoked") is not True:
            issues.append(_issue(
                "G1_TASK_ME_NOT_INVOKED",
                "preflight",
                "implementation_plan.task_me_invoked",
                "Task Me plan source requires invocation evidence.",
            ))
        if (
            plan.get("task_me_applicable") is True
            and plan.get("task_me_available") is True
            and plan.get("task_me_invoked") is not True
        ):
            issues.append(_issue(
                "G1_TASK_ME_REQUIRED",
                "preflight",
                "implementation_plan",
                "Task Me was applicable and available but was not invoked.",
            ))
        if (
            plan.get("source") == "generated_kiro"
            and plan.get("task_me_applicable") is True
            and plan.get("task_me_invoked") is not True
            and not plan.get("task_me_fallback_reason")
        ):
            issues.append(_issue(
                "G1_TASK_ME_FALLBACK_REASON_MISSING",
                "preflight",
                "implementation_plan.task_me_fallback_reason",
                "Kiro fallback requires an explicit Task Me fallback reason.",
            ))
    else:
        issues.append(_issue(
            "G1_PLAN_APPLICABILITY_INVALID",
            "preflight",
            "implementation_plan.applicability",
            "Plan applicability must be required or not_applicable.",
        ))

    for field in PLAN_REF_FIELDS:
        if reference.get(field) != plan.get(field):
            issues.append(_issue(
                "G1_IMPLEMENTATION_PLAN_REFERENCE_MISMATCH",
                "decision",
                f"implementation_plan_ref.{field}",
                f"Decision plan reference does not match preflight field: {field}.",
            ))

    trace = preflight.get("trace", {})
    if plan.get("repository") != trace.get("repository"):
        issues.append(_issue(
            "G1_IMPLEMENTATION_PLAN_REPOSITORY_MISMATCH",
            "preflight",
            "implementation_plan.repository",
            "Implementation-plan repository does not match the G1 trace.",
        ))
    if plan.get("protected_base_sha") != trace.get("base_sha"):
        issues.append(_issue(
            "G1_IMPLEMENTATION_PLAN_BASE_MISMATCH",
            "preflight",
            "implementation_plan.protected_base_sha",
            "Implementation-plan protected base SHA does not match the G1 trace.",
        ))
    return issues


def _g2_plan_read_issues(
    workspace: Path,
    artifacts: dict[str, Any],
    envelope: dict[str, Any],
) -> list[ValidationIssue]:
    """Require a verified exact-plan read receipt before G2 mutation."""
    preflight_plan = artifacts.get("preflight", {}).get("implementation_plan")
    plan = preflight_plan or envelope.get("implementation_plan")
    if not plan or plan.get("applicability") == "not_applicable":
        return []

    receipt_path = workspace / "g2" / "plan-read-receipt.yaml"
    if not receipt_path.is_file():
        return [_issue(
            "G2_PLAN_READ_RECEIPT_MISSING",
            "G2_EXECUTION",
            "g2/plan-read-receipt.yaml",
            "G2 must read the approved implementation plan before the first repository write.",
        )]
    try:
        receipt = _load_yaml(receipt_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [_issue(
            "G2_PLAN_READ_EVIDENCE_INVALID",
            "G2_EXECUTION",
            "g2/plan-read-receipt.yaml",
            f"Plan-read receipt could not be loaded: {exc}",
        )]
    if not isinstance(receipt, dict):
        return [_issue(
            "G2_PLAN_READ_EVIDENCE_INVALID",
            "G2_EXECUTION",
            "g2/plan-read-receipt.yaml",
            "Plan-read receipt must be a YAML object.",
        )]

    expected_paths = {
        plan.get("requirements_path"),
        plan.get("design_path"),
        plan.get("tasks_path"),
    } - {None}
    observed_paths = set(receipt.get("paths_read", []))
    checks = {
        "canonical_task_uid": receipt.get("canonical_task_uid") == plan.get("canonical_task_uid"),
        "repository": receipt.get("repository") == plan.get("repository"),
        "base_sha": receipt.get("base_sha") == plan.get("protected_base_sha"),
        "plan_revision": receipt.get("plan_revision") == plan.get("plan_revision"),
        "paths_read": expected_paths.issubset(observed_paths),
        "scope_consistency": receipt.get("scope_consistency") == "MATCH",
        "repository_state": receipt.get("repository_state") == "MATCH",
        "status": receipt.get("status") == "VERIFIED",
    }
    issues: list[ValidationIssue] = []
    for field, matched in checks.items():
        if not matched:
            issues.append(_issue(
                "G2_PLAN_READ_MISMATCH",
                "G2_EXECUTION",
                f"plan-read-receipt.{field}",
                f"G2 plan-read check failed: {field}.",
            ))
    return issues


def validate_gate_artifact(
    repo_root: Path | str | None = None,
    workspace: Path | str | None = None,
    gate: str | dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
) -> list[ValidationIssue]:
    """Fail closed when an applicable downstream gate artifact is absent or malformed.

    Accept both the current ``(repo_root, workspace, gate, artifacts)`` form and
    the historical ``(workspace, gate, artifacts)`` form. The compatibility
    adapter only supplies the repository root; all existing schema and semantic
    checks remain unchanged.
    """
    if workspace is None:
        return [_issue("GATE_ARTIFACT_INVALID", "gate", "workspace", "Workspace is required.")]
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]
    if isinstance(workspace, str) and (gate is None or isinstance(gate, dict)):
        legacy_workspace = Path(repo_root)
        legacy_gate = workspace
        legacy_artifacts = gate if isinstance(gate, dict) else artifacts
        repo_root = Path(__file__).resolve().parents[1]
        workspace = legacy_workspace
        gate = legacy_gate
        artifacts = legacy_artifacts

    repo_root = Path(repo_root)
    workspace = Path(workspace)
    if not isinstance(gate, str):
        return [_issue("GATE_SEQUENCE_INVALID", "gate", "gate", f"Unsupported downstream gate: {gate}")]
    relative_path = GATE_ARTIFACTS.get(gate)
    if relative_path is None:
        return [_issue("GATE_SEQUENCE_INVALID", gate, "gate", f"Unsupported downstream gate: {gate}")]

    artifact_path = workspace / relative_path
    if not artifact_path.is_file():
        return [_issue("GATE_ARTIFACT_MISSING", gate, relative_path, f"Required gate artifact is missing: {artifact_path}")]

    try:
        artifact = _load_yaml(artifact_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [_issue("GATE_ARTIFACT_INVALID", gate, relative_path, f"Gate artifact could not be loaded: {exc}")]

    if not isinstance(artifact, dict) or not artifact:
        return [_issue("GATE_ARTIFACT_INVALID", gate, relative_path, "Gate artifact must be a non-empty YAML object.")]
    if gate == "G2_EXECUTION":
        schema_path = repo_root / "schemas" / G2_ENVELOPE_SCHEMA
        if not schema_path.is_file():
            return [_issue(
                "GATE_SCHEMA_MISSING",
                gate,
                str(schema_path),
                f"Required G2 envelope schema is missing: {schema_path}",
            )]
        if "schema_version" not in artifact:
            legacy_issues = _legacy_unversioned_g2_issues(artifact)
            if legacy_issues:
                return legacy_issues
            return _g2_plan_read_issues(workspace, artifacts or {}, artifact)
        return _schema_issues(gate, artifact, schema_path) + _g2_plan_read_issues(
            workspace, artifacts or {}, artifact
        )
    return []


def _execution_feasibility_issues(preflight: dict[str, Any]) -> list[ValidationIssue]:
    has_readback = "process_readback" in preflight
    has_feasibility = "execution_feasibility" in preflight

    # Legacy preflight artifacts created before the feasibility extension remain
    # valid when both new fields are absent. New or migrated artifacts must carry
    # the pair together so partial enforcement cannot silently pass.
    if not has_readback and not has_feasibility:
        return []
    if has_readback != has_feasibility:
        return [_issue(
            "G1_EXECUTION_FEASIBILITY_INCOMPLETE",
            "preflight",
            "<root>",
            "process_readback and execution_feasibility must be provided together.",
        )]

    issues: list[ValidationIssue] = []
    readback = preflight.get("process_readback", {})
    feasibility = preflight.get("execution_feasibility", {})
    route_steps = feasibility.get("route_steps", [])

    if readback.get("status") != "VERIFIED":
        issues.append(_issue(
            "G1_PROCESS_READBACK_INCOMPLETE",
            "preflight",
            "process_readback.status",
            "G1 PASS requires verified readback of the governing process and terminal outcome.",
        ))

    if not route_steps:
        issues.append(_issue(
            "G1_EXECUTION_ROUTE_MISSING",
            "preflight",
            "execution_feasibility.route_steps",
            "G1 requires an end-to-end route matrix through the declared terminal outcome.",
        ))
        return issues

    step_ids = [step.get("id") for step in route_steps]
    if len(step_ids) != len(set(step_ids)):
        issues.append(_issue(
            "G1_EXECUTION_ROUTE_DUPLICATE_STEP",
            "preflight",
            "execution_feasibility.route_steps",
            "Execution route step IDs must be unique.",
        ))

    unresolved_steps = [
        step for step in route_steps
        if step.get("capability_status") in NON_EXECUTABLE_CAPABILITY_STATES
    ]
    bypass_steps = [
        step for step in unresolved_steps
        if step.get("bypass_eligibility") in BYPASS_ELIGIBLE
        and bool(step.get("fallback_routes"))
    ]
    bypass_step_ids = {step.get("id") for step in bypass_steps}
    fatal_steps = [step for step in unresolved_steps if step.get("id") not in bypass_step_ids]

    if fatal_steps:
        issues.append(_issue(
            "G1_EXECUTION_CAPABILITY_UNVERIFIED",
            "preflight",
            "execution_feasibility.route_steps",
            "Mandatory route steps are not executable and have no legal HUMAN BYPASS: "
            + ", ".join(str(step.get("id")) for step in fatal_steps)
            + ".",
        ))

    missing_continuation = [
        step.get("id") for step in route_steps if not str(step.get("continuation", "")).strip()
    ]
    if missing_continuation or feasibility.get("continuation_coverage") != "COMPLETE":
        issues.append(_issue(
            "G1_CONTINUATION_COVERAGE_INCOMPLETE",
            "preflight",
            "execution_feasibility.continuation_coverage",
            "Every route step, including async and human-wait steps, requires a continuation rule.",
        ))

    outcome = feasibility.get("outcome")
    human_bypass_required = feasibility.get("human_bypass_required") is True

    if outcome == "NOT_EXECUTABLE":
        issues.append(_issue(
            "G1_EXECUTION_NOT_FEASIBLE",
            "preflight",
            "execution_feasibility.outcome",
            "G1 cannot PASS when the requested terminal outcome is not executable.",
        ))
    if human_bypass_required and outcome != "EXECUTABLE_WITH_HUMAN_BYPASS":
        issues.append(_issue(
            "G1_HUMAN_BYPASS_OUTCOME_MISMATCH",
            "preflight",
            "execution_feasibility",
            "human_bypass_required=true requires EXECUTABLE_WITH_HUMAN_BYPASS.",
        ))
    if outcome == "EXECUTABLE_WITH_HUMAN_BYPASS" and not human_bypass_required:
        issues.append(_issue(
            "G1_HUMAN_BYPASS_OUTCOME_MISMATCH",
            "preflight",
            "execution_feasibility",
            "EXECUTABLE_WITH_HUMAN_BYPASS requires human_bypass_required=true.",
        ))
    if outcome == "EXECUTABLE_WITH_HUMAN_BYPASS" and not bypass_steps:
        issues.append(_issue(
            "G1_HUMAN_BYPASS_STEP_MISSING",
            "preflight",
            "execution_feasibility.route_steps",
            "A human-bypass outcome requires at least one blocked operational step with a legal fallback.",
        ))
    if outcome == "EXECUTABLE" and bypass_steps:
        issues.append(_issue(
            "G1_HUMAN_BYPASS_REQUIRED",
            "preflight",
            "execution_feasibility.outcome",
            "A blocked bypass-eligible step requires EXECUTABLE_WITH_HUMAN_BYPASS.",
        ))
    if outcome == "EXECUTABLE" and human_bypass_required:
        issues.append(_issue(
            "G1_HUMAN_BYPASS_UNEXPECTED",
            "preflight",
            "execution_feasibility.human_bypass_required",
            "EXECUTABLE cannot require HUMAN BYPASS.",
        ))

    return issues


def _cross_artifact_issues(artifacts: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    g0 = artifacts["g0"]
    intake = artifacts["intake"]
    preflight = artifacts["preflight"]
    options = artifacts["options"]
    decision = artifacts["decision"]

    traces = {name: artifact.get("trace") for name, artifact in artifacts.items() if name != "g0"}
    reference_trace = traces["intake"]
    for name, trace in traces.items():
        if trace != reference_trace:
            issues.append(_issue("TRACE_MISMATCH", name, "trace", "All G1 artifacts must use the same trace object."))

    repo = g0.get("repository", {})
    project = g0.get("project", {})
    if reference_trace:
        expected = {
            "project_id": project.get("id"),
            "repository": repo.get("full_name"),
            "base_sha": repo.get("base_sha"),
        }
        for key, value in expected.items():
            if reference_trace.get(key) != value:
                issues.append(_issue(
                    "G0_G1_CONTEXT_MISMATCH", "intake", f"trace.{key}",
                    f"G1 trace {key} does not match the G0 snapshot.",
                ))

    required_sources_missing = [
        item.get("path") for item in g0.get("sources", [])
        if item.get("required") and item.get("status") != "AVAILABLE"
    ]
    if g0.get("status") != "READY" or g0.get("blockers") or required_sources_missing:
        issues.append(_issue("G0_NOT_READY", "g0", "status", "G0 must be READY with no blockers and all required sources available."))

    scope = intake.get("scope", {})
    criteria = intake.get("acceptance_criteria", [])
    if (
        intake.get("status") != "READY"
        or not scope.get("in_scope")
        or not scope.get("non_goals")
        or not criteria
        or intake.get("unresolved_questions")
    ):
        issues.append(_issue(
            "G1_INTAKE_NOT_READY", "intake", "status",
            "READY intake requires scope, non-goals, acceptance criteria, and no unresolved questions.",
        ))
    if any(not item.get("verifiable") for item in criteria):
        issues.append(_issue(
            "G1_ACCEPTANCE_CRITERIA_NOT_VERIFIABLE", "intake", "acceptance_criteria",
            "Every acceptance criterion must be verifiable.",
        ))

    failed_checks = [item.get("id") for item in preflight.get("checks", []) if item.get("status") == "FAIL"]
    if preflight.get("outcome") != "PASS" or preflight.get("blockers") or failed_checks:
        issues.append(_issue(
            "G1_PREFLIGHT_NOT_PASS", "preflight", "outcome",
            "Preflight must PASS with no blockers or failed checks.",
        ))
    issues.extend(_execution_feasibility_issues(preflight))
    issues.extend(_implementation_plan_issues(preflight, decision))

    option_items = options.get("options", [])
    option_ids = [item.get("id") for item in option_items]
    if len(option_ids) != len(set(option_ids)):
        issues.append(_issue("G1_DUPLICATE_OPTION_ID", "options", "options", "Option IDs must be unique."))
    if options.get("status") != "READY" or not option_items:
        issues.append(_issue("G1_OPTIONS_NOT_READY", "options", "status", "Options must be READY and contain at least one option."))
    recommended = options.get("recommended_option_id")
    if recommended is not None and recommended not in option_ids:
        issues.append(_issue(
            "G1_RECOMMENDED_OPTION_NOT_FOUND", "options", "recommended_option_id",
            "The recommended option must exist in options.",
        ))

    selected = decision.get("selected_option_id")
    if selected not in option_ids:
        issues.append(_issue(
            "G1_SELECTED_OPTION_NOT_FOUND", "decision", "selected_option_id",
            "The selected option must exist in the options artifact.",
        ))

    criterion_ids = {item.get("id") for item in criteria}
    referenced_criteria = set(decision.get("acceptance_criteria_refs", []))
    if not referenced_criteria or not referenced_criteria.issubset(criterion_ids):
        issues.append(_issue(
            "G1_ACCEPTANCE_REFERENCE_INVALID", "decision", "acceptance_criteria_refs",
            "Decision acceptance criteria must reference intake criteria.",
        ))

    excluded = set(decision.get("authority_boundaries", {}).get("excluded", []))
    explicit_decision = decision.get("user_decision", {}).get("explicit") is True
    if (
        decision.get("status") != "ACCEPTED"
        or decision.get("g1_gate_outcome") != "PASS"
        or not explicit_decision
        or not REQUIRED_EXCLUDED_AUTHORITIES.issubset(excluded)
    ):
        issues.append(_issue(
            "G1_DECISION_NOT_ACCEPTED", "decision", "status",
            "A PASS decision must be ACCEPTED, explicit, and exclude G4 merge, G5 deploy, and G6 production authority.",
        ))

    if decision.get("authority_boundaries", {}).get("grants"):
        issues.append(_issue(
            "G1_AUTHORITY_GRANT_FORBIDDEN", "decision", "authority_boundaries.grants",
            "A G1 decision cannot grant execution, merge, deploy, or production authority.",
        ))
    return issues


def validate_workspace(repo_root: Path, workspace: Path, gate: str | None = None) -> ValidationReport:
    issues: list[ValidationIssue] = []
    artifacts: dict[str, Any] = {}

    for name, (relative_path, schema_name) in ARTIFACTS.items():
        artifact_path = workspace / relative_path
        schema_path = repo_root / "schemas" / schema_name
        if not artifact_path.is_file():
            issues.append(_issue("MISSING_ARTIFACT", name, relative_path, f"Required artifact is missing: {artifact_path}"))
            continue
        if not schema_path.is_file():
            issues.append(_issue("MISSING_SCHEMA", name, str(schema_path), f"Required schema is missing: {schema_path}"))
            continue
        try:
            artifact = _load_yaml(artifact_path)
            artifacts[name] = artifact
            issues.extend(_schema_issues(name, artifact, schema_path))
        except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
            issues.append(_issue("ARTIFACT_LOAD_ERROR", name, relative_path, str(exc)))

    if len(artifacts) == len(ARTIFACTS) and not any(issue.code == "SCHEMA_VALIDATION_ERROR" for issue in issues):
        issues.extend(_cross_artifact_issues(artifacts))
    if gate is not None:
        issues.extend(validate_gate_artifact(repo_root, workspace, gate, artifacts))

    return ValidationReport(outcome="PASS" if not issues else "BLOCKED", issues=issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="Repository root; defaults to the parent of tools/.")
    parser.add_argument("--workspace", default=".gwc", help="G0/G1 workspace path, relative to the repository root unless absolute.")
    parser.add_argument("--gate", choices=sorted(GATE_ARTIFACTS), default=None, help="Require the applicable downstream gate artifact in this task workspace.")
    parser.add_argument("--json", action="store_true", help="Emit a JSON report.")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    workspace = Path(args.workspace)
    if not workspace.is_absolute():
        workspace = repo_root / workspace

    try:
        report = validate_workspace(repo_root, workspace.resolve(), gate=args.gate)
    except Exception as exc:  # configuration-level failure
        if args.json:
            print(json.dumps({"outcome": "ERROR", "valid": False, "error": str(exc)}))
        else:
            print(f"ERROR: {exc}")
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"G0/G1 validation outcome: {report.outcome}")
        for issue in report.issues:
            print(f"{issue.code}: {issue.artifact}:{issue.location}: {issue.message}")
    return 0 if report.valid else 1


if __name__ == "__main__":
    sys.exit(main())
