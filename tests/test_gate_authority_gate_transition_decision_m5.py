"""M5 tests for replay-safe gate transition decisions (SCRUM-190)."""
from __future__ import annotations

import copy
import unittest

from tools.node_architect.gate_transition_decision import decide_gate_transition

_SCOPE = "sha256:" + "a" * 64


def _gsr():
    return {
        "current_gate": "G2",
        "current_state": "G1_ALIGNED",
        "expected_transition": "G1->G2",
        "expected_state": "G2_EXECUTABLE",
        "next_gate": "G2",
        "next_node": "hermes/scrum-x",
    }


def _base(evidence_flags=None, observed=None, approval=None, envelope=None,
          prior=None, event="evt-1"):
    return dict(
        task_id="SCRUM-190",
        repository="nhatnguyenquang1838-coder/gwc",
        gate_state_resolution=_gsr(),
        evidence_map={"flags": evidence_flags or [], "refs": ["ref1"]},
        authority_boundary_decision={"excluded": ["G4_MERGE"]},
        approval_validation=approval,
        g2_execution_envelope=envelope,
        observed_task_state=observed,
        event_id_or_idempotency_key=event,
        prior_decision=prior,
    )


class TestDecisions(unittest.TestCase):
    def test_pass_when_readback_matches(self):
        d = decide_gate_transition(**_base(observed="G1_ALIGNED", approval={"outcome": "VALID"}))
        self.assertEqual(d["decision"], "PASS")
        self.assertEqual(d["reason_code"], "TRANSITION_PASS")

    def test_awaiting_when_no_approval(self):
        d = decide_gate_transition(**_base(approval=None))
        self.assertEqual(d["decision"], "AWAITING_APPROVAL")
        self.assertEqual(d["reason_code"], "TRANSITION_APPROVAL_REQUIRED")
        self.assertTrue(d["requires_human_approval"])

    def test_continue_when_readback_pending(self):
        d = decide_gate_transition(**_base(observed=None, approval={"outcome": "VALID"}))
        self.assertEqual(d["decision"], "CONTINUE")
        self.assertEqual(d["reason_code"], "TRANSITION_READBACK_REQUIRED")
        self.assertTrue(d["readback_required"])
        self.assertTrue(d["checkpoint_required"])

    def test_block_when_readback_mismatch(self):
        d = decide_gate_transition(**_base(observed="OTHER_STATE", approval={"outcome": "VALID"}))
        self.assertEqual(d["decision"], "BLOCK")
        self.assertEqual(d["reason_code"], "TRANSITION_READBACK_MISMATCH")

    def test_block_when_evidence_missing_flag(self):
        d = decide_gate_transition(**_base(evidence_flags=["TRANSITION_EVIDENCE_MISSING"]))
        self.assertEqual(d["decision"], "BLOCK")
        self.assertEqual(d["reason_code"], "TRANSITION_EVIDENCE_MISSING")

    def test_block_when_envelope_inactive(self):
        env = {"activation_state": "AWAITING_APPROVAL"}
        d = decide_gate_transition(**_base(approval={"outcome": "VALID"}, envelope=env,
                                             observed="G1_ALIGNED"))
        self.assertEqual(d["decision"], "BLOCK")
        self.assertEqual(d["reason_code"], "TRANSITION_ENVELOPE_INACTIVE")

    def test_not_applicable_gate(self):
        gsr = _gsr()
        gsr["current_gate"] = "G6"
        gsr["current_state"] = "NO_PROD_CHANGE"
        d = decide_gate_transition(
            task_id="SCRUM-190", repository="nhatnguyenquang1838-coder/gwc",
            gate_state_resolution=gsr, evidence_map={"flags": [], "refs": []},
            authority_boundary_decision={"excluded": ["G6_PRODUCTION"]},
            approval_validation={"outcome": "VALID"}, g2_execution_envelope=None,
            observed_task_state="NO_PROD_CHANGE",
            event_id_or_idempotency_key="evt-g6")
        self.assertIn(d["decision"], ("PASS", "NOT_APPLICABLE"))

    def test_replay_conflict(self):
        prior = {"event_id_or_idempotency_key": "evt-1", "decision": "PASS"}
        d = decide_gate_transition(**_base(observed="G1_ALIGNED", prior=prior))
        self.assertEqual(d["replay_status"], "CONFLICT")
        self.assertEqual(d["decision"], "BLOCK")
        self.assertEqual(d["reason_code"], "TRANSITION_REPLAY_CONFLICT")

    def test_replay_idempotent(self):
        prior = {"event_id_or_idempotency_key": "evt-1", "decision": "PASS"}
        d = decide_gate_transition(**_base(observed="G1_ALIGNED", prior=prior, event="evt-2"))
        self.assertEqual(d["replay_status"], "IDEMPOTENT")

    def test_no_execution_side_effect(self):
        d = decide_gate_transition(**_base(observed="G1_ALIGNED"))
        self.assertEqual(d["execution_performed"], False)
        self.assertNotIn("transition_result", d)


if __name__ == "__main__":
    unittest.main()
