#!/usr/bin/env python3
"""Validate the SCRUM-150 cross-phase evidence contract.

This validator is deliberately pure: it reads an observed JSON record and
returns typed failures. It never executes a provider, mutates a checkpoint,
changes a gate, writes a projection, or promotes a candidate.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


TASK_ID = "SCRUM-150"
CHAIN_ID = "SCRUM-147-151"
DEPENDENCY_IDS = ["SCRUM-147", "SCRUM-148", "SCRUM-149", "SCRUM-151"]
REQUIRED_METRICS = {
    "evidence-completeness",
    "outcome-comparison-accuracy",
    "recovery-success-rate",
}
REQUIRED_GATES = ["G2", "G4", "G5"]


def issue(code: str, message: str, location: str = "<root>") -> dict[str, str]:
    return {"code": code, "message": message, "location": location}


def _is_sha(value: Any, length: int | None = None) -> bool:
    if not isinstance(value, str):
        return False
    if length is not None and len(value) != length:
        return False
    return bool(value) and all(char in "0123456789abcdef" for char in value)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _validate_ci(binding: dict[str, Any], location: str, merge_sha: str) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    runs = _as_list(binding.get("ci_runs"))
    if not runs:
        return [issue("CI_EVIDENCE_MISSING", "exact required CI runs are required", f"{location}.ci_runs")]
    for index, run in enumerate(runs):
        run_location = f"{location}.ci_runs[{index}]"
        if not isinstance(run, dict):
            problems.append(issue("CI_EVIDENCE_INVALID", "CI run must be an object", run_location))
            continue
        if not _nonempty(run.get("workflow")):
            problems.append(issue("CI_EVIDENCE_INVALID", "CI workflow name is required", f"{run_location}.workflow"))
        if run.get("head_sha") != merge_sha or run.get("merge_sha") != merge_sha:
            problems.append(issue("CI_SHA_MISMATCH", "selected CI run must bind to the exact merge SHA", run_location))
        if run.get("conclusion") != "success":
            problems.append(issue("CI_NOT_SUCCESS", "required exact-SHA CI run must conclude success", f"{run_location}.conclusion"))
    return problems


def _validate_binding(binding: Any, location: str, composite_base_sha: str) -> list[dict[str, str]]:
    if not isinstance(binding, dict):
        return [issue("EXACT_BINDING_MISSING", "exact source/base/head/merge binding is required", location)]
    problems: list[dict[str, str]] = []
    for field, length in (("source_sha", None), ("base_sha", 40), ("head_sha", 40), ("merge_sha", 40)):
        if not _is_sha(binding.get(field), length):
            problems.append(issue("EXACT_BINDING_INVALID", f"{field} must be an exact lowercase SHA", f"{location}.{field}"))
    if binding.get("rebaseline_sha") != composite_base_sha or binding.get("rebaseline_status") != "PASS":
        problems.append(issue("STALE_DEPENDENCY_EVIDENCE", "dependency evidence must be rebaselined to the composite base", location))
    merge_sha = binding.get("merge_sha")
    if _is_sha(merge_sha, 40):
        problems.extend(_validate_ci(binding, location, merge_sha))
    return problems


def _validate_metric(metric: Any, index: int, history_ids: set[str]) -> list[dict[str, str]]:
    location = f"p5.metrics[{index}]"
    if not isinstance(metric, dict):
        return [issue("METRIC_INVALID", "metric must be an object", location)]
    problems: list[dict[str, str]] = []
    metric_id = metric.get("metric_id")
    numerator = metric.get("numerator")
    denominator = metric.get("denominator")
    value = metric.get("value")
    if not _nonempty(metric_id):
        problems.append(issue("METRIC_INVALID", "metric_id is required", f"{location}.metric_id"))
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)) or denominator <= 0:
        problems.append(issue("METRIC_PROVENANCE_MISSING", "metric needs a positive denominator and numeric numerator", location))
    elif not isinstance(value, (int, float)) or abs(float(value) - float(numerator) / float(denominator)) > 1e-9:
        problems.append(issue("METRIC_VALUE_FABRICATED", "metric value must equal numerator divided by denominator", f"{location}.value"))
    observed = {str(item) for item in _as_list(metric.get("observed_event_ids"))}
    if not observed or not observed <= history_ids:
        problems.append(issue("METRIC_PROVENANCE_MISSING", "metric must reference observed history event IDs", f"{location}.observed_event_ids"))
    return problems


def validate_record(record: dict[str, Any]) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    if record.get("schema_version") != "0.1":
        problems.append(issue("SCHEMA_VERSION_MISMATCH", "schema_version must be 0.1", "schema_version"))
    if record.get("task_id") != TASK_ID:
        problems.append(issue("TASK_MISMATCH", "task_id must be SCRUM-150", "task_id"))
    if record.get("chain_id") != CHAIN_ID or record.get("linked_task_ids") != DEPENDENCY_IDS:
        problems.append(issue("DEPENDENCY_CHAIN_MISMATCH", "linked_task_ids must preserve SCRUM-147 through SCRUM-151 order", "linked_task_ids"))
    repository = record.get("repository")
    if repository != "nhatnguyenquang1838-coder/gwc":
        problems.append(issue("REPOSITORY_MISMATCH", "record must bind to the GWC repository", "repository"))
    composite_base = record.get("composite_base_sha")
    if not _is_sha(composite_base, 40):
        problems.append(issue("EXACT_BINDING_INVALID", "composite_base_sha must be an exact SHA", "composite_base_sha"))

    dependencies = _as_list(record.get("dependencies"))
    observed_dependency_ids = [item.get("task_id") for item in dependencies if isinstance(item, dict)]
    if observed_dependency_ids != DEPENDENCY_IDS:
        problems.append(issue("DEPENDENCY_EVIDENCE_MISSING", "all four dependency evidence records are required in order", "dependencies"))
    for index, dependency in enumerate(dependencies):
        if not isinstance(dependency, dict):
            problems.append(issue("DEPENDENCY_EVIDENCE_INVALID", "dependency must be an object", f"dependencies[{index}]"))
            continue
        location = f"dependencies[{index}]"
        if dependency.get("status") != "PASS":
            problems.append(issue("DEPENDENCY_EVIDENCE_INVALID", "dependency evidence must be PASS", f"{location}.status"))
        if not _nonempty(dependency.get("evidence_ref")):
            problems.append(issue("DEPENDENCY_EVIDENCE_MISSING", "dependency evidence_ref is required", f"{location}.evidence_ref"))
        problems.extend(_validate_binding(dependency.get("binding"), f"{location}.binding", composite_base))

    replay = record.get("replay") or {}
    if replay.get("terminal_state_first") != replay.get("terminal_state_replayed"):
        if not isinstance(replay.get("typed_live_state_divergence"), dict) or not replay.get("typed_live_state_divergence"):
            problems.append(issue("REPLAY_DIVERGENCE", "replay mismatch needs typed live-state divergence", "replay"))
    if replay.get("route_matches") is not True or replay.get("decision_matches") is not True:
        if not isinstance(replay.get("typed_live_state_divergence"), dict) or not replay.get("typed_live_state_divergence"):
            problems.append(issue("REPLAY_DIVERGENCE", "route and decision replay must match or carry typed divergence", "replay"))
    if replay.get("duplicate_external_effects") != 0:
        problems.append(issue("DUPLICATE_SIDE_EFFECT", "replay must report zero duplicate external effects", "replay.duplicate_external_effects"))
    side_effect_keys = _as_list(replay.get("side_effect_idempotency_keys"))
    if len(side_effect_keys) != len(set(side_effect_keys)):
        problems.append(issue("DUPLICATE_SIDE_EFFECT", "side-effect idempotency keys must be unique", "replay.side_effect_idempotency_keys"))

    controls = record.get("human_controls") or {}
    for field in ("interrupt_resume_audited", "audited_bypass", "canonical_continues_on_projection_outage"):
        if controls.get(field) is not True:
            problems.append(issue("HUMAN_CONTROL_MISSING", f"{field} must remain true", f"human_controls.{field}"))

    for gate in REQUIRED_GATES:
        binding = (record.get("gate_bindings") or {}).get(gate)
        problems.extend(_validate_binding(binding, f"gate_bindings.{gate}", composite_base))
        if isinstance(binding, dict) and binding.get("stale_envelope_rejected") is not True:
            problems.append(issue("STALE_ENVELOPE_ACCEPTED", "stale envelope rejection must be observed", f"gate_bindings.{gate}.stale_envelope_rejected"))

    p5 = record.get("p5") or {}
    history_ids = {str(item) for item in _as_list(p5.get("observed_history_event_ids"))}
    if not history_ids:
        problems.append(issue("P5_HISTORY_MISSING", "P5 evaluation must reference observed history", "p5.observed_history_event_ids"))
    metric_ids = set()
    for index, metric in enumerate(_as_list(p5.get("metrics"))):
        if isinstance(metric, dict) and metric.get("metric_id"):
            metric_ids.add(str(metric["metric_id"]))
        problems.extend(_validate_metric(metric, index, history_ids))
    missing_metrics = sorted(REQUIRED_METRICS - metric_ids)
    if missing_metrics:
        problems.append(issue("P5_METRIC_MISSING", "required P5 metrics are missing: " + ", ".join(missing_metrics), "p5.metrics"))
    if p5.get("shadow_side_effect_free") is not True:
        problems.append(issue("SHADOW_SIDE_EFFECT", "shadow evaluation must be side-effect free", "p5.shadow_side_effect_free"))
    canary = p5.get("canary") or {}
    if canary.get("allowed") is True and not all(canary.get(field) is True for field in ("allowlisted", "bounded", "eligible")):
        problems.append(issue("CANARY_POLICY_VIOLATION", "allowed canary must be allowlisted, bounded and eligible", "p5.canary"))

    promotion = record.get("promotion") or {}
    if promotion.get("human_approval_required") is not True or promotion.get("automatic_promotion") is not False:
        problems.append(issue("PROMOTION_POLICY_VIOLATION", "promotion requires human approval and forbids automatic promotion", "promotion"))
    if not _nonempty(promotion.get("rollback_plan")):
        problems.append(issue("PROMOTION_POLICY_VIOLATION", "rollback plan is required", "promotion.rollback_plan"))

    for index, projection in enumerate(_as_list(record.get("projections"))):
        if not isinstance(projection, dict) or projection.get("authority") != "projection" or projection.get("grants_gate_authority") is not False:
            problems.append(issue("PROJECTION_AUTHORITY_LEAKAGE", "projection records cannot grant gate authority", f"projections[{index}]"))

    feed = record.get("feeds") or {}
    if feed.get("scrum_146", {}).get("task_id") != "SCRUM-146" or not _nonempty(feed.get("scrum_146", {}).get("evidence_ref")):
        problems.append(issue("SCRUM_146_FEED_MISSING", "result must provide a SCRUM-146 evidence reference", "feeds.scrum_146"))
    return problems


def _set_path(record: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: Any = record
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    leaf = parts[-1]
    if isinstance(current, list):
        current[int(leaf)] = value
    else:
        current[leaf] = value


def _load_fixture(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if fixture.get("fixture_type") != "mutation":
        return fixture
    base = json.loads((path.parent / fixture["base"]).read_text(encoding="utf-8"))
    record = copy.deepcopy(base)
    for mutation in fixture.get("mutations", []):
        _set_path(record, mutation["path"], mutation["value"])
    return record


def run_suite(root: Path) -> dict[str, Any]:
    fixture_root = root / "examples/integrations/cross-phase"
    expected = {
        "rejected-stale-dependency.json": "STALE_DEPENDENCY_EVIDENCE",
        "rejected-replay-divergence.json": "REPLAY_DIVERGENCE",
        "rejected-metric-fabrication.json": "METRIC_VALUE_FABRICATED",
        "rejected-projection-authority.json": "PROJECTION_AUTHORITY_LEAKAGE",
        "rejected-automatic-promotion.json": "PROMOTION_POLICY_VIOLATION",
        "rejected-gate-head-drift.json": "CI_SHA_MISMATCH",
    }
    cases: list[dict[str, Any]] = []
    problems: list[dict[str, str]] = []
    for path in sorted(fixture_root.glob("*.json")):
        issues = validate_record(_load_fixture(path))
        codes = {item["code"] for item in issues}
        expected_code = expected.get(path.name)
        passed = (expected_code in codes) if expected_code else not issues
        cases.append({"file": str(path.relative_to(root)), "expected_failure": expected_code, "codes": sorted(codes), "passed": passed})
        if not passed:
            problems.append(issue("VALIDATION_FAILED", f"fixture expectation failed: {path.name}", str(path)))
    return {"outcome": "PASS" if cases and not problems else "FAIL", "valid": bool(cases and not problems), "cases": cases, "issues": problems}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--suite", action="store_true")
    args = parser.parse_args()
    if args.suite:
        result = run_suite(Path(args.root))
    else:
        if not args.path:
            raise SystemExit("validate_scrum_150_cross_phase requires a JSON path or --suite")
        issues = validate_record(_load_fixture(Path(args.path)))
        result = {"outcome": "PASS" if not issues else "FAIL", "valid": not issues, "issues": issues}
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["outcome"])
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
