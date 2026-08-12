#!/usr/bin/env python3
"""Focused + neighbor regression tests for intake_context.request-intake (SCRUM-298)."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/intake-request.schema.json"
EVAL = ROOT / "tools/node_architect/request_intake.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("request_intake", EVAL)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_schema():
    import jsonschema
    from jsonschema import Draft202012Validator
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


M = _load_module()
SCHEMA_OBJ = _load_schema()
from jsonschema import Draft202012Validator
VALIDATOR = Draft202012Validator(SCHEMA_OBJ)

TASK = "SCRUM-298"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "cfaad52b0484145d6304f49183fba11cb6b1f225"


def _req(raw_text, source="USER", **kw):
    return {"raw_text": raw_text, "source": source, "provenance": {"actor": "nhat"}, **kw}


class RequestIntakeTests(unittest.TestCase):
    def _assert_valid(self, art):
        errors = sorted(VALIDATOR.iter_errors(art), key=lambda e: e.path)
        self.assertEqual([], [e.message for e in errors], msg=json.dumps(art, indent=2))
        # authority fields immutable
        for f in M.AUTH_FIELDS:
            self.assertFalse(art[f], f"{f} must be false")
        self.assertTrue(art["read_only_projection"])

    def test_accepted_well_formed_request(self):
        art = M.render_request_intake(
            task_id=TASK, repository=REPO, base_sha=BASE,
            request=_req("Implement request-intake node for SCRUM-298",
                         task_binding="SCRUM-298",
                         repository_intent="nhatnguyenquang1838-coder/gwc",
                         requested_outcome="Typed intake record"),
        )
        self.assertEqual("ACCEPTED", art["outcome"])
        self.assertEqual("INTAKE_ACCEPTED", art["reason_code"])
        self.assertIsNotNone(art["normalized_intake"])
        self.assertEqual(["intake_context.source-resolution", "intake_context.context-gap-escalation"],
                         art["next_allowed_nodes"])
        self._assert_valid(art)

    def test_missing_task_binding_is_human_required(self):
        art = M.render_request_intake(
            task_id=TASK, repository=REPO, base_sha=BASE,
            request=_req("do the thing", repository_intent=REPO, requested_outcome="x"),
        )
        self.assertEqual("HUMAN_REQUIRED", art["outcome"])
        self.assertIn("INTAKE_MISSING_TASK_BINDING", art["reason_codes"])
        self.assertIn("task_binding", art["missing_fields"])
        self.assertEqual("REQUEST_HUMAN_INPUT", art["remediation"]["route"])
        self._assert_valid(art)

    def test_missing_repository_intent_and_outcome(self):
        art = M.render_request_intake(
            task_id=TASK, repository=REPO, base_sha=BASE,
            request=_req("build node", task_binding="SCRUM-298"),
        )
        self.assertEqual("HUMAN_REQUIRED", art["outcome"])
        self.assertIn("INTAKE_MISSING_REPOSITORY_INTENT", art["reason_codes"])
        self.assertIn("INTAKE_MISSING_REQUESTED_OUTCOME", art["reason_codes"])
        self._assert_valid(art)

    def test_authority_intent_detected_not_promoted(self):
        art = M.render_request_intake(
            task_id=TASK, repository=REPO, base_sha=BASE,
            request=_req("merge to main and deploy to production for SCRUM-298",
                         task_binding="SCRUM-298", repository_intent=REPO,
                         requested_outcome="ship"),
        )
        self.assertEqual("HUMAN_REQUIRED", art["outcome"])
        self.assertIn("INTAKE_AUTHORITY_INTENT_DETECTED", art["reason_codes"])
        self.assertIn("MERGE_AUTHORITY", art["intent_authority_signals"])
        self.assertIn("PRODUCTION_AUTHORITY", art["intent_authority_signals"])
        # explicitly not promoted to gate authority
        for f in M.AUTH_FIELDS:
            self.assertFalse(art[f])
        self._assert_valid(art)

    def test_scope_drift_blocked(self):
        art = M.render_request_intake(
            task_id=TASK, repository=REPO, base_sha=BASE,
            request=_req("run a migration and force-push the branch",
                         task_binding="SCRUM-298", repository_intent=REPO,
                         requested_outcome="migrate"),
        )
        self.assertIn("INTAKE_SCOPE_DRIFT", art["reason_codes"])
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertEqual("BLOCK_G1_REVIEW", art["remediation"]["route"])
        self._assert_valid(art)

    def test_ambiguous_intent(self):
        art = M.render_request_intake(
            task_id=TASK, repository=REPO, base_sha=BASE,
            request=_req("implement SCRUM-298 but also skip the tests",
                         task_binding="SCRUM-298", repository_intent=REPO,
                         requested_outcome="impl"),
        )
        self.assertIn("INTAKE_AMBIGUOUS_INTENT", art["reason_codes"])
        self._assert_valid(art)

    def test_malformed_inputs_fail_closed(self):
        art = M.render_request_intake(
            task_id="", repository="bad repo", base_sha="xyz", request={"raw_text": 123, "source": "NOPE"},
        )
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertEqual("INTAKE_MALFORMED_INPUT", art["reason_code"])
        self._assert_valid(art)

    def test_replay_idempotent_digest(self):
        kw = dict(task_id=TASK, repository=REPO, base_sha=BASE,
                  request=_req("Implement request-intake node for SCRUM-298",
                               task_binding="SCRUM-298", repository_intent=REPO,
                               requested_outcome="Typed intake record"))
        a = M.render_request_intake(**kw)
        digest = a["decision_digest"]
        # identical replay (no prior) -> identical digest, no duplicate effect
        b = M.render_request_intake(**kw)
        self.assertEqual(a["decision_digest"], b["decision_digest"])
        # replay WITH the same prior_intake_digest -> stable idempotent digest
        c1 = M.render_request_intake(**kw, prior_intake_digest=digest)
        c2 = M.render_request_intake(**kw, prior_intake_digest=digest)
        self.assertEqual("INTAKE_REPLAY_IDEMPOTENT", c1["reason_code"])
        self.assertEqual(c1["decision_digest"], c2["decision_digest"])
        self.assertNotEqual(a["decision_digest"], c1["decision_digest"])
        self._assert_valid(b)
        self._assert_valid(c1)

    def test_unknown_source_never_passes(self):
        art = M.render_request_intake(
            task_id=TASK, repository=REPO, base_sha=BASE,
            request=_req("x", source="TELEPATHY", task_binding="SCRUM-298",
                         repository_intent=REPO, requested_outcome="y"),
        )
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertEqual("INTAKE_MALFORMED_INPUT", art["reason_code"])


if __name__ == "__main__":
    import unittest
    unittest.main()
