import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from tools.node_architect.task_center_sync import project_task_center_sync

SCHEMA = json.loads(Path("schemas/task-center-sync-projection.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
REVISION_A = "d9a89a002aae4348359cd88810a9d03926199597"
REVISION_B = "e9a89a002aae4348359cd88810a9d03926199598"


def _source_authority_digest(decision):
    semantic = {k: v for k, v in decision.items() if k not in {"reason_codes", "decision_digest"}}
    payload = json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def valid_source_authority():
    decision = {
        "schema_version": "1.0",
        "artifact_type": "projection-source-authority-decision",
        "task_id": "SCRUM-221",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "task-center",
        "source_bindings": [
            {"source_type": "TASK_RECORD", "authority_class": "CANONICAL", "ref": "jira:SCRUM-221",
             "revision": REVISION_A, "content_digest": DIGEST_A, "observed_at": "2026-08-06T13:00:00Z", "status": "VERIFIED"},
        ],
        "field_authority": [
            {"field_path": "/task/status", "source_ref": "jira:SCRUM-221", "source_revision": REVISION_A,
             "evidence_digest": DIGEST_A, "derivation": "DIRECT"},
        ],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_SOURCE_AUTHORITY_CONFIRMED",
        "reason_codes": ["PROJECTION_SOURCE_AUTHORITY_CONFIRMED"],
        "observed_at": "2026-08-06T13:05:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    decision["decision_digest"] = _source_authority_digest(decision)
    return decision


def valid_linkset(source_digest=DIGEST_A):
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-evidence-linkset",
        "task_id": "SCRUM-221",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "task-center",
        "source_authority_digest": source_digest,
        "links": [
            {"evidence_id": "task-221", "source_type": "TASK_RECORD", "ref": "jira:SCRUM-221",
             "revision": REVISION_A, "content_digest": DIGEST_A, "relation": "SUPPORTS_FIELD",
             "field_paths": ["/task/status"], "verification_status": "VERIFIED"},
        ],
        "covered_fields": ["/task/status"],
        "uncovered_fields": [],
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "link_status": "VERIFIED",
        "outcome": "READY",
        "reason_code": "EVIDENCE_LINKSET_READY",
        "reason_codes": ["EVIDENCE_LINKSET_READY"],
        "linked_at": "2026-08-06T13:10:00Z",
        "linkset_digest": DIGEST_B,
    }


def valid_privacy():
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-privacy-decision",
        "task_id": "SCRUM-221",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "task-center",
        "outcome": "READY",
        "reason_code": "PRIVACY_APPROVED",
        "reason_codes": ["PRIVACY_APPROVED"],
        "observed_at": "2026-08-06T13:12:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "decision_digest": DIGEST_C,
    }


def valid_envelope(source_digest=DIGEST_A):
    return {
        "schema_version": "1.0",
        "artifact_type": "sync-projection-envelope",
        "task_id": "SCRUM-221",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "task-center",
        "source_authority_digest": source_digest,
        "evidence_linkset_digest": DIGEST_B,
        "privacy_boundary_digest": DIGEST_C,
        "prior_projection": None,
        "freshness_policy": {"max_source_age_seconds": 3600, "max_readback_age_seconds": 900},
        "canonical_state": {
            "task_id": "SCRUM-221",
            "task_status": "In Progress",
            "task_title": "Task Center sync",
            "task_type": "Subtask",
            "task_assignee": "Nhat Nguyen Quang",
            "gate": "G2_EXECUTION",
            "gate_outcome": "PASS",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "repository_head": REVISION_A,
            "projection_target": "task-center",
            "projected_at": "2026-08-06T13:15:00Z",
        },
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


class TaskCenterSyncTests(unittest.TestCase):
    def assert_schema_valid(self, projection):
        errors = sorted(VALIDATOR.iter_errors(projection), key=lambda error: list(error.path))
        self.assertEqual(errors, [], [error.message for error in errors])

    def build(self, **overrides):
        decision = valid_source_authority()
        payload = {
            "task_id": "SCRUM-221",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "projection_target": "task-center",
            "source_authority_decision": decision,
            "evidence_linkset": valid_linkset(decision["decision_digest"]),
            "privacy_boundary_decision": valid_privacy(),
            "envelope": valid_envelope(decision["decision_digest"]),
            "projected_at": "2026-08-06T13:15:00Z",
        }
        payload.update(overrides)
        result = project_task_center_sync(**payload)
        self.assert_schema_valid(result)
        return result

    def test_valid_sync_is_ready_and_read_only(self):
        result = self.build()
        self.assertEqual(result["outcome"], "READY")
        self.assertEqual(result["reason_code"], "TASK_CENTER_SYNC_READY")
        self.assertTrue(result["read_only_projection"])
        for key in ("write_authority_granted", "approval_authority_granted",
                    "merge_authority_granted", "deployment_authority_granted",
                    "production_authority_granted"):
            self.assertFalse(result[key])

    def test_invalid_source_authority_is_blocked(self):
        bad = valid_source_authority()
        bad["outcome"] = "BLOCKED"
        self.assertEqual(self.build(source_authority_decision=bad)["reason_code"], "TASK_CENTER_SOURCE_AUTHORITY_INVALID")

    def test_invalid_evidence_linkset_is_blocked(self):
        bad = valid_linkset()
        bad["outcome"] = "BLOCKED"
        self.assertEqual(self.build(evidence_linkset=bad)["reason_code"], "TASK_CENTER_EVIDENCE_LINKSET_INVALID")

    def test_invalid_privacy_boundary_is_blocked(self):
        bad = valid_privacy()
        bad["outcome"] = "BLOCKED"
        self.assertEqual(self.build(privacy_boundary_decision=bad)["reason_code"], "TASK_CENTER_PRIVACY_BOUNDARY_INVALID")

    def test_source_authority_digest_mismatch_is_blocked(self):
        env = valid_envelope()
        env["source_authority_digest"] = DIGEST_B
        self.assertEqual(self.build(envelope=env)["reason_code"], "TASK_CENTER_SOURCE_AUTHORITY_INVALID")

    def test_prior_binding_to_other_task_is_blocked(self):
        prior = self.build()
        prior["task_id"] = "SCRUM-220"
        self.assertEqual(self.build(prior_projection=prior)["reason_code"], "TASK_CENTER_PRIOR_BINDING_MISMATCH")

    def test_revision_regression_is_blocked(self):
        prior = self.build()
        prior["canonical_state"] = {**prior["canonical_state"], "repository_head": REVISION_B}
        self.assertEqual(self.build(prior_projection=prior)["reason_code"], "TASK_CENTER_REVISION_REGRESSION")

    def test_prior_readback_mismatch_is_blocked(self):
        prior = self.build()
        prior["canonical_state"] = {**prior["canonical_state"], "task_status": "Done"}
        self.assertEqual(self.build(prior_projection=prior)["reason_code"], "TASK_CENTER_PRIOR_READBACK_MISMATCH")

    def test_prior_readback_match_is_noop_current(self):
        prior = self.build()
        result = self.build(prior_projection=prior)
        self.assertEqual(result["reason_code"], "TASK_CENTER_SYNC_CURRENT")
        self.assertTrue(result["prior_projection_present"])

    def test_disallowed_canonical_key_is_blocked(self):
        env = valid_envelope()
        env["canonical_state"] = {"secret": "x"}
        self.assertEqual(self.build(envelope=env)["reason_code"], "TASK_CENTER_INPUT_INVALID")

    def test_order_independent_digest(self):
        first = self.build()
        second_env = valid_envelope()
        second_env["canonical_state"] = dict(reversed(list(second_env["canonical_state"].items())))
        second = self.build(envelope=second_env)
        self.assertEqual(first["canonical_state_digest"], second["canonical_state_digest"])

    def test_invalid_task_id_is_blocked(self):
        self.assertEqual(self.build(task_id="bad")["reason_code"], "TASK_CENTER_INPUT_INVALID")


if __name__ == "__main__":
    unittest.main()
