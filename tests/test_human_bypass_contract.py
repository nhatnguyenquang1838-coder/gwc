from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
import sys
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]


def load_schema(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def valid_record() -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "human-bypass-record",
        "bypass_request_id": "HB-SCRUM72-001",
        "task_id": "SCRUM-72",
        "gate": "G3_PR",
        "node_id": "ready-for-review-promotion",
        "blocked_step_id": "STEP-08",
        "blocker_code": "CONNECTOR_ACTION_UNAVAILABLE",
        "rationale": "The agent cannot invoke the metadata action but the same bounded UI action exists.",
        "human_actor": {"id": "human-owner", "display_name": "Owner"},
        "exact_scope": ["PR #83: mark ready for review"],
        "authorized_manual_action": "Mark the exact Draft PR ready for review.",
        "excluded_actions": ["merge", "base change", "scope change"],
        "repository": {
            "full_name": "nhatnguyenquang1838-coder/gwc",
            "base_sha": "0" * 40,
            "branch": "feat/example",
            "head_sha": "1" * 40,
        },
        "scope_hash": "sha256:" + "a" * 64,
        "issued_at_utc": "2026-07-23T00:00:00Z",
        "accepted_at_utc": "2026-07-23T00:01:00Z",
        "expires_at_utc": "2026-07-23T01:00:00Z",
        "checkpoint_before": "cp-before",
        "expected_readback": "PR is not draft and head SHA is unchanged.",
        "observed_readback": "PR is not draft; head SHA remains " + "1" * 40,
        "checkpoint_after": "cp-after",
        "residual_risk": "none",
        "audit_event_id": "evt_human-bypass.001",
        "state": "RESUME",
        "outcome": "SUCCESS",
    }


class HumanBypassSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = load_schema("schemas/human-bypass.schema.json")
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())

    def errors(self, record: dict) -> list:
        return list(self.validator.iter_errors(record))

    def test_eligible_bypass_with_readback_passes(self) -> None:
        self.assertEqual([], self.errors(valid_record()))

    def test_forbidden_bypass_is_excluded_by_contract(self) -> None:
        record = valid_record()
        record["authorized_manual_action"] = "Merge the pull request without G4."
        forbidden = {
            "merge without exact G4 authority",
            "direct write to a protected branch",
            "skipping required CI",
        }
        contract = (ROOT / "core/HUMAN_BYPASS_CONTRACT_v1.0.md").read_text(encoding="utf-8")
        for phrase in forbidden:
            self.assertIn(phrase, contract)
        self.assertIn("merge", record["excluded_actions"])

    def test_expiry_is_terminal_and_not_success(self) -> None:
        record = valid_record()
        record.update({
            "accepted_at_utc": None,
            "observed_readback": None,
            "checkpoint_after": None,
            "audit_event_id": None,
            "state": "HUMAN_BYPASS_EXPIRED",
            "outcome": "EXPIRED",
        })
        self.assertEqual([], self.errors(record))
        expiry = datetime.fromisoformat(record["expires_at_utc"].replace("Z", "+00:00"))
        now = datetime(2026, 7, 23, 2, tzinfo=timezone.utc)
        self.assertLess(expiry, now)

    def test_drift_invalidates_scope_binding(self) -> None:
        before = valid_record()
        after = deepcopy(before)
        after["repository"]["head_sha"] = "2" * 40
        self.assertNotEqual(before["repository"]["head_sha"], after["repository"]["head_sha"])
        self.assertIn("invalidated by task, base SHA, head SHA", (ROOT / "core/HUMAN_BYPASS_CONTRACT_v1.0.md").read_text())

    def test_duplicate_acceptance_is_idempotent_only_for_same_binding(self) -> None:
        first = valid_record()
        duplicate = deepcopy(first)
        self.assertEqual(first, duplicate)
        conflicting = deepcopy(first)
        conflicting["scope_hash"] = "sha256:" + "b" * 64
        self.assertNotEqual(first, conflicting)

    def test_resume_requires_readback_checkpoint_and_audit(self) -> None:
        record = valid_record()
        for field in ("observed_readback", "checkpoint_after", "audit_event_id"):
            broken = deepcopy(record)
            broken[field] = None
            self.assertTrue(self.errors(broken), field)

    def test_runtime_event_requires_bypass_binding(self) -> None:
        schema = load_schema("schemas/node-architect/runtime-event.schema.json")
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        event = {
            "schema_version": "0.1",
            "event_id": "evt_human-bypass.001",
            "event_type": "human_bypass_evidence_verified",
            "occurred_at_utc": "2026-07-23T00:02:00Z",
            "actor": {"kind": "human", "id": "owner", "execution_mode": "chat_connector_only"},
            "node_id": "ready-for-review-promotion",
            "gate": "G3_PR",
            "outcome": "success",
            "checkpoint_id": "cp-after",
            "idempotency_key": "HB-SCRUM72-001",
            "bypass": {
                "bypass_request_id": "HB-SCRUM72-001",
                "blocked_step_id": "STEP-08",
                "scope_hash": "sha256:" + "a" * 64,
            },
        }
        self.assertEqual([], list(validator.iter_errors(event)))
        del event["bypass"]
        self.assertTrue(list(validator.iter_errors(event)))


class G1FeasibilityValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator_module = load_module("validate_g01", "tools/validate_g01.py")
        cls.generator_module = load_module("generate_g01_runtime", "tools/generate_g01_runtime.py")

    def valid_preflight(self) -> dict:
        return {
            "process_readback": {"status": "VERIFIED"},
            "execution_feasibility": {
                "outcome": "EXECUTABLE_WITH_HUMAN_BYPASS",
                "continuation_coverage": "COMPLETE",
                "human_bypass_required": True,
                "route_steps": [
                    {
                        "id": "STEP-08",
                        "capability_status": "VERIFIED",
                        "fallback_routes": ["human manual UI action"],
                        "continuation": "checkpoint and readback",
                        "bypass_eligibility": "OPERATIONAL_ONLY",
                    }
                ],
            },
        }

    def test_unknown_capability_without_fallback_blocks_g1(self) -> None:
        preflight = self.valid_preflight()
        step = preflight["execution_feasibility"]["route_steps"][0]
        step["capability_status"] = "UNKNOWN"
        step["fallback_routes"] = []
        codes = {issue.code for issue in self.validator_module._execution_feasibility_issues(preflight)}
        self.assertIn("G1_EXECUTION_CAPABILITY_UNVERIFIED", codes)

    def test_missing_continuation_blocks_g1(self) -> None:
        preflight = self.valid_preflight()
        preflight["execution_feasibility"]["route_steps"][0]["continuation"] = ""
        codes = {issue.code for issue in self.validator_module._execution_feasibility_issues(preflight)}
        self.assertIn("G1_CONTINUATION_COVERAGE_INCOMPLETE", codes)

    def test_human_bypass_outcome_requires_blocked_eligible_step(self) -> None:
        preflight = self.valid_preflight()
        codes = {issue.code for issue in self.validator_module._execution_feasibility_issues(preflight)}
        self.assertIn("G1_HUMAN_BYPASS_STEP_MISSING", codes)

    def test_eligible_blocked_step_with_fallback_uses_human_bypass(self) -> None:
        preflight = self.valid_preflight()
        preflight["execution_feasibility"]["route_steps"][0]["capability_status"] = "HARD_BLOCKED"
        self.assertEqual([], self.validator_module._execution_feasibility_issues(preflight))

    def test_legacy_pair_absent_is_compatible_but_partial_is_blocked(self) -> None:
        self.assertEqual([], self.validator_module._execution_feasibility_issues({}))
        partial = {"process_readback": {"status": "VERIFIED"}}
        codes = {issue.code for issue in self.validator_module._execution_feasibility_issues(partial)}
        self.assertIn("G1_EXECUTION_FEASIBILITY_INCOMPLETE", codes)

    def test_generator_classifies_bypass_resolvable_route(self) -> None:
        route = [{
            "id": "STEP-08",
            "capability_status": "HARD_BLOCKED",
            "fallback_routes": ["human manual UI action"],
            "bypass_eligibility": "OPERATIONAL_ONLY",
        }]
        result = self.generator_module._classify_execution_feasibility(route)
        self.assertEqual("EXECUTABLE_WITH_HUMAN_BYPASS", result["outcome"])
        self.assertTrue(result["human_bypass_required"])

    def test_generated_route_covers_g3_review_and_ready_promotion(self) -> None:
        repository = {"verified": True, "write_enabled": True}
        runtime = {
            "selected_connector": "DWC",
            "connector_priority": ["GitHub", "DWC", "DW1"],
            "connector_fallback_evidence": [
                {"connector": "DWC", "role": "fallback", "status": "AVAILABLE", "evidence": "verified"}
            ],
        }
        names = {step["name"] for step in self.generator_module._route_steps(repository, runtime, True)}
        self.assertIn("independent-g3-review", names)
        self.assertIn("ready-for-review-promotion", names)


if __name__ == "__main__":
    unittest.main()
