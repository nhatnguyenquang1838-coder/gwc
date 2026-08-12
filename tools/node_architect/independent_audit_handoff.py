#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def attach_digest(decision: dict[str, Any]) -> dict[str, Any]:
    decision["decision_digest"] = digest_payload(
        {key: value for key, value in decision.items() if key != "decision_digest"}
    )
    return decision


def _valid_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(ch in "0123456789abcdef" for ch in value[7:])
    )


def _valid_non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


REQUIRED_LIMITATIONS = {
    "no_production_scale_authority",
    "no_deployment_authority",
    "independent_audit_required",
}
REQUIRED_CI = {"Validate instructions", "Build instruction packages"}


def _valid_manifest(manifest: object) -> bool:
    return (
        isinstance(manifest, dict)
        and isinstance(manifest.get("families"), int)
        and not isinstance(manifest.get("families"), bool)
        and isinstance(manifest.get("nodes"), int)
        and not isinstance(manifest.get("nodes"), bool)
        and isinstance(manifest.get("artifacts"), list)
        and all(_valid_non_empty(item) for item in manifest.get("artifacts", []))
    )


_ALLOWED_EVIDENCE_STATUS = {"proven", "missing", "stale", "partial"}


def _valid_evidence_map(evidence_map: object) -> bool:
    """An evidence map is optional; when present every entry must bind a
    non-empty requirement to an explicit status. Missing/stale evidence is
    intentionally carried (status != 'proven'), not rejected here."""
    if evidence_map is None:
        return True
    if not isinstance(evidence_map, list):
        return False
    for item in evidence_map:
        if not isinstance(item, dict):
            return False
        if not _valid_non_empty(item.get("requirement")):
            return False
        if item.get("status") not in _ALLOWED_EVIDENCE_STATUS:
            return False
    return True


def _valid_ci(item: object) -> bool:
    return (
        isinstance(item, dict)
        and _valid_non_empty(item.get("workflow"))
        and isinstance(item.get("run_id"), int)
        and not isinstance(item.get("run_id"), bool)
        and item["run_id"] > 0
        and item.get("conclusion") in {"success", "failure", "cancelled", "timed_out"}
        and _valid_sha(item.get("head_sha"))
    )


def decide_independent_audit_handoff(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    package_revision: str,
    expected_revision: str,
    completeness_manifest: dict[str, Any],
    ci_evidence: list[dict[str, Any]],
    limitation_disclosures: list[str],
    reviewer: str,
    implementer: str | None = None,
    evidence_map: list[dict[str, Any]] | None = None,
    dag_dependencies: list[str] | None = None,
    exclusions: list[str] | None = None,
    findings: list[str] | None = None,
    unresolved_risks: list[str] | None = None,
    next_legal_action: str | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Prepare an independent-audit handoff without granting audit or scale authority."""
    handoff_status = "BLOCKED"
    reason_code = "AUDIT_HANDOFF_NOT_READY"

    identity_invalid = not all(_valid_non_empty(value) for value in (task_id, repository, branch, reviewer))
    sha_invalid = not (_valid_sha(base_sha) and _valid_sha(head_sha))
    revision_invalid = not (_valid_digest(package_revision) and _valid_digest(expected_revision))
    manifest_invalid = not _valid_manifest(completeness_manifest)
    ci_invalid = not (isinstance(ci_evidence, list) and ci_evidence and all(_valid_ci(item) for item in ci_evidence))
    limitations_invalid = not (
        isinstance(limitation_disclosures, list)
        and all(_valid_non_empty(item) for item in limitation_disclosures)
        and REQUIRED_LIMITATIONS.issubset(set(limitation_disclosures))
    )

    ci_by_name = {} if ci_invalid else {item["workflow"]: item for item in ci_evidence if item["head_sha"] == head_sha}
    missing_ci_workflows = [] if ci_invalid else sorted(REQUIRED_CI - set(ci_by_name))
    failed_ci_workflows = [] if ci_invalid else sorted(name for name, item in ci_by_name.items() if item["conclusion"] != "success")

    evidence_map_invalid = not _valid_evidence_map(evidence_map)
    unverified_evidence = (
        [] if evidence_map_invalid or not evidence_map
        else [item["requirement"] for item in evidence_map if item.get("status") != "proven"]
    )

    if identity_invalid:
        reason_code = "REQUIRED_IDENTITY_MISSING"
    elif sha_invalid:
        reason_code = "INVALID_OR_MISSING_SHA_BINDING"
    elif revision_invalid:
        reason_code = "INVALID_PACKAGE_REVISION"
    elif package_revision != expected_revision:
        reason_code = "PACKAGE_REVISION_MISMATCH"
    elif manifest_invalid:
        reason_code = "INVALID_COMPLETENESS_MANIFEST"
    elif completeness_manifest["families"] != 9:
        reason_code = "FAMILY_COUNT_MISMATCH"
    elif completeness_manifest["nodes"] != 81:
        reason_code = "NODE_COUNT_MISMATCH"
    elif not completeness_manifest["artifacts"]:
        reason_code = "HANDOFF_ARTIFACTS_MISSING"
    elif ci_invalid:
        reason_code = "INVALID_CI_EVIDENCE"
    elif missing_ci_workflows:
        reason_code = "REQUIRED_CI_EVIDENCE_MISSING"
    elif failed_ci_workflows:
        reason_code = "REQUIRED_CI_FAILED"
    elif limitations_invalid:
        reason_code = "LIMITATION_DISCLOSURE_INCOMPLETE"
    elif evidence_map_invalid:
        reason_code = "INVALID_EVIDENCE_MAP"
    elif implementer and reviewer and implementer == reviewer:
        reason_code = "REVIEWER_CONFLICT"
    else:
        handoff_status = "READY_FOR_INDEPENDENT_AUDIT"
        reason_code = "REVISION_BOUND_AUDIT_HANDOFF_READY"

    decision = {
        "schema_version": "1.0",
        "artifact_type": "independent-audit-handoff-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "package_revision": package_revision,
        "expected_revision": expected_revision,
        "completeness_manifest": completeness_manifest if isinstance(completeness_manifest, dict) else {},
        "missing_ci_workflows": missing_ci_workflows,
        "failed_ci_workflows": failed_ci_workflows,
        "limitation_disclosures": sorted(limitation_disclosures) if isinstance(limitation_disclosures, list) else [],
        "reviewer": reviewer,
        "implementer": implementer,
        "reviewer_independent": not (implementer and reviewer and implementer == reviewer),
        "evidence_map": evidence_map if isinstance(evidence_map, list) else [],
        "unverified_evidence": unverified_evidence,
        "dag_dependencies": dag_dependencies if isinstance(dag_dependencies, list) else [],
        "exclusions": exclusions if isinstance(exclusions, list) else [],
        "findings": findings if isinstance(findings, list) else [],
        "unresolved_risks": unresolved_risks if isinstance(unresolved_risks, list) else [],
        "next_legal_action": next_legal_action or "",
        "handoff_status": handoff_status,
        "reason_code": reason_code,
        "read_only_projection": True,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "audit_completion_authority_granted": False,
        "scale_authority_granted": False,
        "observed_at": observed_at or now_utc(),
    }
    return attach_digest(decision)
