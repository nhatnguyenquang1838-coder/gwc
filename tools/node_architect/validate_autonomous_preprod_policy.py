#!/usr/bin/env python3
"""Validate bounded autonomous pre-prod standing policy and run manifests.

The validator is data-only and deterministic. It never grants authority or calls
GitHub/Jira. It returns stable reason codes and canonical SHA-256 digests.
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


def load_document(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        if path.suffix.lower() == ".json":
            return json.load(handle)
        return yaml.safe_load(handle)


def parse_utc(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be an ISO-8601 UTC timestamp ending in Z")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def canonical_digest(value: Mapping[str, Any], *, omit: tuple[str, ...] = ()) -> str:
    normalized = copy.deepcopy(dict(value))
    for key in omit:
        normalized.pop(key, None)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def task_scope_hash(task: Mapping[str, Any]) -> str:
    return canonical_digest(task, omit=("scope_hash",))


def _schema_errors(instance: Any, schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    ]


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


def validate_policy(
    policy: Mapping[str, Any],
    *,
    root: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    reasons, details = _target_reasons(policy.get("target_branch"))
    schema_path = root / "schemas/autonomous-preprod-run-policy.schema.json"
    try:
        errors = _schema_errors(policy, schema_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors = [str(exc)]
    if errors:
        reasons.append("AUTONOMOUS_POLICY_INVALID")
        details.extend(errors)
    else:
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
        try:
            issued = parse_utc(str(policy["issued_at"]), "policy.issued_at")
            expires = parse_utc(str(policy["expires_at"]), "policy.expires_at")
            if expires <= issued:
                reasons.append("AUTONOMOUS_POLICY_INVALID")
                details.append("policy expires_at must be later than issued_at")
            if expires <= now:
                reasons.append("AUTONOMOUS_POLICY_EXPIRED")
        except (KeyError, ValueError) as exc:
            reasons.append("AUTONOMOUS_POLICY_INVALID")
            details.append(str(exc))
    digest = canonical_digest(policy) if isinstance(policy, Mapping) else None
    reasons = _dedupe(reasons)
    return {
        "outcome": "PASS" if not reasons else "BLOCKED",
        "reason_codes": reasons,
        "details": details,
        "policy_digest": digest,
    }


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
    schema_path = root / "schemas/autonomous-preprod-run-manifest.schema.json"
    try:
        schema_errors = _schema_errors(manifest, schema_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        schema_errors = [str(exc)]
    if schema_errors:
        reasons.append("AUTONOMOUS_RUN_MANIFEST_INVALID")
        details.extend(schema_errors)
    else:
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
        try:
            issued = parse_utc(str(manifest["issued_at"]), "manifest.issued_at")
            expires = parse_utc(str(manifest["expires_at"]), "manifest.expires_at")
            policy_expires = parse_utc(str(policy["expires_at"]), "policy.expires_at")
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
            branch = str(task.get("working_branch", ""))
            if branch in {"main", "pre-prod"} or not branch.startswith(prefix):
                reasons.append("AUTONOMOUS_SCOPE_DRIFT")
                details.append(f"{task_id}: working branch violates policy prefix/protected-branch rule")
            actions = set(task.get("authorized_g2_actions", []))
            if not actions.issubset(allowed_actions) or actions & denied_actions:
                reasons.append("AUTONOMOUS_ACTION_FORBIDDEN")
                details.append(f"{task_id}: G2 action is outside policy")
            for path in task.get("authorized_paths", []):
                if any(_path_overlaps(str(path), denied_path) for denied_path in protected):
                    reasons.append("AUTONOMOUS_CONTROL_PLANE_SELF_MODIFICATION_FORBIDDEN")
                    details.append(f"{task_id}: protected control-plane path in child scope: {path}")
            if task.get("scope_hash") != task_scope_hash(task):
                reasons.append("AUTONOMOUS_SCOPE_DRIFT")
                details.append(f"{task_id}: scope_hash mismatch")
    reasons = _dedupe(reasons)
    return {
        "outcome": "PASS" if not reasons else "BLOCKED",
        "reason_codes": reasons,
        "details": details,
        "policy_digest": policy_result.get("policy_digest"),
        "manifest_digest": canonical_digest(manifest) if isinstance(manifest, Mapping) else None,
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
