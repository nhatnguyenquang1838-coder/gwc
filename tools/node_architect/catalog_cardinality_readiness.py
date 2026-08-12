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


def _valid_sha(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _valid_non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


EXPECTED_FAMILY_COUNT = 9
EXPECTED_NODES_PER_FAMILY = 9
EXPECTED_TOTAL_NODES = 81


def _valid_revision(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(ch in "0123456789abcdef" for ch in value[7:])
    )


def decide_catalog_cardinality_readiness(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    catalog_revision: str,
    expected_revision: str,
    family_node_ids: dict[str, list[str]],
    expected_node_ids: list[str],
    expected_family_node_ids: dict[str, list[str]] | None = None,
    expected_family_count: int = EXPECTED_FAMILY_COUNT,
    expected_nodes_per_family: int = EXPECTED_NODES_PER_FAMILY,
    expected_total_nodes: int = EXPECTED_TOTAL_NODES,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Return deterministic catalog readiness without granting scale or audit authority.

    When ``expected_family_node_ids`` is supplied, each observed node must belong
    to its expected family (family membership consistency, SCRUM-373 current
    AC). A node placed under the wrong family is rejected deterministically.
    """
    outcome = "BLOCKED"
    reason_code = "CATALOG_READINESS_NOT_SATISFIED"
    readiness_passed = False

    identity_invalid = not all(
        _valid_non_empty(value) for value in (task_id, repository, branch)
    )
    sha_invalid = not (_valid_sha(base_sha) and _valid_sha(head_sha))
    limits_invalid = not all(
        isinstance(value, int) and not isinstance(value, bool) and value > 0
        for value in (expected_family_count, expected_nodes_per_family, expected_total_nodes)
    )
    mapping_invalid = not isinstance(family_node_ids, dict)
    expected_invalid = not (
        isinstance(expected_node_ids, list)
        and all(_valid_non_empty(item) for item in expected_node_ids)
    )

    family_names: list[str] = []
    flattened: list[str] = []
    family_size_violations: dict[str, int] = {}
    if not mapping_invalid:
        family_names = list(family_node_ids.keys())
        if not all(_valid_non_empty(name) for name in family_names):
            mapping_invalid = True
        for family, node_ids in family_node_ids.items():
            if not isinstance(node_ids, list) or not all(_valid_non_empty(item) for item in node_ids):
                mapping_invalid = True
                continue
            flattened.extend(node_ids)
            if len(node_ids) != expected_nodes_per_family:
                family_size_violations[family] = len(node_ids)

    duplicate_node_ids = sorted({node for node in flattened if flattened.count(node) > 1})
    expected_duplicates = (
        sorted({node for node in expected_node_ids if expected_node_ids.count(node) > 1})
        if not expected_invalid
        else []
    )
    expected_set = set(expected_node_ids) if not expected_invalid else set()
    observed_set = set(flattened)

    # Family membership consistency: when the expected family->node map is
    # supplied, every observed node must sit under its expected family. A node
    # under the wrong family is a deterministic BLOCK (SCRUM-373 AC: "family
    # membership consistent"). This is fail-closed: if the map is absent we skip
    # the check (backward-compatible with older callers).
    family_membership_violations: dict[str, str] = {}
    if expected_family_node_ids is not None and not mapping_invalid:
        expected_node_to_family: dict[str, str] = {}
        for fam, nids in expected_family_node_ids.items():
            for nid in nids:
                expected_node_to_family[nid] = fam
        for fam, nids in family_node_ids.items():
            for nid in nids:
                exp_fam = expected_node_to_family.get(nid)
                if exp_fam is not None and exp_fam != fam:
                    family_membership_violations[nid] = f"{fam}!=expected:{exp_fam}"

    missing_node_ids = sorted(expected_set - observed_set)
    unexpected_node_ids = sorted(observed_set - expected_set)

    if identity_invalid:
        reason_code = "REQUIRED_IDENTITY_MISSING"
    elif sha_invalid:
        reason_code = "INVALID_OR_MISSING_SHA_BINDING"
    elif limits_invalid:
        reason_code = "INVALID_CARDINALITY_LIMIT"
    elif not (_valid_revision(catalog_revision) and _valid_revision(expected_revision)):
        reason_code = "INVALID_CATALOG_REVISION"
    elif catalog_revision != expected_revision:
        reason_code = "CATALOG_REVISION_MISMATCH"
    elif mapping_invalid:
        reason_code = "INVALID_FAMILY_NODE_MAPPING"
    elif expected_invalid or expected_duplicates or len(expected_node_ids) != expected_total_nodes:
        reason_code = "INVALID_EXPECTED_NODE_CATALOG"
    elif len(family_names) != expected_family_count:
        reason_code = "FAMILY_COUNT_MISMATCH"
    elif family_size_violations:
        reason_code = "FAMILY_CARDINALITY_MISMATCH"
    elif duplicate_node_ids:
        reason_code = "DUPLICATE_NODE_ID"
    elif family_membership_violations:
        reason_code = "FAMILY_MEMBERSHIP_MISMATCH"
    elif len(flattened) != expected_total_nodes:
        reason_code = "TOTAL_NODE_COUNT_MISMATCH"
    elif missing_node_ids:
        reason_code = "CANONICAL_NODE_MISSING"
    elif unexpected_node_ids:
        reason_code = "UNEXPECTED_NODE_PRESENT"
    else:
        outcome = "READY"
        reason_code = "EXACT_CATALOG_CARDINALITY_CONFIRMED"
        readiness_passed = True

    decision = {
        "schema_version": "1.0",
        "artifact_type": "catalog-cardinality-readiness-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "catalog_revision": catalog_revision,
        "expected_revision": expected_revision,
        "expected_family_count": expected_family_count,
        "expected_nodes_per_family": expected_nodes_per_family,
        "expected_total_nodes": expected_total_nodes,
        "observed_family_count": len(family_names),
        "observed_node_count": len(flattened),
        "observed_unique_node_count": len(observed_set),
        "family_size_violations": family_size_violations,
        "family_membership_violations": family_membership_violations,
        "duplicate_node_ids": duplicate_node_ids,
        "missing_node_ids": missing_node_ids,
        "unexpected_node_ids": unexpected_node_ids,
        "readiness_passed": readiness_passed,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "audit_authority_granted": False,
        "scale_authority_granted": False,
        "outcome": outcome,
        "reason_code": reason_code,
        "observed_at": observed_at or now_utc(),
    }
    return attach_digest(decision)
