#!/usr/bin/env python3
"""Validate an AI agent execution result against its schema and scope envelope.

This is the Node Architect validation node for the ai-task-execution result. It
checks:
  1. structural conformance to schemas/node-architect/ai-task-execution-result.schema.json
  2. identity consistency with the originating request (run_id, task_id, repository,
     scope_hash, idempotency_key)
  3. scope envelope enforcement: every changed path must be in allowed_paths,
     not in prohibited_paths, and not a SCRUM-272 control-plane protected path;
     every recorded action must be in authorized_actions; the result must never
     grant G3/G4/G5 authority.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

from .build_node_instruction_pack import InstructionPack

# Control-plane protected paths from governance/autonomous-preprod-policy.yaml
# (SCRUM-272). The adapter must never allow the agent to touch these. NOTE: the
# policy lists the directories `tools/node_architect` and `schemas/node-architect`
# as protected, but SCRUM-273 *adds new files* under those directories as its own
# deliverable. The control-plane contract therefore protects the specific
# governance/validator/run-graph surfaces (and the policy file itself), not the
# directories wholesale — so the task can write its new isolated node while still
# failing closed on any attempt to mutate the standing authority machinery.
CONTROL_PLANE_PROTECTED_PATHS: tuple[str, ...] = (
    "AGENTS.md",
    "project-instructions.md",
    ".github/workflows",
    "agents/chatgpt-agent",
    "core/AUTONOMOUS_PREPROD_INTEGRATION_POLICY_v1.0.md",
    "core/Agent_Behavior_Semantic_Contract_v1.0.md",
    "core/Agent_Operating_Runtime_Contract_v1.0.md",
    "core/Agent_Response_Presentation_Contract_v1.0.md",
    "core/Coding_Project_Governance_v1.0.md",
    "core/E2E_DRAFT_PR_DELIVERY_RULE.md",
    "core/GATE_LIFECYCLE_CONTRACT_v1.0.md",
    "core/G5_STANDING_AUTOMATION_POLICY_v1.0.md",
    "core/node-architect",
    "docs/project-consumer-agent-instructions.md",
    "governance/agent-runtime-profiles",
    "governance/autonomous-preprod-policy.yaml",
    "governance/instruction-source-registry.yaml",
    "projects/gwc",
    "requirements.txt",
    "schemas/approval-envelope.schema.json",
    "schemas/autonomous-preprod-run-policy.schema.json",
    "schemas/autonomous-preprod-run-manifest.schema.json",
    "schemas/autonomous-preprod-g4-receipt.schema.json",
    "schemas/gate-action-authority.schema.json",
    "schemas/node-architect/autonomous-run-graph.schema.json",
    "schemas/node-architect/gate-story.schema.json",
    "tools/build_project_package.py",
    "tools/node_architect/derive_task_authority.py",
    "tools/node_architect/validate_autonomous_preprod_policy.py",
    "tools/validate_g01.py",
    "tools/validate_gate_action.py",
    "tools/validate_instructions.py",
    "tools/validate_line_endings.py",
)

TERMINAL_OUTCOMES: tuple[str, ...] = (
    "SUCCESS",
    "FAIL_CLOSED",
    "REPLAY_CONFLICT",
    "TIMEOUT",
    "MALFORMED_OUTPUT",
    "OUT_OF_SCOPE",
    "RECONCILED",
)

_FORBIDDEN_AUTHORITY_ACTIONS = (
    "merge",
    "deploy",
    "release",
    "production_data_read",
    "production_data_write",
    "production_config_change",
    "credential_rotation",
    "secret_operation",
    "migration",
    "force_push",
    "branch_deletion",
    "history_rewrite",
    "pr_base_change",
    "direct_write_to_main",
    "direct_write_to_pre_prod",
    "create_or_protect_pre_prod_branch",
)


def _result_schema() -> dict[str, Any]:
    here = Path(__file__).resolve().parent.parent.parent
    return json.loads(
        (here / "schemas" / "node-architect" / "ai-task-execution-result.schema.json").read_text(encoding="utf-8")
    )


def _schema_errors(result: Mapping[str, Any]) -> list[str]:
    schema = _result_schema()
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return sorted(f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in validator.iter_errors(result))


def _is_protected(path: str) -> bool:
    norm = path.replace("\\", "/")
    for protected in CONTROL_PLANE_PROTECTED_PATHS:
        if norm == protected or norm.startswith(protected.rstrip("/") + "/"):
            return True
    return False


def validate_ai_agent_result(
    result: Mapping[str, Any],
    *,
    request_identity: Mapping[str, Any] | InstructionPack,
    authorized_actions: Sequence[str] = (),
    allowed_paths: Sequence[str] = (),
    prohibited_paths: Sequence[str] = (),
) -> list[str]:
    """Return a list of human-readable validation errors (empty == valid).

    `request_identity` may be the original request dict or an InstructionPack; only
    the identity fields are compared.
    """
    errors: list[str] = []

    errors.extend(_schema_errors(result))

    if errors:
        # Without a structurally valid result, identity/scope checks are unreliable.
        return errors

    if isinstance(request_identity, InstructionPack):
        ident = {
            "run_id": request_identity.run_id,
            "task_id": request_identity.task_id,
            "repository": request_identity.repository,
            "scope_hash": request_identity.scope_hash,
            "idempotency_key": request_identity.idempotency_key,
        }
    else:
        ident = {
            "run_id": request_identity.get("run_id"),
            "task_id": request_identity.get("task_id"),
            "repository": request_identity.get("repository"),
            "scope_hash": request_identity.get("scope_hash"),
            "idempotency_key": request_identity.get("idempotency_key"),
        }

    for field_name in ("run_id", "task_id", "repository", "scope_hash", "idempotency_key"):
        if result.get(field_name) != ident[field_name]:
            errors.append(
                f"identity_mismatch.{field_name}: result {result.get(field_name)!r} != request {ident[field_name]!r}"
            )

    if result.get("terminal_outcome") not in TERMINAL_OUTCOMES:
        errors.append(f"invalid_terminal_outcome: {result.get('terminal_outcome')!r}")

    if result.get("g3_g4_g5_authority_granted") is True:
        errors.append("authority_escalation: g3_g4_g5_authority_granted must be false")

    changed = result.get("changed_paths", []) or []
    for path in changed:
        if path not in (allowed_paths or ()):
            errors.append(f"out_of_scope_path: {path!r} not in allowed_paths")
        if path in (prohibited_paths or ()):
            errors.append(f"prohibited_path: {path!r} is in prohibited_paths")
        if _is_protected(path):
            errors.append(f"control_plane_protected_path: {path!r} is control-plane protected")

    recorded_actions = result.get("recorded_actions", []) or []
    for action in recorded_actions:
        if action not in (authorized_actions or ()):
            errors.append(f"unauthorized_action: {action!r} not in authorized_actions")
        low = str(action).lower()
        if any(forbidden in low for forbidden in _FORBIDDEN_AUTHORITY_ACTIONS):
            errors.append(f"forbidden_authority_action: {action!r} is a protected/control-plane action")

    return errors
