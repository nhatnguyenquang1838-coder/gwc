import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from tools.node_architect.projection_source_authority_check import decide_projection_source_authority
from tools.node_architect.projection_evidence_linking import build_projection_evidence_linkset
from tools.node_architect.projection_privacy_boundary_check import decide_projection_privacy

SCHEMA = json.loads(Path("schemas/projection-source-authority-decision.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
LINK_SCHEMA = json.loads(Path("schemas/projection-evidence-linkset.schema.json").read_text(encoding="utf-8"))
LINK_VALIDATOR = Draft202012Validator(LINK_SCHEMA, format_checker=FormatChecker())
PRIVACY_SCHEMA = json.loads(Path("schemas/projection-privacy-decision.schema.json").read_text(encoding="utf-8"))
PRIVACY_VALIDATOR = Draft202012Validator(PRIVACY_SCHEMA, format_checker=FormatChecker())


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
REVISION_A = "d9a89a002aae4348359cd88810a9d03926199597"
REVISION_B = "e9a89a002aae4348359cd88810a9d03926199598"


def valid_input():
    return {
        "task_id": "SCRUM-223",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "ds-admin",
        "requested_fields": ["/task/status"],
        "source_bindings": [
            {
                "source_type": "TASK_RECORD",
                "authority_class": "CANONICAL",
                "ref": "jira:SCRUM-223",
                "revision": REVISION_A,
                "content_digest": DIGEST_A,
                "observed_at": "2026-08-03T13:00:00Z",
                "status": "VERIFIED",
            }
        ],
        "field_evidence": [
            {
                "field_path": "/task/status",
                "source_ref": "jira:SCRUM-223",
                "source_revision": REVISION_A,
                "evidence_digest": DIGEST_A,
                "derivation": "DIRECT",
            }
        ],
        "current_revisions": [
            {
                "ref": "jira:SCRUM-223",
                "revision": REVISION_A,
                "observed_at": "2026-08-03T13:05:00Z",
            }
        ],
        "freshness_policy": {
            "max_source_age_seconds": 3600,
            "max_readback_age_seconds": 900,
        },
        "observed_at": "2026-08-03T13:10:00Z",
    }


class ProjectionSourceAuthorityTests(unittest.TestCase):
    def assert_schema_valid(self, decision):
        errors = sorted(VALIDATOR.iter_errors(decision), key=lambda error: list(error.path))
        self.assertEqual(errors, [], [error.message for error in errors])

    def decide(self, payload=None):
        decision = decide_projection_source_authority(**(payload or valid_input()))
        self.assert_schema_valid(decision)
        return decision

    def test_valid_direct_evidence_is_ready_and_read_only(self):
        decision = self.decide()
        self.assertEqual(decision["outcome"], "READY")
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_AUTHORITY_CONFIRMED")
        self.assertTrue(decision["read_only_projection"])
        for key in (
            "write_authority_granted",
            "approval_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(decision[key])

    def test_known_deterministic_derivation_is_ready(self):
        payload = valid_input()
        payload["field_evidence"][0]["derivation"] = "DETERMINISTIC_DERIVATION"
        payload["field_evidence"][0]["derivation_rule_id"] = "canonical-json-pointer-v1"
        self.assertEqual(self.decide(payload)["outcome"], "READY")

    def test_no_canonical_source_fails_closed(self):
        payload = valid_input()
        payload["source_bindings"][0]["authority_class"] = "ADVISORY"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_CANONICAL_MISSING")

    def test_projection_only_source_rejected(self):
        payload = valid_input()
        payload["source_bindings"].append(
            {
                **payload["source_bindings"][0],
                "authority_class": "PROJECTION",
                "ref": "projection:task-center:SCRUM-223",
                "revision": REVISION_B,
                "content_digest": DIGEST_B,
            }
        )
        payload["field_evidence"][0].update(
            source_ref="projection:task-center:SCRUM-223",
            source_revision=REVISION_B,
            evidence_digest=DIGEST_B,
        )
        payload["current_revisions"].append(
            {"ref": "projection:task-center:SCRUM-223", "revision": REVISION_B, "observed_at": "2026-08-03T13:05:00Z"}
        )
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_AUTHORITY_INVALID")

    def test_missing_field_binding_rejected(self):
        payload = valid_input()
        payload["requested_fields"].append("/task/assignee")
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_FIELD_UNBOUND")

    def test_ambiguous_or_conflicting_binding_rejected(self):
        payload = valid_input()
        payload["source_bindings"][0]["status"] = "CONFLICT"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_CONFLICT")

    def test_digest_mismatch_rejected(self):
        payload = valid_input()
        payload["field_evidence"][0]["evidence_digest"] = DIGEST_B
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_DIGEST_MISMATCH")

    def test_current_revision_drift_rejected(self):
        payload = valid_input()
        payload["current_revisions"][0]["revision"] = REVISION_B
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_REVISION_DRIFT")

    def test_stale_source_rejected(self):
        payload = valid_input()
        payload["source_bindings"][0]["observed_at"] = "2026-08-03T10:00:00Z"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_STALE")

    def test_missing_canonical_binding_status_rejected(self):
        payload = valid_input()
        payload["source_bindings"][0]["status"] = "MISSING"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_CANONICAL_MISSING")

    def test_missing_current_readback_rejected(self):
        payload = valid_input()
        payload["current_revisions"] = []
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_REVISION_DRIFT")

    def test_stale_readback_rejected(self):
        payload = valid_input()
        payload["current_revisions"][0]["observed_at"] = "2026-08-03T12:00:00Z"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_STALE")

    def test_unknown_derivation_rule_rejected(self):
        payload = valid_input()
        payload["field_evidence"][0]["derivation"] = "DETERMINISTIC_DERIVATION"
        payload["field_evidence"][0]["derivation_rule_id"] = "unknown-rule-v99"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_DERIVATION_UNVERIFIED")

    def test_inferred_status_rejected(self):
        payload = valid_input()
        payload["field_evidence"][0]["derivation"] = "INFERRED"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_INFERRED_STATUS_REJECTED")
        self.assertIn("PROJECTION_SOURCE_FIELD_UNBOUND", decision["reason_codes"])

    def test_empty_fields_rejected_before_source_analysis(self):
        payload = valid_input()
        payload["requested_fields"] = []
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_FIELDS_EMPTY")

    def test_invalid_input_precedence(self):
        payload = valid_input()
        payload["task_id"] = "bad"
        payload["requested_fields"] = []
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_INPUT_INVALID")

    def test_input_order_does_not_change_digest(self):
        payload = valid_input()
        payload["requested_fields"].append("/task/id")
        payload["field_evidence"].append(
            {
                "field_path": "/task/id",
                "source_ref": "jira:SCRUM-223",
                "source_revision": REVISION_A,
                "evidence_digest": DIGEST_A,
                "derivation": "DIRECT",
            }
        )
        first = self.decide(payload)
        reordered = copy.deepcopy(payload)
        reordered["requested_fields"].reverse()
        reordered["field_evidence"].reverse()
        reordered["source_bindings"].reverse()
        reordered["current_revisions"].reverse()
        second = self.decide(reordered)
        self.assertEqual(first["decision_digest"], second["decision_digest"])

    def test_semantic_change_changes_digest(self):
        first = self.decide()
        payload = valid_input()
        payload["projection_target"] = "task-center"
        second = self.decide(payload)
        self.assertNotEqual(first["decision_digest"], second["decision_digest"])

    def test_observed_at_is_excluded_from_digest(self):
        first = self.decide()
        payload = valid_input()
        payload["observed_at"] = "2026-08-03T13:11:00Z"
        payload["source_bindings"][0]["observed_at"] = "2026-08-03T13:01:00Z"
        payload["current_revisions"][0]["observed_at"] = "2026-08-03T13:06:00Z"
        second = self.decide(payload)
        # Input evidence timestamps are semantic and remain in the digest; only output observed_at is excluded.
        self.assertNotEqual(first["decision_digest"], second["decision_digest"])


def _source_authority_digest(decision):
    semantic = {
        key: value
        for key, value in decision.items()
        if key not in {"observed_at", "decision_digest"}
    }
    payload = json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def valid_authority_decision():
    decision = {
        "schema_version": "1.0",
        "artifact_type": "projection-source-authority-decision",
        "task_id": "SCRUM-227",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "ds-admin",
        "source_bindings": [
            {
                "source_type": "TASK_RECORD",
                "authority_class": "CANONICAL",
                "ref": "jira:SCRUM-227",
                "revision": REVISION_A,
                "content_digest": DIGEST_A,
                "observed_at": "2026-08-03T17:00:00Z",
                "status": "VERIFIED",
            },
            {
                "source_type": "REPOSITORY",
                "authority_class": "CANONICAL",
                "ref": "github:gwc",
                "revision": REVISION_B,
                "content_digest": DIGEST_B,
                "observed_at": "2026-08-03T17:00:00Z",
                "status": "VERIFIED",
            },
        ],
        "field_authority": [
            {
                "field_path": "/task/status",
                "source_ref": "jira:SCRUM-227",
                "source_revision": REVISION_A,
                "evidence_digest": DIGEST_A,
                "derivation": "DIRECT",
            },
            {
                "field_path": "/repository/head",
                "source_ref": "github:gwc",
                "source_revision": REVISION_B,
                "evidence_digest": DIGEST_B,
                "derivation": "DIRECT",
            },
        ],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_SOURCE_AUTHORITY_CONFIRMED",
        "reason_codes": ["PROJECTION_SOURCE_AUTHORITY_CONFIRMED"],
        "observed_at": "2026-08-03T17:05:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    decision["decision_digest"] = _source_authority_digest(decision)
    return decision


def valid_evidence_items():
    return [
        {
            "evidence_id": "task-227",
            "source_type": "TASK_RECORD",
            "ref": "jira:SCRUM-227",
            "revision": REVISION_A,
            "content_digest": DIGEST_A,
            "relation": "SUPPORTS_FIELD",
            "field_paths": ["/task/status"],
            "display_url": "https://example.invalid/SCRUM-227",
            "verification_status": "VERIFIED",
        },
        {
            "evidence_id": "repo-head",
            "source_type": "REPOSITORY",
            "ref": "github:gwc",
            "revision": REVISION_B,
            "content_digest": DIGEST_B,
            "relation": "DERIVED_FROM",
            "field_paths": ["/repository/head"],
            "verification_status": "VERIFIED",
        },
    ]


class ProjectionEvidenceLinkingTests(unittest.TestCase):
    def build(self, **overrides):
        payload = {
            "task_id": "SCRUM-227",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "projection_target": "ds-admin",
            "source_authority_decision": valid_authority_decision(),
            "evidence_items": valid_evidence_items(),
            "projected_fields": ["/task/status", "/repository/head"],
            "linked_at": "2026-08-03T17:10:00Z",
        }
        payload.update(overrides)
        result = build_projection_evidence_linkset(**payload)
        errors = sorted(LINK_VALIDATOR.iter_errors(result), key=lambda error: list(error.path))
        self.assertEqual(errors, [], [error.message for error in errors])
        return result

    def test_valid_multi_source_coverage_is_ready_and_read_only(self):
        result = self.build()
        self.assertEqual(result["outcome"], "READY")
        self.assertEqual(result["reason_code"], "EVIDENCE_LINKSET_READY")
        self.assertEqual(result["covered_fields"], ["/repository/head", "/task/status"])
        self.assertEqual(result["uncovered_fields"], [])
        self.assertTrue(result["read_only_projection"])
        for key in (
            "write_authority_granted",
            "approval_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(result[key])

    def test_order_normalization_and_duplicate_collapse(self):
        items = valid_evidence_items()
        items.append(copy.deepcopy(items[0]))
        items.reverse()
        fields = ["/repository/head", "/task/status", "/task/status"]
        first = self.build(evidence_items=items, projected_fields=fields)
        second = self.build()
        self.assertEqual(len(first["links"]), 2)
        self.assertEqual(first["linkset_digest"], second["linkset_digest"])

    def test_display_url_is_preserved_but_excluded_from_digest(self):
        first = self.build()
        task_link = next(link for link in first["links"] if link["evidence_id"] == "task-227")
        self.assertEqual(task_link["display_url"], "https://example.invalid/SCRUM-227")
        items = valid_evidence_items()
        items[0]["display_url"] = "https://example.invalid/alternate"
        second = self.build(evidence_items=items)
        task_link = next(link for link in second["links"] if link["evidence_id"] == "task-227")
        self.assertEqual(task_link["display_url"], "https://example.invalid/alternate")
        self.assertEqual(first["linkset_digest"], second["linkset_digest"])

    def test_url_only_is_not_authority(self):
        item = {
            "evidence_id": "url-only",
            "source_type": "TASK_RECORD",
            "display_url": "https://example.invalid/227",
            "relation": "SUPPORTS_FIELD",
            "field_paths": ["/task/status"],
            "verification_status": "VERIFIED",
        }
        result = self.build(evidence_items=[item], projected_fields=["/task/status"])
        self.assertEqual(result["reason_code"], "EVIDENCE_LINK_IMMUTABLE_REF_MISSING")
        self.assertIn("EVIDENCE_LINK_URL_NOT_AUTHORITY", result["reason_codes"])

    def test_blocked_or_mismatched_source_authority_is_rejected(self):
        blocked = valid_authority_decision()
        blocked["outcome"] = "BLOCKED"
        self.assertEqual(
            self.build(source_authority_decision=blocked)["reason_code"],
            "EVIDENCE_LINK_SOURCE_AUTHORITY_INVALID",
        )
        mismatched = valid_authority_decision()
        mismatched["projection_target"] = "task-center"
        self.assertEqual(
            self.build(source_authority_decision=mismatched)["reason_code"],
            "EVIDENCE_LINK_SOURCE_AUTHORITY_INVALID",
        )

    def test_malformed_or_tampered_source_authority_is_rejected(self):
        malformed = valid_authority_decision()
        malformed.pop("reason_code")
        self.assertEqual(
            self.build(source_authority_decision=malformed)["reason_code"],
            "EVIDENCE_LINK_SOURCE_AUTHORITY_INVALID",
        )

        extra_field = valid_authority_decision()
        extra_field["unexpected"] = True
        extra_field["decision_digest"] = _source_authority_digest(extra_field)
        self.assertEqual(
            self.build(source_authority_decision=extra_field)["reason_code"],
            "EVIDENCE_LINK_SOURCE_AUTHORITY_INVALID",
        )

        tampered = valid_authority_decision()
        tampered["field_authority"][0]["field_path"] = "/task/assignee"
        self.assertEqual(
            self.build(source_authority_decision=tampered)["reason_code"],
            "EVIDENCE_LINK_SOURCE_AUTHORITY_INVALID",
        )

    def test_broken_stale_and_unverified_links_fail_closed(self):
        expected = {
            "BROKEN": "EVIDENCE_LINK_BROKEN",
            "STALE": "EVIDENCE_LINK_STALE",
            "UNVERIFIED": "EVIDENCE_LINK_UNVERIFIED",
        }
        for status, reason in expected.items():
            items = valid_evidence_items()
            items[0]["verification_status"] = status
            with self.subTest(status=status):
                self.assertEqual(self.build(evidence_items=items)["reason_code"], reason)

    def test_conflicting_digest_for_same_identity_is_blocked(self):
        items = valid_evidence_items()
        conflict = copy.deepcopy(items[0])
        conflict["content_digest"] = DIGEST_B
        items.append(conflict)
        self.assertEqual(
            self.build(evidence_items=items)["reason_code"],
            "EVIDENCE_LINK_DIGEST_CONFLICT",
        )

    def test_uncovered_projected_field_is_blocked(self):
        result = self.build(projected_fields=["/task/status", "/task/assignee"])
        self.assertEqual(result["reason_code"], "EVIDENCE_LINK_FIELD_UNBOUND")
        self.assertEqual(result["uncovered_fields"], ["/task/assignee"])

    def test_field_not_confirmed_by_source_authority_is_unbound(self):
        decision = valid_authority_decision()
        decision["field_authority"] = decision["field_authority"][:1]
        decision["decision_digest"] = _source_authority_digest(decision)
        result = self.build(source_authority_decision=decision)
        self.assertEqual(result["reason_code"], "EVIDENCE_LINK_FIELD_UNBOUND")
        self.assertEqual(result["uncovered_fields"], ["/repository/head"])

    def test_supersedes_preserves_old_and_new_revisions(self):
        items = valid_evidence_items()
        items.append(
            {
                "evidence_id": "task-history",
                "source_type": "TASK_RECORD",
                "ref": "jira:SCRUM-227",
                "revision": REVISION_B,
                "supersedes_revision": REVISION_A,
                "content_digest": DIGEST_B,
                "relation": "SUPERSEDES",
                "field_paths": [],
                "verification_status": "VERIFIED",
            }
        )
        result = self.build(evidence_items=items)
        history = [link for link in result["links"] if link["relation"] == "SUPERSEDES"]
        self.assertEqual(history[0]["supersedes_revision"], REVISION_A)
        self.assertEqual(history[0]["revision"], REVISION_B)

    def test_expected_digest_mismatch_is_blocked(self):
        result = self.build(expected_linkset_digest="sha256:" + "f" * 64)
        self.assertEqual(result["reason_code"], "EVIDENCE_LINK_DIGEST_MISMATCH")

    def test_semantic_provenance_change_changes_digest(self):
        first = self.build()
        items = valid_evidence_items()
        items[1]["relation"] = "SUPPORTS_FIELD"
        second = self.build(evidence_items=items)
        self.assertNotEqual(first["linkset_digest"], second["linkset_digest"])


def _source_authority_digest_for_privacy(decision):
    semantic = {
        key: value
        for key, value in decision.items()
        if key not in {"reason_codes", "decision_digest"}
    }
    payload = json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def valid_privacy_authority_decision():
    decision = {
        "schema_version": "1.0",
        "artifact_type": "projection-source-authority-decision",
        "task_id": "SCRUM-228",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "ds-admin",
        "source_bindings": [
            {
                "source_type": "TASK_RECORD",
                "authority_class": "CANONICAL",
                "ref": "jira:SCRUM-228",
                "revision": REVISION_A,
                "content_digest": DIGEST_A,
                "observed_at": "2026-08-04T17:00:00Z",
                "status": "VERIFIED",
            }
        ],
        "field_authority": [
            {
                "field_path": "/task/status",
                "source_ref": "jira:SCRUM-228",
                "source_revision": REVISION_A,
                "evidence_digest": DIGEST_A,
                "derivation": "DIRECT",
            }
        ],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_SOURCE_AUTHORITY_CONFIRMED",
        "reason_codes": ["PROJECTION_SOURCE_AUTHORITY_CONFIRMED"],
        "observed_at": "2026-08-04T17:05:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    decision["decision_digest"] = _source_authority_digest_for_privacy(decision)
    return decision


def clean_policy():
    return {
        "policy_revision": "privacy-v1",
        "allowed_classes": ["PUBLIC_METADATA", "INTERNAL_METADATA", "CONFIDENTIAL_METADATA", "PERSONAL_SENSITIVE", "POLICY_REDACTED"],
        "redact_fields": ["owner_email"],
        "remove_fields": ["owner_ssn"],
        "max_string_length": 4096,
        "max_list_length": 1024,
        "max_object_depth": 16,
        "allow_stable_pseudonymous_actor_ids": True,
    }


class ProjectionPrivacyBoundaryTests(unittest.TestCase):
    def decide(self, **overrides):
        payload = {
            "task_id": "SCRUM-228",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "projection_target": "ds-admin",
            "source_authority_decision": valid_privacy_authority_decision(),
            "candidate_payload": {
                "id": "task-1",
                "status": "open",
                "owner_email": "alice@example.com",
                "owner_ssn": "123-45-6789",
            },
            "field_classifications": [
                {"field_path": "owner_email", "classification": "PERSONAL_SENSITIVE"},
                {"field_path": "owner_ssn", "classification": "PERSONAL_SENSITIVE"},
            ],
            "redaction_policy": clean_policy(),
            "evaluated_at": "2026-08-04T17:10:00Z",
        }
        payload.update(overrides)
        result = decide_projection_privacy(**payload)
        errors = sorted(PRIVACY_VALIDATOR.iter_errors(result), key=lambda error: list(error.path))
        self.assertEqual(errors, [], [error.message for error in errors])
        return result

    def test_clean_metadata_approved(self):
        result = self.decide(
            candidate_payload={"id": "task-1", "status": "open"},
            field_classifications=[],
            redaction_policy={"policy_revision": "privacy-v1", "allowed_classes": ["PUBLIC_METADATA"]},
        )
        self.assertEqual(result["outcome"], "READY")
        self.assertEqual(result["reason_code"], "PRIVACY_APPROVED")
        self.assertEqual(result["privacy_status"], "APPROVED")
        self.assertEqual(result["sanitized_payload"], {"id": "task-1", "status": "open"})
        self.assertEqual(result["redactions"], [])

    def test_safe_redaction_records_no_originals(self):
        result = self.decide()
        self.assertEqual(result["outcome"], "READY")
        self.assertEqual(result["reason_code"], "PRIVACY_APPROVED_REDACTED")
        self.assertEqual(result["privacy_status"], "REDACTED")
        # originals never appear
        self.assertNotIn("alice@example.com", canonical_json(result["sanitized_payload"]))
        self.assertNotIn("123-45-6789", canonical_json(result["sanitized_payload"]))
        self.assertEqual(result["sanitized_payload"].get("owner_email"), "[REDACTED]")
        self.assertNotIn("owner_ssn", result["sanitized_payload"])
        for redaction in result["redactions"]:
            self.assertNotIn("alice@example.com", canonical_json(redaction))
            self.assertNotIn("123-45-6789", canonical_json(redaction))

    def test_unclassified_protected_key_fails_closed(self):
        result = self.decide(
            candidate_payload={"password": "hunter2"},
            field_classifications=[],
            redaction_policy={"policy_revision": "privacy-v1", "allowed_classes": ["PUBLIC_METADATA"]},
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertEqual(result["reason_code"], "PRIVACY_CLASSIFICATION_MISSING")

    def test_each_prohibited_class_rejected(self):
        cases = {
            "secret": "PRIVACY_SECRET_REJECTED",
            "credential": "PRIVACY_CREDENTIAL_REJECTED",
            "token": "PRIVACY_TOKEN_REJECTED",
            "private_key": "PRIVACY_PRIVATE_KEY_REJECTED",
            "production_data": "PRIVACY_PRODUCTION_DATA_REJECTED",
            "hidden_reasoning": "PRIVACY_HIDDEN_REASONING_REJECTED",
        }
        for cls, reason in cases.items():
            with self.subTest(cls=cls):
                result = self.decide(
                    candidate_payload={"v": "x"},
                    field_classifications=[{"field_path": "v", "classification": cls.upper()}],
                    redaction_policy={"policy_revision": "privacy-v1", "allowed_classes": [cls.upper()]},
                )
                self.assertEqual(result["reason_code"], reason)

    def test_nested_prohibited_key_detected_recursively(self):
        result = self.decide(
            candidate_payload={"a": {"b": {"access_token": "leaky"}}},
            field_classifications=[],
            redaction_policy={"policy_revision": "privacy-v1", "allowed_classes": ["PUBLIC_METADATA"]},
        )
        self.assertEqual(result["reason_code"], "PRIVACY_CLASSIFICATION_MISSING")
        self.assertIn("PRIVACY_CLASSIFICATION_MISSING", result["reason_codes"])

    def test_target_policy_denial_fails_closed(self):
        result = self.decide(
            candidate_payload={"note": "confidential"},
            field_classifications=[{"field_path": "note", "classification": "CONFIDENTIAL_METADATA"}],
            redaction_policy={"policy_revision": "privacy-v1", "allowed_classes": ["PUBLIC_METADATA"]},
        )
        self.assertEqual(result["reason_code"], "PRIVACY_TARGET_POLICY_DENIED")
        self.assertNotIn("note", result["sanitized_payload"])

    def test_invalid_redaction_directive_fails_closed(self):
        result = self.decide(
            redaction_policy={"policy_revision": "privacy-v1", "allowed_classes": ["PUBLIC_METADATA"], "redact_fields": "owner_email"},
        )
        self.assertEqual(result["reason_code"], "PRIVACY_REDACTION_DIRECTIVE_INVALID")

    def test_payload_size_limit_exceeded(self):
        big = {"blob": "x" * (1024 * 1024 + 1)}
        result = self.decide(
            candidate_payload=big,
            field_classifications=[],
            redaction_policy={"policy_revision": "privacy-v1", "allowed_classes": ["PUBLIC_METADATA"]},
        )
        self.assertEqual(result["reason_code"], "PRIVACY_PAYLOAD_LIMIT_EXCEEDED")

    def test_blocked_source_authority_rejected(self):
        blocked = valid_privacy_authority_decision()
        blocked["outcome"] = "BLOCKED"
        result = self.decide(source_authority_decision=blocked)
        self.assertEqual(result["reason_code"], "PRIVACY_SOURCE_AUTHORITY_INVALID")

    def test_mismatched_source_authority_rejected(self):
        mismatched = valid_privacy_authority_decision()
        mismatched["projection_target"] = "task-center"
        result = self.decide(source_authority_decision=mismatched)
        self.assertEqual(result["reason_code"], "PRIVACY_SOURCE_AUTHORITY_INVALID")

    def test_residual_leak_detected(self):
        # Policy permits the class but a raw protected value still survives -> leak scan.
        leaked = valid_privacy_authority_decision()
        leaked["decision_digest"] = _source_authority_digest_for_privacy(leaked)
        # Force a payload whose sanitized copy still embeds a raw token-like string.
        result = self.decide(
            source_authority_decision=leaked,
            candidate_payload={"exposed": "this contains a raw password inside"},
            field_classifications=[],
            redaction_policy={"policy_revision": "privacy-v1", "allowed_classes": ["PUBLIC_METADATA"]},
        )
        self.assertEqual(result["reason_code"], "PRIVACY_LEAK_DETECTED")

    def test_digest_stability_across_ordering(self):
        first = self.decide()
        reordered = self.decide(
            field_classifications=[
                {"field_path": "owner_ssn", "classification": "PERSONAL_SENSITIVE"},
                {"field_path": "owner_email", "classification": "PERSONAL_SENSITIVE"},
            ],
        )
        self.assertEqual(first["sanitized_digest"], reordered["sanitized_digest"])
        self.assertEqual(first["decision_digest"], reordered["decision_digest"])

    def test_digest_drift_on_policy_change(self):
        first = self.decide()
        second = self.decide(
            redaction_policy={**clean_policy(), "policy_revision": "privacy-v2"},
        )
        self.assertNotEqual(first["sanitized_digest"], second["sanitized_digest"])

    def test_expected_digest_mismatch_fails_closed(self):
        result = self.decide(expected_sanitized_digest="sha256:" + "f" * 64)
        self.assertEqual(result["reason_code"], "PRIVACY_DIGEST_MISMATCH")

    def test_no_authority_field_can_be_true(self):
        result = self.decide()
        for key in (
            "read_only_projection",
            "write_authority_granted",
            "approval_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertIn(key, result)
        self.assertTrue(result["read_only_projection"])
        for key in (
            "write_authority_granted",
            "approval_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(result[key])


if __name__ == "__main__":
    unittest.main()
