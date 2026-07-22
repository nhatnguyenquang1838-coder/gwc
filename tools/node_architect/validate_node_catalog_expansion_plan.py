#!/usr/bin/env python3
"""Validate the controlled 81-node catalog expansion plan.

This validator intentionally uses only Python stdlib. It validates the
machine-readable plan beyond generic JSON Schema shape by enforcing GWC-specific
scale-control invariants.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_PREREQUISITES = {
    "runtime_kernel",
    "reference_nodes",
    "checkpoint_engine_contract",
    "failure_simulation_matrix",
}

REQUIRED_VALIDATION_LANES = {
    "schema",
    "registry",
    "gate_authority",
    "side_effects",
    "suspend_resume",
    "failure_mapping",
    "package_export",
}

REQUIRED_EXCLUSIONS = {
    "implement_81_node_catalog",
    "production_runtime_engine",
    "scheduler_worker",
    "merge",
    "auto_merge",
    "deploy_release",
    "production_config_data",
    "secrets_credentials",
    "migration",
    "direct_main_push",
    "force_push_branch_delete_pr_base_change",
}


class ValidationError(Exception):
    """Raised when the plan violates a GWC expansion invariant."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{path}: root must be an object")
    return data


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_plan(plan: dict[str, Any]) -> None:
    _expect(plan.get("task_id") == "REVAMP-GWC-015", "task_id must be REVAMP-GWC-015")
    _expect(plan.get("status") == "plan_only", "status must be plan_only")
    _expect(plan.get("target_total_nodes") == 81, "target_total_nodes must remain 81")
    _expect(plan.get("scale_81_nodes_allowed") is False, "scale_81_nodes_allowed must be false")
    _expect(plan.get("implementation_allowed") is False, "implementation_allowed must be false")
    _expect(plan.get("max_nodes_per_batch") == 9, "max_nodes_per_batch must be exactly 9")

    prerequisites = plan.get("prerequisites", [])
    _expect(isinstance(prerequisites, list), "prerequisites must be a list")
    prereq_ids = {item.get("id") for item in prerequisites if isinstance(item, dict)}
    missing_prereqs = REQUIRED_PREREQUISITES - prereq_ids
    _expect(not missing_prereqs, f"missing prerequisite(s): {sorted(missing_prereqs)}")
    for prereq in prerequisites:
        _expect(isinstance(prereq, dict), "each prerequisite must be an object")
        _expect(prereq.get("status") == "landed", f"prerequisite {prereq.get('id')} must be landed")
        _expect(bool(prereq.get("evidence")), f"prerequisite {prereq.get('id')} needs evidence")

    families = plan.get("node_families", [])
    _expect(isinstance(families, list), "node_families must be a list")
    _expect(len(families) == 9, "node_families must contain exactly 9 families")
    family_ids = []
    total_family_nodes = 0
    for family in families:
        _expect(isinstance(family, dict), "each node family must be an object")
        family_id = family.get("family_id")
        _expect(isinstance(family_id, str) and family_id, "family_id is required")
        _expect(family_id not in family_ids, f"duplicate family_id: {family_id}")
        family_ids.append(family_id)
        planned_nodes = family.get("planned_nodes")
        _expect(planned_nodes == 9, f"{family_id}: planned_nodes must be 9")
        _expect(bool(family.get("authority_boundary")), f"{family_id}: authority_boundary is required")
        total_family_nodes += planned_nodes

    _expect(total_family_nodes == 81, "sum of node_families.planned_nodes must be 81")

    batches = plan.get("batch_sequence", [])
    _expect(isinstance(batches, list), "batch_sequence must be a list")
    _expect(len(batches) == 9, "batch_sequence must contain exactly 9 batches")
    batch_ids = []
    seen_batch_families = []
    for index, batch in enumerate(batches, start=1):
        _expect(isinstance(batch, dict), "each batch must be an object")
        expected_prefix = f"batch-{index:02d}-"
        batch_id = batch.get("batch_id")
        _expect(isinstance(batch_id, str) and batch_id.startswith(expected_prefix), f"batch {index}: id must start with {expected_prefix}")
        _expect(batch_id not in batch_ids, f"duplicate batch_id: {batch_id}")
        batch_ids.append(batch_id)
        family_id = batch.get("family_id")
        _expect(family_id in family_ids, f"{batch_id}: unknown family_id {family_id}")
        _expect(family_id not in seen_batch_families, f"{family_id}: appears in multiple batches")
        seen_batch_families.append(family_id)
        _expect(batch.get("planned_nodes") == 9, f"{batch_id}: planned_nodes must be 9")
        _expect(bool(batch.get("base_requirement")), f"{batch_id}: base_requirement is required")

    _expect(set(seen_batch_families) == set(family_ids), "batch_sequence must cover every family exactly once")

    lanes = set(plan.get("validation_lanes", []))
    _expect(REQUIRED_VALIDATION_LANES <= lanes, f"missing validation lane(s): {sorted(REQUIRED_VALIDATION_LANES - lanes)}")

    exclusions = set(plan.get("explicit_exclusions", []))
    _expect(REQUIRED_EXCLUSIONS <= exclusions, f"missing explicit exclusion(s): {sorted(REQUIRED_EXCLUSIONS - exclusions)}")

    admission_criteria = set(plan.get("admission_criteria", []))
    _expect("previous_batch_merged_to_main" in admission_criteria, "admission criteria must require previous_batch_merged_to_main")
    _expect("exact_post_merge_ci_available" in admission_criteria, "admission criteria must require exact_post_merge_ci_available")
    _expect("no_merge_deploy_or_production_authority_in_batch_scope" in admission_criteria, "admission criteria must keep merge/deploy/prod out of batch scope")

    stop_conditions = set(plan.get("stop_conditions", []))
    _expect("batch_exceeds_max_nodes_per_batch" in stop_conditions, "stop conditions must block oversized batches")
    _expect("production_engine_implementation_requested" in stop_conditions, "stop conditions must block production engine implementation")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("core/node-architect/node-catalog-expansion-plan.json"),
        help="Path to node-catalog-expansion-plan.json",
    )
    args = parser.parse_args(argv)

    try:
        plan = _load_json(args.plan)
        validate_plan(plan)
    except ValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"PASS: {args.plan}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
