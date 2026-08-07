#!/usr/bin/env python3
"""Validate bounded autonomous pre-prod standing policy and approved run manifests.

The validator is data-only and deterministic. It never grants live gate authority or
calls GitHub/Jira. Parent run authority is accepted only as a contract projection
when the manifest carries a closed trusted-bot receipt bound to immutable scope.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator, FormatChecker

RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
PROHIBITED_ACTIONS = {
    "direct_write_to_main",
    "direct_write_to_pre_prod",
    "create_or_protect_pre_prod_branch",
    "deploy_approved_release",
    "runtime_reload",
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
}
MANDATORY_CONTROL_PLANE_PROTECTED_PATHS = {
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
    "schemas/approval-envelope.schema.json",
    "schemas/autonomous-preprod-run-policy.schema.json",
    "schemas/autonomous-preprod-run-manifest.schema.json",
    "schemas/autonomous-preprod-g4-receipt.schema.json",
    "schemas/gate-action-authority.schema.json",
    "schemas/node-architect",
    "tools/node_architect",
    "tools/validate_g01.py",
    "tools/validate_gate_action.py",
}
RUN_AUTHORITY_MARKER = "gwc:autonomous-preprod-run-authority-receipt"
GITHUB_ACTIONS_BOT = "github-actions[bot]"
GITHUB_ACTIONS_BOT_COMMENT = "github_actions_bot_comment"
GLOB_META = "*?[]"
GIT_REF_FORBIDDEN = set(" ~^:?*[\\")


def load_document(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle) if path.suffix.lower() == ".json" else yaml.safe_load(handle)


def parse_utc(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be an ISO-8601 UTC timestamp ending in Z")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{field} must be UTC")
    return parsed


def canonical_digest(value: Mapping[str, Any], *, omit: tuple[str, ...] = ()) -> str:
    normalized = copy.deepcopy(dict(value))
    for key in omit:
        normalized.pop(key, None)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def task_scope_hash(task: Mapping[str, Any]) -> str:
    return canonical_digest(task, omit=("scope_hash",))


def manifest_approval_scope_digest(manifest: Mapping[str, Any]) -> str:
    return canonical_digest(manifest, omit=("authority_receipt",))


def authority_receipt_digest(receipt: Mapping[str, Any]) -> str:
    return canonical_digest(receipt)


def _schema_errors(instance: Any, schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    ]


def _repo_path_error(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return "path must be a non-empty string"
    if value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return "leading/trailing whitespace and control characters are forbidden"
    if value.startswith("/"):
        return "absolute paths are forbidden"
    if "\\" in value:
        return "backslash path separators are forbidden"
    if any(char in value for char in GLOB_META):
        return "glob metacharacters are forbidden"
    segments = value.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        return "path must be canonical and must not contain empty, '.' or '..' segments"
    return None


def _branch_name_error(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return "branch must be a non-empty string"
    if value == "@" or value.startswith("/") or value.endswith("/") or value.endswith("."):
        return "branch is not a canonical Git ref name"
    if ".." in value or "@{" in value or "//" in value:
        return "branch contains a forbidden Git ref sequence"
    if any(ord(char) < 32 or ord(char) == 127 or char in GIT_REF_FORBIDDEN for char in value):
        return "branch contains a forbidden Git ref character"
    parts = value.split("/")
    if any(part in {"", ".", ".."} or part.startswith(".") or part.endswith(".lock") for part in parts):
        return "branch contains a forbidden Git ref component"
    return None


def _path_overlaps(path: str, protected: str) -> bool:
    left = path.rstrip("/")
    right = protected.rstrip("/")
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _target_reasons(target: Any) -> tuple[list[str], list[str]]:
    if target == "main":
        return ["AUTONOMOUS_MAIN_TARGET_FORBIDDEN"], ["autonomous target branch must never be main"]
    if target is not None and target != "pre-prod":
        return ["AUTONOMOUS_PREPROD_TARGET_REQUIRED"], ["autonomous integration target must be pre-prod"]
    return [], []


def validate_policy(policy: Mapping[str, Any], *, root: Path, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    reasons, details = _target_reasons(policy.get("target_branch"))
    try:
        errors = _schema_errors(policy, root / "schemas/autonomous-preprod-run-policy.schema.json")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors = [str(exc)]
    if errors:
        reasons.append("AUTONOMOUS_POLICY_INVALID")
        details.extend(errors)
    else:
        if policy.get("allowed_branch_prefix") != "auto/":
            reasons.append("AUTONOMOUS_POLICY_INVALID")
            details.append("allowed_branch_prefix must be exactly auto/")
        if RISK_ORDER.get(str(policy.get("max_child_risk")), 99) > RISK_ORDER["R2"]:
            reasons.append("AUTONOMOUS_POLICY_INVALID")
            details.append("max_child_risk must not exceed R2")
        allowed = set(policy.get("allowed_g2_actions", [])) | set(policy.get("allowed_g4_actions", []))
        denied = set(policy.get("denied_actions", []))
        overlap = sorted(allowed & (denied | PROHIBITED_ACTIONS))
        if overlap:
            reasons.append("AUTONOMOUS_ACTION_FORBIDDEN")
            details.append("policy allows prohibited actions: " + ", ".join(overlap))
        missing_denies = sorted(PROHIBITED_ACTIONS - denied)
        if missing_denies:
            reasons.append("AUTONOMOUS_POLICY_INVALID")
            details.append("policy denied_actions missing: " + ", ".join(missing_denies))
        protected_paths = set(policy.get("control_plane_protected_paths", []))
        missing_protected = sorted(MANDATORY_CONTROL_PLANE_PROTECTED_PATHS - protected_paths)
        if missing_protected:
            reasons.append("AUTONOMOUS_POLICY_INVALID")
            details.append("policy control_plane_protected_paths missing mandatory entries: " + ", ".join(missing_protected))
        for protected_path in protected_paths:
            path_error = _repo_path_error(protected_path)
            if path_error:
                reasons.append("AUTONOMOUS_POLICY_INVALID")
                details.append(f"invalid protected path {protected_path!r}: {path_error}")
        try:
            issued = parse_utc(str(policy["issued_at"]), "policy.issued_at")
            expires = parse_utc(str(policy["expires_at"]), "policy.expires_at")
            if issued > now:
                reasons.append("AUTONOMOUS_POLICY_INVALID")
                details.append("policy is not yet valid")
            if expires <= issued:
                reasons.append("AUTONOMOUS_POLICY_INVALID")
                details.append("policy expires_at must be later than issued_at")
            if expires <= now:
                reasons.append("AUTONOMOUS_POLICY_EXPIRED")
        except (KeyError, ValueError) as exc:
            reasons.append("AUTONOMOUS_POLICY_INVALID")
            details.append(str(exc))
    reasons = _dedupe(reasons)
    try:
        digest = canonical_digest(policy)
    except (TypeError, ValueError) as exc:
        reasons = _dedupe(reasons + ["AUTONOMOUS_POLICY_INVALID"])
        details.append(f"policy canonicalization failed: {exc}")
        digest = None
    return {"outcome": "PASS" if not reasons else "BLOCKED", "reason_codes": reasons, "details": details, "policy_digest": digest}


def _run_authority_errors(
    policy: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    policy_digest: str | None,
    now: datetime,
) -> tuple[list[str], list[str], str | None]:
    code = "AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED"
    receipt = manifest.get("authority_receipt")
    if not isinstance(receipt, Mapping):
        return [code], ["trusted parent run authority receipt is missing"], None
    errors: list[str] = []
    if receipt.get("status") != "present":
        errors.append("authority receipt status must be present")
    if receipt.get("source") != GITHUB_ACTIONS_BOT_COMMENT:
        errors.append("authority receipt source must be github_actions_bot_comment")
    if receipt.get("bot_login") != GITHUB_ACTIONS_BOT:
        errors.append("authority receipt bot_login must be github-actions[bot]")
    if receipt.get("marker") != RUN_AUTHORITY_MARKER:
        errors.append("authority receipt marker mismatch")
    if receipt.get("approved_run_id") != manifest.get("run_id"):
        errors.append("authority receipt run_id mismatch")
    if receipt.get("approved_policy_id") != policy.get("policy_id"):
        errors.append("authority receipt policy_id mismatch")
    if receipt.get("approved_policy_revision") != policy.get("policy_revision"):
        errors.append("authority receipt policy_revision mismatch")
    if receipt.get("approved_policy_digest") != policy_digest:
        errors.append("authority receipt policy_digest mismatch")
    try:
        expected_scope_digest = manifest_approval_scope_digest(manifest)
        if receipt.get("manifest_scope_digest") != expected_scope_digest:
            errors.append("authority receipt manifest_scope_digest mismatch")
        expected_scope_prefix = expected_scope_digest.removeprefix("sha256:")[:16]
        if receipt.get("scope_hash_prefix") != expected_scope_prefix:
            errors.append("authority receipt scope_hash_prefix mismatch")
    except (TypeError, ValueError) as exc:
        errors.append(f"manifest approval scope canonicalization failed: {exc}")
    for field in ("receipt_comment_id", "source_comment_id"):
        value = receipt.get(field)
        if type(value) is not int or value < 1:
            errors.append(f"authority receipt {field} must be a positive integer")
    if receipt.get("receipt_comment_id") == receipt.get("source_comment_id"):
        errors.append("authority receipt comment id must differ from source approval comment id")
    if not isinstance(receipt.get("approval_id"), str) or not receipt.get("approval_id"):
        errors.append("authority receipt approval_id is required")
    try:
        policy_issued = parse_utc(str(policy["issued_at"]), "policy.issued_at")
        policy_expires = parse_utc(str(policy["expires_at"]), "policy.expires_at")
        manifest_issued = parse_utc(str(manifest["issued_at"]), "manifest.issued_at")
        manifest_expires = parse_utc(str(manifest["expires_at"]), "manifest.expires_at")
        receipt_issued = parse_utc(str(receipt["issued_at"]), "authority_receipt.issued_at")
        receipt_expires = parse_utc(str(receipt["expires_at"]), "authority_receipt.expires_at")
        if manifest_issued < policy_issued:
            errors.append("manifest cannot precede policy issue time")
        if receipt_issued < manifest_issued:
            errors.append("authority receipt cannot precede manifest issue time")
        if receipt_issued > now:
            errors.append("authority receipt is not yet valid")
        if receipt_issued >= manifest_expires:
            errors.append("authority receipt must be issued before manifest expiry")
        if receipt_expires <= receipt_issued or receipt_expires <= now:
            errors.append("authority receipt is expired or has invalid expiry")
        if manifest_expires > receipt_expires:
            errors.append("manifest expiry exceeds parent authority expiry")
        if receipt_expires > policy_expires:
            errors.append("parent authority expiry exceeds policy expiry")
    except (KeyError, ValueError) as exc:
        errors.append(str(exc))
    try:
        digest = authority_receipt_digest(receipt)
    except (TypeError, ValueError) as exc:
        errors.append(f"authority receipt canonicalization failed: {exc}")
        digest = None
    return ([code] if errors else []), errors, digest


def validate_manifest(
    policy: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    root: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    policy_result = validate_policy(policy, root=root, now=now)
    reasons = list(policy_result["reason_codes"])
    details = list(policy_result["details"])
    target_reasons, target_details = _target_reasons(manifest.get("target_branch"))
    reasons.extend(target_reasons)
    details.extend(target_details)
    try:
        schema_errors = _schema_errors(manifest, root / "schemas/autonomous-preprod-run-manifest.schema.json")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        schema_errors = [str(exc)]
    if schema_errors:
        reasons.append("AUTONOMOUS_RUN_MANIFEST_INVALID")
        details.extend(schema_errors)

    authority_reasons, authority_details, authority_digest = _run_authority_errors(
        policy, manifest, policy_digest=policy_result.get("policy_digest"), now=now
    )
    reasons.extend(authority_reasons)
    details.extend(authority_details)

    if not schema_errors:
        if manifest.get("repository") != policy.get("repository"):
            reasons.append("AUTONOMOUS_SCOPE_DRIFT")
            details.append("manifest repository does not match policy repository")
        if manifest.get("target_branch") != policy.get("target_branch"):
            reasons.append("AUTONOMOUS_SCOPE_DRIFT")
            details.append("manifest target branch does not match policy target branch")
        if manifest.get("policy_id") != policy.get("policy_id") or manifest.get("policy_revision") != policy.get("policy_revision"):
            reasons.append("AUTONOMOUS_POLICY_REVISION_DRIFT")
        if manifest.get("policy_digest") != policy_result.get("policy_digest"):
            reasons.append("AUTONOMOUS_POLICY_DIGEST_DRIFT")
        if _branch_name_error(manifest.get("approved_base_ref")):
            reasons.append("AUTONOMOUS_RUN_MANIFEST_INVALID")
            details.append("approved_base_ref is not a canonical Git ref name")
        try:
            policy_issued = parse_utc(str(policy["issued_at"]), "policy.issued_at")
            issued = parse_utc(str(manifest["issued_at"]), "manifest.issued_at")
            expires = parse_utc(str(manifest["expires_at"]), "manifest.expires_at")
            policy_expires = parse_utc(str(policy["expires_at"]), "policy.expires_at")
            if issued < policy_issued:
                reasons.append("AUTONOMOUS_RUN_MANIFEST_INVALID")
                details.append("manifest cannot precede policy issue time")
            if issued > now:
                reasons.append("AUTONOMOUS_RUN_MANIFEST_INVALID")
                details.append("manifest is not yet valid")
            if expires <= issued or expires > policy_expires:
                reasons.append("AUTONOMOUS_RUN_MANIFEST_INVALID")
                details.append("manifest expiry must follow issue time and must not exceed policy expiry")
            if expires <= now:
                reasons.append("AUTONOMOUS_RUN_MANIFEST_EXPIRED")
        except (KeyError, ValueError) as exc:
            reasons.append("AUTONOMOUS_RUN_MANIFEST_INVALID")
            details.append(str(exc))

        seen: set[str] = set()
        protected = [str(path) for path in policy.get("control_plane_protected_paths", [])]
        allowed_actions = set(policy.get("allowed_g2_actions", []))
        denied_actions = set(policy.get("denied_actions", [])) | PROHIBITED_ACTIONS
        ceiling = RISK_ORDER.get(str(policy.get("max_child_risk")), -1)
        prefix = str(policy.get("allowed_branch_prefix", ""))
        for task in manifest.get("allowed_tasks", []):
            task_id = str(task.get("task_id", ""))
            if task_id in seen:
                reasons.append("AUTONOMOUS_RUN_MANIFEST_INVALID")
                details.append(f"duplicate task_id: {task_id}")
            seen.add(task_id)
            if RISK_ORDER.get(str(task.get("risk_class")), 99) > ceiling:
                reasons.append("AUTONOMOUS_TASK_RISK_EXCEEDS_CEILING")
                details.append(f"{task_id}: risk exceeds policy ceiling")
            branch = task.get("working_branch")
            branch_error = _branch_name_error(branch)
            if branch_error or branch in {"main", "pre-prod"} or not isinstance(branch, str) or not branch.startswith(prefix):
                reasons.append("AUTONOMOUS_SCOPE_DRIFT")
                details.append(f"{task_id}: working branch violates canonical/prefix/protected-branch rule")
            actions = set(task.get("authorized_g2_actions", []))
            if not actions.issubset(allowed_actions) or actions & denied_actions:
                reasons.append("AUTONOMOUS_ACTION_FORBIDDEN")
                details.append(f"{task_id}: G2 action is outside policy")
            for path in task.get("authorized_paths", []):
                path_text = str(path)
                path_error = _repo_path_error(path_text)
                if path_error:
                    reasons.append("AUTONOMOUS_SCOPE_DRIFT")
                    details.append(f"{task_id}: invalid authorized path {path_text!r}: {path_error}")
                    continue
                if any(_path_overlaps(path_text, denied_path) for denied_path in protected):
                    reasons.append("AUTONOMOUS_CONTROL_PLANE_SELF_MODIFICATION_FORBIDDEN")
                    details.append(f"{task_id}: protected control-plane path in child scope: {path_text}")
            try:
                expected_scope = task_scope_hash(task)
            except (TypeError, ValueError) as exc:
                reasons.append("AUTONOMOUS_SCOPE_DRIFT")
                details.append(f"{task_id}: scope_hash canonicalization failed: {exc}")
            else:
                if task.get("scope_hash") != expected_scope:
                    reasons.append("AUTONOMOUS_SCOPE_DRIFT")
                    details.append(f"{task_id}: scope_hash mismatch")
    reasons = _dedupe(reasons)
    try:
        manifest_digest = canonical_digest(manifest)
        approval_scope_digest = manifest_approval_scope_digest(manifest)
    except (TypeError, ValueError) as exc:
        reasons = _dedupe(reasons + ["AUTONOMOUS_RUN_MANIFEST_INVALID"])
        details.append(f"manifest canonicalization failed: {exc}")
        manifest_digest = None
        approval_scope_digest = None
    return {
        "outcome": "PASS" if not reasons else "BLOCKED",
        "reason_codes": reasons,
        "details": details,
        "policy_digest": policy_result.get("policy_digest"),
        "manifest_digest": manifest_digest,
        "manifest_approval_scope_digest": approval_scope_digest,
        "authority_receipt_digest": authority_digest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--now", help="Override current UTC time for deterministic validation")
    args = parser.parse_args(argv)
    try:
        policy = load_document(args.policy)
        if not isinstance(policy, Mapping):
            raise ValueError("policy must be an object")
        now = parse_utc(args.now, "now") if args.now else None
        if args.manifest:
            manifest = load_document(args.manifest)
            if not isinstance(manifest, Mapping):
                raise ValueError("manifest must be an object")
            result = validate_manifest(policy, manifest, root=args.root, now=now)
        else:
            result = validate_policy(policy, root=args.root, now=now)
    except (OSError, TypeError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        result = {"outcome": "BLOCKED", "reason_codes": ["AUTONOMOUS_POLICY_INVALID"], "details": [str(exc)]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("outcome") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
