#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_METRICS = {
    "planning-completeness",
    "runtime-history-completeness",
    "outcome-comparison-accuracy",
    "catalog-quality",
    "route-selection-accuracy",
    "confidence-calibration",
    "human-override-rate",
    "evidence-completeness",
    "policy-violation-rate",
    "recovery-success-rate",
}

PROMOTION_LIFECYCLE = [
    "experimental",
    "candidate",
    "pilot",
    "stable",
    "deprecated",
    "retired",
]


def issue(code: str, message: str, location: str = "<root>") -> dict[str, str]:
    return {"code": code, "message": message, "location": location}


def _as_set(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values}


def validate_record(record: dict[str, Any]) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []

    if record.get("schema_version") != "0.1":
        problems.append(issue("SCHEMA_VERSION_MISMATCH", "schema_version must be 0.1", "schema_version"))
    if record.get("task_id") != "SCRUM-122":
        problems.append(issue("TASK_MISMATCH", "task_id must be SCRUM-122", "task_id"))
    if record.get("chain_id") != "SCRUM-122-126":
        problems.append(issue("CHAIN_MISMATCH", "chain_id must be SCRUM-122-126", "chain_id"))

    linked = record.get("linked_task_ids") or []
    linked_ids = [str(value) for value in linked] if isinstance(linked, list) else []
    expected_chain = ["SCRUM-122", "SCRUM-123", "SCRUM-124", "SCRUM-125", "SCRUM-126"]
    if linked_ids != expected_chain:
        problems.append(
            issue(
                "CHAIN_TASK_IDS_MISMATCH",
                "linked_task_ids must preserve the SCRUM-122 through SCRUM-126 order",
                "linked_task_ids",
            )
        )

    history = record.get("history") or {}
    run = history.get("run") or {}
    if not run.get("run_id"):
        problems.append(issue("HISTORY_RUN_MISSING", "history.run.run_id is required", "history.run.run_id"))
    if run.get("run_id") and record.get("run_id") and str(run.get("run_id")) != str(record.get("run_id")):
        problems.append(issue("RUN_ID_MISMATCH", "history.run.run_id must match run_id", "history.run.run_id"))

    metrics = record.get("metrics") or []
    metric_ids = {str(item.get("metric_id")) for item in metrics if isinstance(item, dict) and item.get("metric_id")}
    missing_metrics = sorted(REQUIRED_METRICS - metric_ids)
    if missing_metrics:
        problems.append(
            issue(
                "METRIC_MISSING",
                "required P5 metrics are missing: " + ", ".join(missing_metrics),
                "metrics",
            )
        )

    shadow = record.get("shadow") or {}
    if shadow.get("side_effect_free") is not True:
        problems.append(issue("SHADOW_SIDE_EFFECT", "shadow execution must stay side-effect free", "shadow.side_effect_free"))
    if shadow.get("candidate_allowed") is False and shadow.get("stable_fallback") is not True:
        problems.append(
            issue(
                "CONFIDENCE_CALIBRATION_DRIFT",
                "low-confidence candidate planning must retain stable fallback",
                "shadow.stable_fallback",
            )
        )
    confidence = shadow.get("confidence")
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        problems.append(issue("CONFIDENCE_CALIBRATION_DRIFT", "confidence must be a number between 0 and 1", "shadow.confidence"))

    canary = shadow.get("canary") or {}
    canary_allowed = canary.get("allowed")
    if canary_allowed is True and not (canary.get("allowlisted") and canary.get("bounded") and canary.get("eligible")):
        problems.append(
            issue(
                "CANARY_POLICY_VIOLATION",
                "allowed canaries must also be allowlisted, bounded and eligible",
                "shadow.canary",
            )
        )

    comparison = record.get("comparison") or {}
    replay = comparison.get("replay") or {}
    route_matches = replay.get("route_matches")
    decision_matches = replay.get("decision_matches")
    if route_matches is not True or decision_matches is not True:
        if replay.get("typed_divergence") in (None, {}):
            problems.append(
                issue(
                    "REPLAY_DIVERGENCE",
                    "replay mismatch needs a typed live-state divergence",
                    "comparison.replay",
                )
            )

    promotion = record.get("promotion") or {}
    lifecycle = promotion.get("lifecycle") or []
    lifecycle_ids = [str(value) for value in lifecycle] if isinstance(lifecycle, list) else []
    if lifecycle_ids != PROMOTION_LIFECYCLE:
        problems.append(
            issue(
                "PROMOTION_POLICY_VIOLATION",
                "promotion lifecycle must preserve the experimental -> retired order",
                "promotion.lifecycle",
            )
        )
    if promotion.get("current_stage") not in PROMOTION_LIFECYCLE:
        problems.append(issue("PROMOTION_POLICY_VIOLATION", "current_stage must be a known lifecycle stage", "promotion.current_stage"))
    if promotion.get("human_approval_required") is not True:
        problems.append(issue("PROMOTION_POLICY_VIOLATION", "human approval is required for promotion", "promotion.human_approval_required"))
    if promotion.get("automatic_promotion") is not False:
        problems.append(issue("PROMOTION_POLICY_VIOLATION", "automatic promotion is not allowed", "promotion.automatic_promotion"))
    if not str(promotion.get("rollback_plan") or "").strip():
        problems.append(issue("PROMOTION_POLICY_VIOLATION", "rollback_plan is required", "promotion.rollback_plan"))

    for index, projection in enumerate(record.get("projections") or []):
        if projection.get("authority") != "projection" or projection.get("grants_gate_authority") is not False:
            problems.append(
                issue(
                    "PROJECTION_AUTHORITY_LEAKAGE",
                    "projection layers cannot grant gate authority",
                    f"projections[{index}]",
                )
            )

    return problems


def run_suite() -> dict[str, Any]:
    valid_record = {
        "schema_version": "0.1",
        "task_id": "SCRUM-122",
        "chain_id": "SCRUM-122-126",
        "linked_task_ids": ["SCRUM-122", "SCRUM-123", "SCRUM-124", "SCRUM-125", "SCRUM-126"],
        "repository": "nhatnguyenquang1838-coder/gwc",
        "base_sha": "cd9b49cf9e6fd97413bc49ed480b2fc9941513af",
        "scope_hash": "sha256:" + "9" * 64,
        "run_id": "p5-eval-122-126-20260727",
        "history": {"run": {"run_id": "p5-eval-122-126-20260727", "status": "completed"}, "events": [], "checkpoints": []},
        "metrics": [
            {"metric_id": metric_id, "label": metric_id.replace("-", " ").title(), "value": 1.0, "target": 1.0, "direction": "higher_is_better", "status": "pass"}
            for metric_id in sorted(REQUIRED_METRICS)
        ],
        "shadow": {
            "candidate_allowed": True,
            "confidence": 0.92,
            "stable_fallback": True,
            "side_effect_free": True,
            "canary": {"allowed": True, "allowlisted": True, "bounded": True, "eligible": True},
        },
        "comparison": {
            "stable": {"graph_revision": "stable-r1", "route_signature": "stable-route", "decision_signature": "stable-decision"},
            "candidate": {"graph_revision": "candidate-r1", "route_signature": "candidate-route", "decision_signature": "candidate-decision"},
            "replay": {"route_matches": True, "decision_matches": True},
        },
        "promotion": {
            "lifecycle": PROMOTION_LIFECYCLE,
            "current_stage": "pilot",
            "human_approval_required": True,
            "automatic_promotion": False,
            "rollback_plan": "revert to stable planner and prior graph revision",
        },
        "projections": [{"system": "jira", "authority": "projection", "grants_gate_authority": False}],
    }
    cases = [
        {"name": "accepted-evaluation", "record": valid_record, "expected": set()},
        {
            "name": "rejected-promotion",
            "record": dict(valid_record, promotion=dict(valid_record["promotion"], automatic_promotion=True)),
            "expected": {"PROMOTION_POLICY_VIOLATION"},
        },
        {
            "name": "rejected-projection-authority",
            "record": dict(valid_record, projections=[{"system": "jira", "authority": "projection", "grants_gate_authority": True}]),
            "expected": {"PROJECTION_AUTHORITY_LEAKAGE"},
        },
    ]
    results = []
    problems = []
    for case in cases:
        issues = validate_record(case["record"])
        codes = {item["code"] for item in issues}
        passed = codes == case["expected"]
        results.append({"name": case["name"], "codes": sorted(codes), "passed": passed})
        if not passed:
            problems.append(issue("VALIDATION_FAILED", f"{case['name']} expectation failed", case["name"]))
    return {"valid": not problems, "cases": results, "issues": problems}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--suite", action="store_true")
    args = parser.parse_args()

    if args.suite:
        result = run_suite()
    else:
        if not args.path:
            raise SystemExit("validate_p5_evaluation requires a JSON path or --suite")
        record = json.loads(Path(args.path).read_text(encoding="utf-8"))
        issues = validate_record(record)
        result = {"valid": not issues, "issues": issues}

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("PASS" if result["valid"] else "FAIL")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

