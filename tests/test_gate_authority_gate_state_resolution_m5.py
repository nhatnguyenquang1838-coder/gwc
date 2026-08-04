"""SCRUM-184 M5 tests for deterministic, replay-safe gate-state resolution."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from tools.node_architect.gate_state_resolution import GATE_ORDER, resolve_gate_state

BASE = "9a7fd18af8f1b9dac4f5bc2774f4e0f602216624"
SCOPE = "sha256:" + "a" * 64
REPO = "nhatnguyenquang1838-coder/gwc"


def transition_map():
    return {
        "contract_version": "1.0.1",
        "rules": [
            {"outcome": "G0_READY", "from_state": "draft", "transition": "SUBMIT", "expected_state": "ready"},
            {"outcome": "WRITE_APPROVED", "from_state": "pending_approval", "transition": "APPROVE_WRITE", "expected_state": "write_running"},
        ],
        "terminal_states": ["completed", "cancelled"],
    }


def scope_identity(**overrides):
    value = {
        "artifact_type": "gate-scope-identity",
        "task_id": "SCRUM-184",
        "repository": REPO,
        "base_sha": BASE,
        "head_sha": None,
        "scope_hash": SCOPE,
        "authorized_actions": ["modify_approved_files"],
        "outcome": "READY",
        "authority_granted": False,
    }
    value.update(overrides)
    return value


def _entry(gate, target, *, status="PASS", digest=None, **overrides):
    value = {
        "evidence_key": target,
        "gate": gate,
        "artifact_role": target.rsplit("/", 1)[-1],
        "classification": "CANONICAL_GATE_EVIDENCE",
        "required": True,
        "source_type": "repository_artifact",
        "target": target,
        "ref": target,
        "revision": BASE,
        "digest": digest or ("sha256:" + hashlib.sha256(f"{gate}:{target}".encode()).hexdigest()),
        "binding_status": "MATCHED",
        "freshness_status": "FRESH",
        "materialization_status": "MATERIALIZED",
        "source_of_truth": True,
        "status": status,
        "reason_codes": [],
    }
    value.update(overrides)
    return value


def complete_evidence(*, include_g6=False):
    targets = {
        "G0_CONTEXT": [".gwc/tasks/SCRUM-184/g0/context-snapshot.yaml"],
        "G1_ALIGNMENT": [
            ".gwc/tasks/SCRUM-184/g1/intake/g1-intake-brief.yaml",
            ".gwc/tasks/SCRUM-184/g1/preflight/g1-preflight-report.yaml",
            ".gwc/tasks/SCRUM-184/g1/brainstorming/g1-options.yaml",
            ".gwc/tasks/SCRUM-184/g1/decision/g1-decision-record.yaml",
        ],
        "G2_EXECUTION": [".gwc/tasks/SCRUM-184/g2/execution-envelope.yaml"],
        "G3_PR": [".gwc/tasks/SCRUM-184/g3/delivery-record.yaml"],
        "G4_MERGE": [".gwc/tasks/SCRUM-184/g4/merge-approval.yaml"],
        "G5_DEPLOY": ["actions://g5-status-verify"],
    }
    if include_g6:
        targets["G6_PRODUCTION_DATA"] = [".gwc/tasks/SCRUM-184/g6/production-approval.yaml"]
    requirements = []
    entries = []
    for gate, refs in targets.items():
        for ref in refs:
            requirements.append({"gate": gate, "target": ref, "required": True})
            entries.append(_entry(gate, ref))
    return {
        "artifact_type": "gate-evidence-artifact-map",
        "task_id": "SCRUM-184",
        "repository": REPO,
        "base_sha": BASE,
        "head_sha": None,
        "scope_hash": SCOPE,
        "outcome": "READY",
        "reason_codes": ["EVIDENCE_MAP_READY"],
        "requirements": requirements,
        "entries": entries,
        "missing_required": [],
        "stale_required": [],
        "projection_only": [],
    }


def resolve(**overrides):
    kwargs = {
        "task_id": "SCRUM-184",
        "repository": REPO,
        "current_base_sha": BASE,
        "scope_identity": scope_identity(),
        "evidence_map": complete_evidence(),
        "transition_map": transition_map(),
        "task_projection": None,
        "event_id_or_idempotency_key": "scrum-184-event-1",
        "prior_resolution": None,
        "observed_at": "2026-08-04T13:50:00Z",
    }
    kwargs.update(overrides)
    return resolve_gate_state(**kwargs)


class GateStateResolutionTests(unittest.TestCase):
    def test_complete_non_production_resolves_g6_not_applicable(self):
        out = resolve()
        self.assertEqual(out["current_gate"], "G6_PRODUCTION_DATA")
        self.assertEqual(out["gate_status"], "NOT_APPLICABLE")
        self.assertEqual(out["last_passed_gate"], "G5_DEPLOY")
        self.assertIsNone(out["next_gate"])
        self.assertIn("GATE_STATE_RESOLVED", out["reason_codes"])
        self.assertIn("GATE_STATE_G6_NOT_APPLICABLE", out["reason_codes"])

    def test_schema_valid(self):
        schema = json.loads((Path(__file__).parents[1] / "schemas/gate-state-resolution.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        errors = list(Draft202012Validator(schema).iter_errors(resolve()))
        self.assertEqual(errors, [])

    def test_all_authority_flags_false(self):
        out = resolve()
        for flag in (
            "authority_granted", "write_authority_granted", "pr_authority_granted",
            "merge_authority_granted", "deployment_authority_granted", "production_authority_granted",
        ):
            self.assertIs(out[flag], False)

    def test_missing_g0_blocks_earliest_gate(self):
        evidence = complete_evidence()
        target = ".gwc/tasks/SCRUM-184/g0/context-snapshot.yaml"
        evidence["entries"] = [e for e in evidence["entries"] if e["target"] != target]
        evidence["missing_required"] = [target]
        out = resolve(evidence_map=evidence)
        self.assertEqual(out["current_gate"], "G0_CONTEXT")
        self.assertEqual(out["gate_status"], "BLOCKED")
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_REQUIRED_EVIDENCE_MISSING")
        self.assertIn("GATE_STATE_LATER_GATE_INHERITANCE_REJECTED", out["reason_codes"])

    def test_missing_g2_blocks_after_g1(self):
        evidence = complete_evidence()
        target = ".gwc/tasks/SCRUM-184/g2/execution-envelope.yaml"
        evidence["entries"] = [e for e in evidence["entries"] if e["target"] != target]
        evidence["missing_required"] = [target]
        out = resolve(evidence_map=evidence)
        self.assertEqual(out["last_passed_gate"], "G1_ALIGNMENT")
        self.assertEqual(out["current_gate"], "G2_EXECUTION")

    def test_stale_evidence_precedes_missing(self):
        evidence = complete_evidence()
        target = ".gwc/tasks/SCRUM-184/g2/execution-envelope.yaml"
        for entry in evidence["entries"]:
            if entry["target"] == target:
                entry["freshness_status"] = "STALE"
                entry["reason_codes"] = ["EVIDENCE_STALE"]
        evidence["stale_required"] = [target]
        out = resolve(evidence_map=evidence)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_EVIDENCE_STALE")
        self.assertIn(target, out["stale_evidence"])

    def test_conflicting_evidence_precedes_drift(self):
        evidence = complete_evidence()
        duplicate = copy.deepcopy(evidence["entries"][0])
        duplicate["digest"] = "sha256:" + "b" * 64
        evidence["entries"].append(duplicate)
        out = resolve(evidence_map=evidence, current_base_sha="1" * 40)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_EVIDENCE_CONFLICT")

    def test_binding_mismatch_precedes_evidence_conflict(self):
        evidence = complete_evidence()
        evidence["repository"] = "other/repo"
        duplicate = copy.deepcopy(evidence["entries"][0])
        duplicate["digest"] = "sha256:" + "c" * 64
        evidence["entries"].append(duplicate)
        out = resolve(evidence_map=evidence)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_BINDING_MISMATCH")

    def test_base_drift_requires_reapproval(self):
        out = resolve(current_base_sha="1" * 40)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_DRIFT")
        self.assertEqual(out["current_gate"], "G0_CONTEXT")
        self.assertIsNone(out["last_passed_gate"])
        self.assertEqual(out["drift_decision"]["status"], "REAPPROVE")
        self.assertIn("BASE_SHA_DRIFT", out["drift_decision"]["reason_codes"])

    def test_projection_mismatch_is_warning_only(self):
        out = resolve(task_projection={"task_id": "SCRUM-184", "current_gate": "G2_EXECUTION", "status": "RUNNING"})
        self.assertEqual(out["gate_status"], "NOT_APPLICABLE")
        self.assertIn("GATE_STATE_PROJECTION_MISMATCH", out["reason_codes"])
        self.assertIn("CURRENT_GATE_MISMATCH", out["projection_warnings"])

    def test_unknown_projection_state_warns_from_transition_map(self):
        out = resolve(task_projection={"task_id": "SCRUM-184", "state": "invented_state"})
        self.assertIn("PROJECTION_STATE_UNKNOWN", out["projection_warnings"])
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_RESOLVED")

    def test_cancelled_projection_not_terminal_authority(self):
        out = resolve(task_projection={"task_id": "SCRUM-184", "state": "cancelled"})
        self.assertEqual(out["gate_status"], "NOT_APPLICABLE")
        self.assertIn("CANCELLED_PROJECTION_WITHOUT_CANONICAL_EVIDENCE", out["projection_warnings"])


    def test_projection_warning_keeps_resolved_primary_reason(self):
        out = resolve(task_projection={"current_gate": "G2_EXECUTION"})
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_RESOLVED")

    def test_running_g5_status_is_running_not_missing(self):
        evidence = complete_evidence()
        target = "actions://g5-status-verify"
        for entry in evidence["entries"]:
            if entry["target"] == target:
                entry["status"] = "RUNNING"
        out = resolve(evidence_map=evidence)
        self.assertEqual(out["current_gate"], "G5_DEPLOY")
        self.assertEqual(out["gate_status"], "RUNNING")
        self.assertEqual(out["next_action_class"], "WAIT_FOR_GATE_COMPLETION")

    def test_g5_status_evidence_needs_no_deployment_authority(self):
        out = resolve()
        g5 = next(item for item in out["gate_evaluations"] if item["gate"] == "G5_DEPLOY")
        self.assertEqual(g5["status"], "PASS")
        self.assertFalse(out["deployment_authority_granted"])

    def test_production_scope_requires_and_passes_g6(self):
        scope = scope_identity(authorized_actions=["production_data_write"])
        out = resolve(scope_identity=scope, evidence_map=complete_evidence(include_g6=True))
        self.assertEqual(out["gate_status"], "PASS")
        self.assertEqual(out["last_passed_gate"], "G6_PRODUCTION_DATA")
        self.assertNotIn("GATE_STATE_G6_NOT_APPLICABLE", out["reason_codes"])
        self.assertFalse(out["production_authority_granted"])

    def test_production_scope_missing_g6_blocks(self):
        scope = scope_identity(authorized_actions=["production_config_change"])
        out = resolve(scope_identity=scope, evidence_map=complete_evidence())
        self.assertEqual(out["current_gate"], "G6_PRODUCTION_DATA")
        self.assertEqual(out["gate_status"], "BLOCKED")

    def test_invalid_transition_map_blocks_input(self):
        out = resolve(transition_map={"rules": [], "terminal_states": []})
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_INPUT_INVALID")
        self.assertEqual(out["next_action_class"], "FIX_INPUT")

    def test_same_semantics_ignore_observed_at(self):
        a = resolve(observed_at="2026-08-04T13:50:00Z")
        b = resolve(observed_at="2026-08-05T13:50:00Z")
        self.assertEqual(a["resolution_digest"], b["resolution_digest"])

    def test_idempotent_replay(self):
        first = resolve()
        replay = resolve(prior_resolution=first, observed_at="2026-08-05T13:50:00Z")
        self.assertEqual(replay["replay_status"], "IDEMPOTENT_REPLAY")
        self.assertEqual(replay["resolution_digest"], first["resolution_digest"])
        self.assertEqual(replay["current_gate"], first["current_gate"])

    def test_replay_conflict_precedes_binding(self):
        first = resolve()
        evidence = complete_evidence()
        evidence["entries"][0]["digest"] = "sha256:" + "d" * 64
        out = resolve(evidence_map=evidence, prior_resolution=first)
        self.assertEqual(out["replay_status"], "REPLAY_CONFLICT")
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_REPLAY_CONFLICT")

    def test_new_event_key_is_first_seen(self):
        first = resolve()
        out = resolve(prior_resolution=first, event_id_or_idempotency_key="scrum-184-event-2")
        self.assertEqual(out["replay_status"], "FIRST_SEEN")

    def test_deterministic_ordering(self):
        evidence = complete_evidence()
        evidence["entries"] = list(reversed(evidence["entries"]))
        a = resolve(evidence_map=complete_evidence())
        b = resolve(evidence_map=evidence)
        self.assertEqual(a["canonical_evidence_refs"], b["canonical_evidence_refs"])
        self.assertEqual(a["current_gate"], b["current_gate"])

    def test_gate_order_constant(self):
        self.assertEqual(GATE_ORDER[0], "G0_CONTEXT")
        self.assertEqual(GATE_ORDER[-1], "G6_PRODUCTION_DATA")


if __name__ == "__main__":
    unittest.main()
