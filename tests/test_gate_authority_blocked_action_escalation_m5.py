"""M5 tests for replay-safe blocked-action escalation (SCRUM-192)."""
from __future__ import annotations

import copy
import unittest

from tools.node_architect.blocked_action_escalation import (
    escalate_blocked_action,
    _BLOCKED_ACTIONS,
)


def _base(checkpoint_done=True, action="merge", prior=None, event="evt-1"):
    return dict(
        task_id="SCRUM-192",
        repository="nhatnguyenquang1838-coder/gwc",
        blocked_action=action,
        checkpoint_state={"checkpoint_done": checkpoint_done},
        prior_escalation=prior,
        event_id_or_idempotency_key=event,
    )


class TestEscalation(unittest.TestCase):
    def test_wait_when_checkpoint_pending(self):
        d = escalate_blocked_action(**_base(checkpoint_done=False))
        self.assertEqual(d["decision"], "WAIT")
        self.assertEqual(d["reason_code"], "ESCALATION_CHECKPOINT_REQUIRED")
        self.assertTrue(d["checkpoint_required"])
        self.assertIsNone(d["remediation_scope"])

    def test_resolve_minimal_when_checkpoint_done(self):
        d = escalate_blocked_action(**_base(checkpoint_done=True))
        self.assertEqual(d["decision"], "RESOLVE_MINIMAL")
        self.assertEqual(d["reason_code"], "ESCALATION_CHECKPOINT_PASSED")
        self.assertFalse(d["checkpoint_required"])
        self.assertEqual(d["remediation_scope"], "minimal-exact:merge")

    def test_replay_idempotent(self):
        d = escalate_blocked_action(**_base(checkpoint_done=True, event="evt-2"))
        self.assertEqual(d["replay_status"], "IDEMPOTENT")

    def test_replay_conflict(self):
        prior = {"event_id_or_idempotency_key": "evt-1"}
        d = escalate_blocked_action(**_base(checkpoint_done=True, prior=prior))
        self.assertEqual(d["replay_status"], "CONFLICT")

    def test_no_unauthorized_continuation(self):
        # blocked action is never executed; decision never performs it.
        d = escalate_blocked_action(**_base(checkpoint_done=True))
        self.assertEqual(d["execution_performed"], False)
        self.assertIn(d["blocked_action"], _BLOCKED_ACTIONS)

    def test_all_blocked_actions_known(self):
        for a in ["open_draft_pr", "mark_pr_ready", "merge", "g4_merge",
                  "deploy", "g6_production"]:
            self.assertIn(a, _BLOCKED_ACTIONS)

    def test_deterministic_digest(self):
        a = escalate_blocked_action(**_base())
        b = escalate_blocked_action(**_base())
        self.assertEqual(a["escalation_digest"], b["escalation_digest"])

    def test_invalid_action_rejected(self):
        with self.assertRaises(ValueError):
            escalate_blocked_action(**_base(action="not_a_blocked_action"))

    def test_digest_format(self):
        d = escalate_blocked_action(**_base())
        self.assertRegex(d["escalation_digest"], r"^sha256:[0-9a-f]{64}$")

    def test_minimal_remediation_exact(self):
        d = escalate_blocked_action(**_base(action="deploy", checkpoint_done=True))
        self.assertEqual(d["remediation_scope"], "minimal-exact:deploy")
        self.assertNotIn("broad", d["remediation_scope"])


if __name__ == "__main__":
    unittest.main()
