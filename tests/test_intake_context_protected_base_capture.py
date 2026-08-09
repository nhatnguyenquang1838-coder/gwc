#!/usr/bin/env python3
"""Focused + neighbor regression tests for intake_context.protected-base-capture (SCRUM-301)."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/protected-base-capture.schema.json"
EVAL = ROOT / "tools/node_architect/protected_base_capture.py"
NEIGHBOR_EVAL = ROOT / "tools/node_architect/request_intake.py"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


M = _load_module("protected_base_capture", EVAL)
NEIGHBOR = _load_module("request_intake", NEIGHBOR_EVAL)

from jsonschema import Draft202012Validator

SCHEMA_OBJ = json.loads(SCHEMA.read_text(encoding="utf-8"))
Draft202012Validator.check_schema(SCHEMA_OBJ)
VALIDATOR = Draft202012Validator(SCHEMA_OBJ)

TASK = "SCRUM-301"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "67ab9839e7cf7ffb6c97f1441020f38e6d9d0ba2"
OTHER = "1111111111111111111111111111111111111111"


class ProtectedBaseCaptureTests(unittest.TestCase):
    def _assert_valid(self, art):
        errors = sorted(VALIDATOR.iter_errors(art), key=lambda e: list(e.path))
        self.assertEqual([], [e.message for e in errors], msg=json.dumps(art, indent=2))
        for f in M.AUTH_FIELDS:
            self.assertFalse(art[f], f"{f} must be false")
        self.assertTrue(art["read_only_projection"])
        if art["outcome"] == "ACCEPTED":
            self.assertIsNone(art["remediation"])
        else:
            self.assertIsNotNone(art["remediation"])

    def _render(self, **kw):
        base = dict(
            task_id=TASK, repository=REPO, protected_base_sha=BASE,
            evidence_source="Verified source-of-truth readback from origin/pre-prod.",
        )
        base.update(kw)
        return M.render_protected_base_capture(**base)

    # --- accepted capture ------------------------------------------------
    def test_accepted_capture_is_verified(self):
        art = self._render()
        self.assertEqual("ACCEPTED", art["outcome"])
        self.assertEqual("BASE_CAPTURED", art["reason_code"])
        self.assertEqual("VERIFIED", art["readback_status"])
        self.assertEqual("NONE", art["drift_state"])
        self.assertEqual([BASE], [art["protected_base_sha"]])
        self.assertEqual(["intake_context.risk-classification"], art["next_allowed_nodes"])
        self._assert_valid(art)

    def test_verified_sha_match_accepted(self):
        art = self._render(verified_sha=BASE)
        self.assertEqual("ACCEPTED", art["outcome"])
        self.assertEqual("VERIFIED", art["readback_status"])
        self._assert_valid(art)

    # --- readback mismatch ----------------------------------------------
    def test_readback_mismatch_routes_human(self):
        art = self._render(verified_sha=OTHER)
        self.assertEqual("HUMAN_REQUIRED", art["outcome"])
        self.assertEqual("BASE_READBACK_MISMATCH", art["reason_code"])
        self.assertEqual("MISMATCH", art["readback_status"])
        self.assertEqual("REQUEST_HUMAN_INPUT", art["remediation"]["route"])
        self.assertEqual([], art["next_allowed_nodes"])
        self._assert_valid(art)

    # --- drift from prior capture ---------------------------------------
    def test_drift_detected_routes_human(self):
        art = self._render(prior_capture={"protected_base_sha": OTHER})
        self.assertEqual("HUMAN_REQUIRED", art["outcome"])
        self.assertEqual("BASE_DRIFTED", art["reason_code"])
        self.assertEqual("DRIFTED", art["drift_state"])
        self.assertEqual(OTHER, art["prior_base_sha"])
        self._assert_valid(art)

    def test_matching_prior_is_idempotent(self):
        art = self._render(prior_capture={"protected_base_sha": BASE})
        self.assertEqual("ACCEPTED", art["outcome"])
        self.assertEqual("NONE", art["drift_state"])
        self.assertIsNone(art["prior_base_sha"])
        self._assert_valid(art)

    # --- missing evidence ------------------------------------------------
    def test_missing_evidence_blocks(self):
        art = self._render(evidence_source="")
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertEqual("BASE_MISSING_EVIDENCE", art["reason_code"])
        self.assertEqual("REQUEST_HUMAN_INPUT", art["remediation"]["route"])
        self._assert_valid(art)

    # --- malformed input -------------------------------------------------
    def test_malformed_inputs_fail_closed(self):
        art = self._render(task_id="", repository="bad repo", protected_base_sha="xyz", evidence_source="x")
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertEqual("BASE_MALFORMED_INPUT", art["reason_code"])
        self.assertEqual("UNKNOWN", art["readback_status"])
        self.assertEqual("BLOCK_G0_REVIEW", art["remediation"]["route"])
        self._assert_valid(art)

    def test_malformed_verified_sha_blocks(self):
        art = self._render(verified_sha="not-a-sha")
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertEqual("BASE_MALFORMED_INPUT", art["reason_code"])
        self._assert_valid(art)

    # --- determinism / replay -------------------------------------------
    def test_replay_is_deterministic(self):
        a = self._render()
        b = self._render()
        self.assertEqual(a["decision_digest"], b["decision_digest"])
        c = self._render(verified_sha=BASE)
        d = self._render(verified_sha=BASE)
        self.assertEqual(c["decision_digest"], d["decision_digest"])

    # --- routing is total over the reason taxonomy ----------------------
    def test_routing_is_total_over_reason_taxonomy(self):
        self.assertEqual(set(M.REASONS), set(M.PRECEDENCE))
        for code in M.REASONS:
            if code == "BASE_CAPTURED":
                self.assertNotIn(code, M.ROUTING)
            else:
                self.assertIn(code, M.ROUTING)
                outcome, route = M.ROUTING[code]
                self.assertIn(outcome, {"BLOCKED", "PENDING", "HUMAN_REQUIRED"})
                self.assertTrue(M._stop_condition(route))

    # --- authority-negative ---------------------------------------------
    def test_no_route_grants_authority(self):
        cases = [
            self._render(),
            self._render(evidence_source=""),
            self._render(verified_sha=OTHER),
            self._render(prior_capture={"protected_base_sha": OTHER}),
        ]
        for art in cases:
            for f in M.AUTH_FIELDS:
                self.assertFalse(art[f])
            self._assert_valid(art)


class NeighborRegressionTests(unittest.TestCase):
    """intake_context.request-intake (SCRUM-298) must keep routing intact."""

    def test_request_intake_still_accepts_and_routes_to_source_resolution(self):
        art = NEIGHBOR.render_request_intake(
            task_id="SCRUM-298", repository=REPO, base_sha=BASE,
            request={"raw_text": "Implement protected-base-capture node", "source": "USER",
                     "provenance": {"actor": "hermes-pc"},
                     "task_binding": "SCRUM-301", "repository_intent": REPO,
                     "requested_outcome": "Typed protected-base-capture record"},
        )
        self.assertEqual("ACCEPTED", art["outcome"])
        self.assertIn("intake_context.source-resolution", art["next_allowed_nodes"])
        for f in NEIGHBOR.AUTH_FIELDS:
            self.assertFalse(art[f])


if __name__ == "__main__":
    unittest.main()
