#!/usr/bin/env python3
"""NA81 projection privacy boundary tests for SCRUM-351 (NA81-F6-N09).

Exercises the SCRUM-351 (NA81-F6-N09) ``decide_projection_privacy_na81`` layer
over the existing sync_projection ``decide_projection_privacy`` evaluator
(SCRUM-228). Maps every current-brief requirement to code + tests:

* allowed field -> ALLOW / READY
* sanitizable field -> SANITIZE / REDACTED
* denied sensitive field -> DENY / BLOCKED
* unknown classification -> fail closed (never projected)
* policy drift -> deterministic digest change
* replay / deterministic output
* projection non-authority (read-only, no authority grants)

Imported via an absolute ``tools/`` path insertion so ``import
node_architect...`` resolves under ``python -m unittest discover`` from the
repository root (PEP 420 namespace packages).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import node_architect.projection_privacy_boundary_check as pb  # noqa: E402

TASK_ID = "SCRUM-351"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
PROJECTION_TARGET = "ds-admin"
REVISION_A = "d9a89a002aae4348359cd88810a9d03926199597"
REVISION_B = "e9a89a002aae4348359cd88810a9d03926199598"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _digest(payload):
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _source_authority_digest(decision):
    semantic = {k: v for k, v in decision.items() if k not in {"reason_codes", "decision_digest"}}
    return _digest(semantic)


def valid_source_authority_decision(status="VERIFIED", task_id=TASK_ID, revision=REVISION_A, target=PROJECTION_TARGET):
    decision = {
        "schema_version": "1.0",
        "artifact_type": "projection-source-authority-decision",
        "task_id": task_id,
        "repository": REPOSITORY,
        "projection_target": target,
        "source_bindings": [
            {
                "source_type": "TASK_RECORD",
                "authority_class": "CANONICAL",
                "ref": "jira:" + task_id,
                "revision": revision,
                "content_digest": DIGEST_A,
                "observed_at": "2026-08-04T17:00:00Z",
                "status": status,
            }
        ],
        "field_authority": [
            {
                "field_path": "/task/status",
                "source_ref": "jira:" + task_id,
                "source_revision": revision,
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
    decision["decision_digest"] = _source_authority_digest(decision)
    return decision


def clean_policy():
    return {
        "policy_revision": "privacy-v1",
        "allowed_classes": [
            "PUBLIC_METADATA",
            "INTERNAL_METADATA",
            "CONFIDENTIAL_METADATA",
            "PERSONAL_SENSITIVE",
            "POLICY_REDACTED",
        ],
        "redact_fields": ["owner_email"],
        "remove_fields": ["owner_ssn"],
    }


def _decide(**overrides):
    payload = {
        "task_id": TASK_ID,
        "repository": REPOSITORY,
        "projection_target": PROJECTION_TARGET,
        "source_authority_decision": valid_source_authority_decision(),
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
    return pb.decide_projection_privacy_na81(**payload)


class ProjectionPrivacyBoundaryNa81Tests(unittest.TestCase):
    # --- naive disposition mapping -------------------------------------
    def test_disposition_allow(self):
        self.assertEqual(
            pb.na81_disposition_for("status", "PUBLIC_METADATA", {}), pb.DISPOSITION_ALLOW
        )

    def test_disposition_sanitize(self):
        self.assertEqual(
            pb.na81_disposition_for("owner_email", "PERSONAL_SENSITIVE", {}), pb.DISPOSITION_SANITIZE
        )

    def test_disposition_deny_prohibited(self):
        for cls in ("SECRET", "CREDENTIAL", "TOKEN", "PRIVATE_KEY", "PRODUCTION_DATA", "HIDDEN_REASONING"):
            with self.subTest(cls=cls):
                self.assertEqual(pb.na81_disposition_for("v", cls, {}), pb.DISPOSITION_DENY)

    def test_disposition_unclassified_protected_key_fails_closed(self):
        # Protected key with no classification hint must fail closed.
        self.assertEqual(
            pb.na81_disposition_for("password", None, {}), pb.DISPOSITION_UNKNOWN_FAIL_CLOSED
        )

    def test_disposition_unknown_classification_fails_closed(self):
        # Explicit but unrecognized classification fails closed.
        self.assertEqual(
            pb.na81_disposition_for("note", "TOTALLY_UNKNOWN", {}), pb.DISPOSITION_UNKNOWN_FAIL_CLOSED
        )

    def test_disposition_non_protected_unclassified_defaults_allow(self):
        self.assertEqual(pb.na81_disposition_for("notes", None, {}), pb.DISPOSITION_ALLOW)

    # --- 1. allowed field -------------------------------------------------
    def test_allowed_field_ready(self):
        res = _decide(
            candidate_payload={"id": "task-1", "status": "open"},
            field_classifications=[],
            redaction_policy={"policy_revision": "privacy-v1", "allowed_classes": ["PUBLIC_METADATA"]},
        )
        self.assertEqual(res["outcome"], "READY")
        self.assertEqual(res["reason_code"], "PRIVACY_APPROVED")
        self.assertEqual(res["privacy_status"], "APPROVED")
        self.assertEqual(res["privacy_decision"]["sanitized_payload"], {"id": "task-1", "status": "open"})
        self.assertTrue(res["na81"]["no_secrets_credentials"])

    # --- 2. sanitizable field --------------------------------------------
    def test_sanitizable_field_redacted(self):
        res = _decide()
        self.assertEqual(res["outcome"], "READY")
        self.assertEqual(res["reason_code"], "PRIVACY_APPROVED_REDACTED")
        self.assertEqual(res["privacy_status"], "REDACTED")
        # originals never appear
        out = json.dumps(res["privacy_decision"]["sanitized_payload"])
        self.assertNotIn("alice@example.com", out)
        self.assertNotIn("123-45-6789", out)
        self.assertEqual(res["privacy_decision"]["sanitized_payload"].get("owner_email"), "[REDACTED]")
        self.assertNotIn("owner_ssn", res["privacy_decision"]["sanitized_payload"])
        self.assertTrue(res["na81"]["no_secrets_credentials"])

    # --- 3. denied sensitive field ---------------------------------------
    def test_denied_sensitive_field_blocked(self):
        res = _decide(
            candidate_payload={"secret": "x"},
            field_classifications=[{"field_path": "secret", "classification": "SECRET"}],
            redaction_policy={"policy_revision": "privacy-v1", "allowed_classes": ["SECRET"]},
        )
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PRIVACY_SECRET_REJECTED")

    # --- 4. unknown classification fails closed --------------------------
    def test_unknown_classification_fails_closed(self):
        res = _decide(
            candidate_payload={"note": "x"},
            field_classifications=[{"field_path": "note", "classification": "NOT_A_REAL_CLASS"}],
            redaction_policy={"policy_revision": "privacy-v1", "allowed_classes": ["NOT_A_REAL_CLASS"]},
        )
        self.assertTrue(res["na81"]["unknown_classification_detected"])
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertTrue(res["na81"]["unknown_classification_fail_closed"])

    def test_no_secrets_credentials_in_output(self):
        res = _decide(
            candidate_payload={"password": "hunter2"},
            field_classifications=[],
            redaction_policy={"policy_revision": "privacy-v1", "allowed_classes": ["PUBLIC_METADATA"]},
        )
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PRIVACY_CLASSIFICATION_MISSING")
        # Even when blocked, the projection must never carry the secret.
        self.assertTrue(res["na81"]["no_secrets_credentials"])

    # --- 5. policy drift -------------------------------------------------
    def test_policy_drift_changes_digest(self):
        first = _decide()
        second = _decide(redaction_policy={**clean_policy(), "policy_revision": "privacy-v2"})
        self.assertNotEqual(first["privacy_boundary_digest"], second["privacy_boundary_digest"])

    # --- 6. replay / deterministic --------------------------------------
    def test_replay_deterministic(self):
        r1 = _decide()
        r2 = _decide()
        self.assertEqual(r1["privacy_boundary_digest"], r2["privacy_boundary_digest"])
        self.assertTrue(r1["na81"]["deterministic"])

    def test_digest_stability_across_classification_ordering(self):
        first = _decide()
        reordered = _decide(
            field_classifications=[
                {"field_path": "owner_ssn", "classification": "PERSONAL_SENSITIVE"},
                {"field_path": "owner_email", "classification": "PERSONAL_SENSITIVE"},
            ],
        )
        self.assertEqual(first["privacy_boundary_digest"], reordered["privacy_boundary_digest"])

    # --- 7. projection non-authority -------------------------------------
    def test_projection_non_authoritative(self):
        res = _decide()
        self.assertTrue(res["na81"]["non_authoritative"])
        base = res["privacy_decision"]
        self.assertTrue(base["read_only_projection"])
        for key in (
            "write_authority_granted",
            "approval_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(base[key])
        self.assertEqual(res["artifact_type"], "projection-privacy-boundary-decision")

    # --- negative: blocked source authority -----------------------------
    def test_blocked_source_authority_rejected(self):
        blocked = valid_source_authority_decision(status="VERIFIED")
        blocked["outcome"] = "BLOCKED"
        blocked["decision_digest"] = _source_authority_digest(blocked)
        res = _decide(source_authority_decision=blocked)
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PRIVACY_SOURCE_AUTHORITY_INVALID")


if __name__ == "__main__":
    unittest.main()
