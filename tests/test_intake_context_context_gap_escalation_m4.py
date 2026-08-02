import copy
import importlib.util
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "node_architect" / "context_gap_escalation.py"
SCHEMA_PATH = REPO_ROOT / "schemas" / "context-gap-decision.schema.json"
TASK = "SCRUM-183"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "65c93c5927013c750631933495c5ecb5e22fae88"
OTHER_BASE = "0" * 40


def load_module():
    spec = importlib.util.spec_from_file_location("context_gap_escalation", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = load_module()


def card_digest(card):
    return mod.digest_payload({k: v for k, v in card.items() if k not in {"created_at", "snapshot_hash"}})


def valid_card(**overrides):
    card = {
        "schema_version": "1.0",
        "artifact_type": "intake-card",
        "contract_revision": "intake-context/v1",
        "task_id": TASK,
        "repository": REPO,
        "base_sha": BASE,
        "request": {
            "intent": "implement context gap escalation",
            "outcome": "context_gap_decision",
            "constraints": ["pure evaluator", "read only"],
            "exclusions": ["merge", "deploy"],
        },
        "source_bindings": [
            {
                "source": "intake_context.intake-card-render",
                "binding": "SCRUM-182",
                "revision": BASE,
                "status": "VERIFIED",
                "mode": "REPO",
            }
        ],
        "repository_context": {
            "repository": REPO,
            "protected_branch": "main",
            "protected_base_sha": BASE,
        },
        "risk_projection": {
            "outcome": "READY",
            "risk_level": "R2",
            "risk_flags": ["workflow_change"],
            "required_gate": "G2_EXECUTION",
            "additional_authority_gates": [],
            "risk_profile_digest": "a" * 64,
        },
        "read_scope_projection": {
            "outcome": "READY",
            "failure_classification": "NONE",
            "files_read": ["schemas/intake-card.schema.json"],
            "files_exclude": [],
            "files_missing": [],
            "read_scope_hash": "b" * 64,
        },
        "write_scope_projection": {
            "outcome": "READY",
            "candidate_paths": ["tools/node_architect/context_gap_escalation.py"],
            "exclusions": [],
            "prohibited_operations": ["MERGE"],
            "branch_binding_status": "REQUIRED_AT_G2",
            "required_authority_gates": ["G2_EXECUTION"],
            "write_scope_hash": "c" * 64,
        },
        "upstream_artifacts": [
            {"artifact_type": "intake-card", "schema_version": "1.0", "digest": "sha256:" + "d" * 64},
            {"artifact_type": "bounded-read-scope", "schema_version": "1.0", "digest": "sha256:" + "e" * 64},
        ],
        "context_status": "READY",
        "outcome": "READY",
        "next_required_action": "CONTINUE_CONTEXT_EVALUATION",
        "scope_hash": "sha256:" + "f" * 64,
        "snapshot_hash": "pending",
        "redaction_status": "NONE",
        "redactions": [],
        "reason_code": "CARD_RENDERED",
        "reason_codes": ["CARD_RENDERED"],
        "created_at": "2026-08-02T16:01:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "commit_authority_granted": False,
        "push_authority_granted": False,
        "pr_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    for key, value in overrides.items():
        card[key] = value
    card["snapshot_hash"] = card_digest(card)
    return card


def decide(card=None, **kwargs):
    payload = dict(
        task_id=TASK,
        repository=REPO,
        base_sha=BASE,
        intake_card=valid_card() if card is None else card,
        current_base_sha=BASE,
        available_evidence_keys=mod.collect_required_evidence(valid_card() if card is None else card),
        confirmed_missing_evidence_keys=[],
        connector_status="CONFIRMED",
        repository_readback_status="CONFIRMED",
        ci_required=True,
        ci_status="SUCCESS",
        validator_status="PASS",
        observed_at="2026-08-02T16:01:00Z",
    )
    payload.update(kwargs)
    return mod.decide_context_gap_escalation(**payload)


class ContextGapEscalationM4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(cls.schema)

    def assert_schema_valid(self, decision):
        errors = sorted(self.validator.iter_errors(decision), key=lambda error: list(error.path))
        self.assertEqual([], [error.message for error in errors])

    def assert_blocked(self, decision, classification, route, reason):
        self.assert_schema_valid(decision)
        self.assertEqual("BLOCKED", decision["outcome"])
        self.assertTrue(decision["preparation_block"]["blocked"])
        self.assertEqual(classification, decision["preparation_block"]["classification"])
        self.assertEqual(route, decision["preparation_block"]["route"])
        self.assertIn(reason, decision["reason_codes"])

    def test_no_gap_routes_to_family_verification(self):
        decision = decide()
        self.assert_schema_valid(decision)
        self.assertEqual("READY", decision["outcome"])
        self.assertEqual("READY_FOR_FAMILY_VERIFICATION", decision["preparation_block"]["route"])
        self.assertEqual("NONE", decision["preparation_block"]["classification"])
        self.assertEqual("CONTEXT_READY", decision["reason_code"])
        self.assertFalse(decision["write_authority_granted"])

    def test_malformed_card_blocks_g1_review(self):
        card = valid_card(artifact_type="wrong")
        card["snapshot_hash"] = card_digest(card)
        decision = decide(card=card)
        self.assert_blocked(decision, "AGENT_PREPARATION_BLOCKED", "BLOCK_G1_REVIEW", "CONTEXT_CARD_INVALID")

    def test_card_hash_mismatch_blocks_g1_review(self):
        card = valid_card()
        card["snapshot_hash"] = "sha256:" + "0" * 64
        decision = decide(card=card)
        self.assert_blocked(decision, "AGENT_PREPARATION_BLOCKED", "BLOCK_G1_REVIEW", "CONTEXT_CARD_INVALID")

    def test_stale_protected_base_recaptures_base(self):
        decision = decide(current_base_sha=OTHER_BASE)
        self.assert_blocked(decision, "AGENT_PREPARATION_BLOCKED", "RECAPTURE_PROTECTED_BASE", "CONTEXT_BASE_STALE")
        self.assertEqual("PROTECTED_BASE_REF", decision["remediation_readset"]["required_reads"][0]["source_type"])

    def test_source_conflict_requests_human_input(self):
        card = valid_card()
        card["source_bindings"][0]["status"] = "CONFLICT"
        card["snapshot_hash"] = card_digest(card)
        decision = decide(card=card)
        self.assert_blocked(decision, "HUMAN_INPUT_REQUIRED", "REQUEST_HUMAN_INPUT", "CONTEXT_SOURCE_CONFLICT")
        self.assertEqual([], decision["remediation_readset"]["required_reads"])

    def test_source_missing_retries_source_readback(self):
        card = valid_card()
        card["source_bindings"][0]["status"] = "MISSING"
        card["snapshot_hash"] = card_digest(card)
        decision = decide(card=card)
        self.assert_blocked(decision, "AGENT_PREPARATION_BLOCKED", "RETRY_SOURCE_READBACK", "CONTEXT_SOURCE_UNRESOLVED")
        self.assertTrue(decision["remediation_readset"]["required_reads"])

    def test_connector_error_is_agent_preparation_not_repository_failure(self):
        card = valid_card()
        card["read_scope_projection"]["files_missing"] = ["core/missing.md"]
        card["outcome"] = "BLOCKED"
        card["context_status"] = "BLOCKED"
        card["reason_code"] = "CARD_UPSTREAM_BLOCKED"
        card["reason_codes"] = ["CARD_UPSTREAM_BLOCKED"]
        card["snapshot_hash"] = card_digest(card)
        decision = decide(
            card=card,
            available_evidence_keys=[key for key in mod.collect_required_evidence(card) if key != "path:core/missing.md"],
            connector_status="ERROR",
        )
        self.assert_blocked(decision, "AGENT_PREPARATION_BLOCKED", "RETRY_SOURCE_READBACK", "CONTEXT_AGENT_PREPARATION_BLOCKED")

    def test_confirmed_repository_omission_is_repository_evidence_missing(self):
        card = valid_card()
        card["read_scope_projection"]["files_missing"] = ["core/missing.md"]
        card["outcome"] = "BLOCKED"
        card["context_status"] = "BLOCKED"
        card["reason_code"] = "CARD_UPSTREAM_BLOCKED"
        card["reason_codes"] = ["CARD_UPSTREAM_BLOCKED"]
        card["snapshot_hash"] = card_digest(card)
        decision = decide(
            card=card,
            available_evidence_keys=[key for key in mod.collect_required_evidence(card) if key != "path:core/missing.md"],
            confirmed_missing_evidence_keys=["path:core/missing.md"],
            repository_readback_status="CONFIRMED",
        )
        self.assert_blocked(decision, "REPOSITORY_EVIDENCE_MISSING", "READ_REQUIRED_EVIDENCE", "CONTEXT_REPOSITORY_EVIDENCE_MISSING")
        self.assertEqual("REPOSITORY_FILE", decision["remediation_readset"]["required_reads"][0]["source_type"])

    def test_connector_empty_without_exact_readback_is_not_repository_failure(self):
        card = valid_card()
        card["read_scope_projection"]["files_missing"] = ["core/missing.md"]
        card["outcome"] = "BLOCKED"
        card["context_status"] = "BLOCKED"
        card["reason_code"] = "CARD_UPSTREAM_BLOCKED"
        card["reason_codes"] = ["CARD_UPSTREAM_BLOCKED"]
        card["snapshot_hash"] = card_digest(card)
        decision = decide(
            card=card,
            available_evidence_keys=[key for key in mod.collect_required_evidence(card) if key != "path:core/missing.md"],
            connector_status="EMPTY",
            repository_readback_status="NOT_ATTEMPTED",
        )
        self.assert_blocked(decision, "AGENT_PREPARATION_BLOCKED", "READ_REQUIRED_EVIDENCE", "CONTEXT_EVIDENCE_MISSING")
        self.assertNotEqual("REPOSITORY_EVIDENCE_MISSING", decision["preparation_block"]["classification"])

    def test_ci_pending_is_observability_gap_not_validation_failure(self):
        decision = decide(ci_status="PENDING")
        self.assert_blocked(decision, "CI_UNAVAILABLE_AT_CHECK", "RETRY_CI_OBSERVABILITY", "CONTEXT_CI_UNAVAILABLE")
        self.assertEqual("CI_RUN_LOOKUP", decision["remediation_readset"]["required_reads"][0]["source_type"])

    def test_validator_failure_before_complete_evidence_is_preparation_blocked(self):
        card = valid_card()
        card["read_scope_projection"]["files_missing"] = ["core/missing.md"]
        card["outcome"] = "BLOCKED"
        card["context_status"] = "BLOCKED"
        card["reason_code"] = "CARD_UPSTREAM_BLOCKED"
        card["reason_codes"] = ["CARD_UPSTREAM_BLOCKED"]
        card["snapshot_hash"] = card_digest(card)
        decision = decide(
            card=card,
            available_evidence_keys=[key for key in mod.collect_required_evidence(card) if key != "path:core/missing.md"],
            validator_status="FAILED",
        )
        self.assert_blocked(decision, "AGENT_PREPARATION_BLOCKED", "READ_REQUIRED_EVIDENCE", "CONTEXT_EVIDENCE_MISSING")

    def test_validator_failure_after_complete_evidence_is_validation_failure(self):
        decision = decide(validator_status="FAILED")
        self.assert_blocked(decision, "VALIDATION_FAILED", "FIX_VALIDATION_FAILURE", "CONTEXT_VALIDATION_FAILED")

    def test_scope_digest_drift_retries_source_readback(self):
        card = valid_card(reason_codes=["CARD_SCOPE_HASH_MISMATCH"], reason_code="CARD_SCOPE_HASH_MISMATCH")
        decision = decide(card=card)
        self.assert_blocked(decision, "AGENT_PREPARATION_BLOCKED", "RETRY_SOURCE_READBACK", "CONTEXT_SCOPE_DRIFT")

    def test_unknown_remediation_key_blocks_input_without_path_invention(self):
        decision = decide(confirmed_missing_evidence_keys=["path:not-in-card.md"])
        self.assert_blocked(decision, "AGENT_PREPARATION_BLOCKED", "BLOCK_G1_REVIEW", "CONTEXT_INPUT_INVALID")
        self.assertEqual([], decision["remediation_readset"]["required_reads"])

    def test_input_order_and_timestamp_do_not_change_hashes(self):
        card = valid_card()
        keys = list(reversed(mod.collect_required_evidence(card)))
        first = decide(card=card, available_evidence_keys=keys, observed_at="2026-08-02T16:01:00Z")
        second = decide(card=card, available_evidence_keys=sorted(keys), observed_at="2026-08-02T17:59:00Z")
        self.assertEqual(first["decision_digest"], second["decision_digest"])
        self.assertEqual(first["remediation_readset"]["readset_hash"], second["remediation_readset"]["readset_hash"])

    def test_all_authority_fields_are_false(self):
        decision = decide()
        for field in (
            "write_authority_granted",
            "commit_authority_granted",
            "push_authority_granted",
            "pr_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(decision[field], field)


if __name__ == "__main__":
    unittest.main()
