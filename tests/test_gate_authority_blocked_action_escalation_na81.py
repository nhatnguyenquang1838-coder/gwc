"""SCRUM-315 (current NA81) tests: deterministic BLOCKED/HUMAN_REQUIRED escalation.

Covers the current-task requirement->code->test mapping on exact SHA. Historical
SCRUM-192 (M5) tests are retained separately; this file proves the NA81 maturity
delta: unauthorized/stale/expired/unsupported/unknown-evidence routing, zero
protected side effects, no approval manufacture, no scope broadening, replay
determinism and terminal/human-required routes.
"""
from __future__ import annotations

import copy
import unittest

from tools.node_architect.blocked_action_escalation import (
    escalate_blocked_action,
    _BLOCKED_ACTIONS,
    DECISION_BLOCKED,
    DECISION_HUMAN_REQUIRED,
    DECISION_WAIT,
    DECISION_RESOLVE_MINIMAL,
    ESC_REMEDIATE_EVIDENCE,
    ESC_TERMINAL_STOP,
    ESC_REQUEST_HUMAN_INPUT,
    ESC_RECAPTURE_BASE_OR_HEAD,
    ESC_REVALIDATE_SCOPE,
    ESC_WAIT_FOR_READBACK,
    ESC_WAIT_FOR_CI,
)


def _base(**over):
    d = dict(
        task_id="SCRUM-315",
        repository="nhatnguyenquang1838-coder/gwc",
        blocked_action="merge",
        authority_check="OK",
        evidence_available=True,
        checkpoint_state={"checkpoint_done": True},
        prior_escalation=None,
        event_id_or_idempotency_key="evt-1",
    )
    d.update(over)
    return d


class TestFailClosedEvidence(unittest.TestCase):
    def test_unknown_evidence_fails_closed(self):
        d = escalate_blocked_action(**_base(evidence_available=False, authority_check="OK"))
        self.assertEqual(d["decision"], DECISION_BLOCKED)
        self.assertEqual(d["reason_code"], "ESCALATION_EVIDENCE_UNAVAILABLE")
        self.assertEqual(d["escalation_class"], ESC_REMEDIATE_EVIDENCE)
        self.assertIsNone(d["remediation_scope"])
        self.assertFalse(d["execution_performed"])

    def test_unknown_authority_fails_closed(self):
        d = escalate_blocked_action(**_base(authority_check="UNKNOWN"))
        self.assertEqual(d["decision"], DECISION_BLOCKED)
        self.assertEqual(d["escalation_class"], ESC_REMEDIATE_EVIDENCE)


class TestClassifiedRoutes(unittest.TestCase):
    def test_unsupported_terminal_stop(self):
        d = escalate_blocked_action(**_base(authority_check="UNSUPPORTED"))
        self.assertEqual(d["decision"], DECISION_BLOCKED)
        self.assertEqual(d["escalation_class"], ESC_TERMINAL_STOP)
        self.assertIsNone(d["remediation_scope"])

    def test_unauthorized_human_required(self):
        d = escalate_blocked_action(**_base(authority_check="UNAUTHORIZED"))
        self.assertEqual(d["decision"], DECISION_HUMAN_REQUIRED)
        self.assertEqual(d["escalation_class"], ESC_REQUEST_HUMAN_INPUT)
        self.assertFalse(d["execution_performed"])

    def test_stale_recapture(self):
        d = escalate_blocked_action(**_base(authority_check="STALE"))
        self.assertEqual(d["decision"], DECISION_BLOCKED)
        self.assertEqual(d["escalation_class"], ESC_RECAPTURE_BASE_OR_HEAD)

    def test_expired_revalidate_scope(self):
        d = escalate_blocked_action(**_base(authority_check="EXPIRED"))
        self.assertEqual(d["decision"], DECISION_HUMAN_REQUIRED)
        self.assertEqual(d["escalation_class"], ESC_REVALIDATE_SCOPE)


class TestNoApprovalNoBroaden(unittest.TestCase):
    def test_execution_never_performed(self):
        for ac in ["UNSUPPORTED", "UNAUTHORIZED", "STALE", "EXPIRED", "UNKNOWN", "OK"]:
            d = escalate_blocked_action(**_base(authority_check=ac))
            self.assertFalse(d["execution_performed"], ac)
            self.assertIn(d["blocked_action"], _BLOCKED_ACTIONS)

    def test_no_approval_manufactured(self):
        # a HUMAN_REQUIRED decision never carries an auto-granted remediation scope
        d = escalate_blocked_action(**_base(authority_check="UNAUTHORIZED"))
        self.assertEqual(d["decision"], DECISION_HUMAN_REQUIRED)
        self.assertIsNone(d["remediation_scope"])

    def test_no_scope_broadening(self):
        d = escalate_blocked_action(**_base(blocked_action="deploy", authority_check="OK"))
        self.assertEqual(d["remediation_scope"], "minimal-exact:deploy")
        self.assertNotIn("broad", d["remediation_scope"])


class TestCheckpointGate(unittest.TestCase):
    def test_wait_when_checkpoint_pending(self):
        d = escalate_blocked_action(**_base(checkpoint_state={"checkpoint_done": False}))
        self.assertEqual(d["decision"], DECISION_WAIT)
        self.assertEqual(d["escalation_class"], ESC_WAIT_FOR_READBACK)
        self.assertTrue(d["checkpoint_required"])

    def test_resolve_minimal_when_checkpoint_done(self):
        d = escalate_blocked_action(**_base())
        self.assertEqual(d["decision"], DECISION_RESOLVE_MINIMAL)
        self.assertEqual(d["escalation_class"], ESC_WAIT_FOR_CI)
        self.assertEqual(d["remediation_scope"], "minimal-exact:merge")


class TestReplayDeterminism(unittest.TestCase):
    def test_replay_idempotent(self):
        d = escalate_blocked_action(**_base(event_id_or_idempotency_key="evt-2"))
        self.assertEqual(d["replay_status"], "IDEMPOTENT")

    def test_replay_conflict(self):
        prior = {"event_id_or_idempotency_key": "evt-1"}
        d = escalate_blocked_action(**_base(prior_escalation=prior))
        self.assertEqual(d["replay_status"], "CONFLICT")

    def test_deterministic_digest(self):
        a = escalate_blocked_action(**_base())
        b = escalate_blocked_action(**_base())
        self.assertEqual(a["escalation_digest"], b["escalation_digest"])

    def test_digest_format(self):
        d = escalate_blocked_action(**_base())
        self.assertRegex(d["escalation_digest"], r"^sha256:[0-9a-f]{64}$")


class TestInputs(unittest.TestCase):
    def test_invalid_action_rejected(self):
        with self.assertRaises(ValueError):
            escalate_blocked_action(**_base(blocked_action="not_a_blocked_action"))

    def test_invalid_authority_rejected(self):
        with self.assertRaises(ValueError):
            escalate_blocked_action(**_base(authority_check="NONSENSE"))

    def test_all_blocked_actions_known(self):
        for a in ["open_draft_pr", "mark_pr_ready", "merge", "g4_merge",
                  "deploy", "g6_production"]:
            self.assertIn(a, _BLOCKED_ACTIONS)


if __name__ == "__main__":
    unittest.main()
