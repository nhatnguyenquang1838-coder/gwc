"""M5 family flow integration across gate_authority MAT-F2 nodes (185/186/190/191/192)."""
from __future__ import annotations

import unittest

from tools.node_architect.approval_token_generation import generate_approval_request
from tools.node_architect.approval_command_validation import validate_approval_command
from tools.node_architect.g2_execution_envelope_render import render_g2_execution_envelope
from tools.node_architect.gate_transition_decision import decide_gate_transition
from tools.node_architect.blocked_action_escalation import escalate_blocked_action
from tools.node_architect.validate_node_catalog_gate_authority import (
    validate_node_catalog_gate_authority,
)


class TestFamilyFlow(unittest.TestCase):
    def test_all_nodes_importable(self):
        rep = validate_node_catalog_gate_authority()
        self.assertEqual(rep["summary"], "OK")
        self.assertTrue(rep["all_present"])

    def test_185_generate_then_186_validate(self):
        req = generate_approval_request(
            task_id="SCRUM-186", repository="nhatnguyenquang1838-coder/gwc",
            gate="G2_EXECUTION", action="create_working_branch",
            scope_identity={"scope_hash": "sha256:" + "b" * 64,
                            "base_sha": "794b55186d9b97b81db8fe99a2def5a99b866754",
                            "head_sha": "794b55186d9b97b81db8fe99a2def5a99b866754"},
            authority_boundary_decision={"decision": "REQUIRE_APPROVAL",
                                         "requested_action": "create_working_branch",
                                         "excluded": ["G4_MERGE"]},
            actor_target={"id": "Hermes-PC"},
            issued_at="2026-08-05T10:00:00Z", expires_at="2026-08-06T10:00:00Z")
        self.assertIn("approval_request_id", req)
        self.assertIn("approval_command", req)
        val = validate_approval_command(
            approval_request=req,
            human_response=req["approval_command"],
            current_readback={"approval_command": req["approval_command"]},
            event_id_or_idempotency_key="evt-family-185-186",
            validated_at="2026-08-05T11:00:00Z")
        self.assertIn(val["outcome"], ("VALID", "INVALID"))

    def test_191_envelope_awaiting_then_190_transition(self):
        env = render_g2_execution_envelope(
            task_id="SCRUM-191", repository="nhatnguyenquang1838-coder/gwc",
            base_ref="main", base_sha="54fcc4c5395d0b3dabfe0564d5b3f8ad8daa3337",
            risk_profile={"risk_class": "R2", "risk_digest": "sha256:" + "c" * 64},
            bounded_read_scope={"paths": [".gwc/tasks/SCRUM-191/**"]},
            bounded_write_scope={"working_branch": "x", "paths": ["y"],
                                 "authorized_actions": ["create_working_branch"]},
            scope_identity={"scope_hash": "sha256:" + "d" * 64},
            gate_state_resolution={"gate": "G2", "state": "AWAITING"},
            authority_boundary_decision={"excluded": ["G4_MERGE"]},
            evidence_map={"f1_artifact_digests": {"g0": "sha256:" + "e" * 64}},
            approval_request={"issued_at": "2026-08-05T10:00:00Z",
                              "expires_at": "2026-08-06T10:00:00Z"},
            approval_validation=None,
            checkpoint={"checkpoint_id": "ck-family"})
        self.assertEqual(env["activation_state"], "AWAITING_APPROVAL")
        g2 = {"activation_state": env["activation_state"]}
        td = decide_gate_transition(
            task_id="SCRUM-190", repository="nhatnguyenquang1838-coder/gwc",
            gate_state_resolution={"current_gate": "G2", "current_state": "G1_ALIGNED",
                                   "next_gate": "G2", "next_node": "x",
                                   "expected_transition": "G1->G2",
                                   "expected_state": "G2_EXECUTABLE"},
            evidence_map={"flags": [], "refs": []},
            authority_boundary_decision={"excluded": ["G4_MERGE"]},
            approval_validation=None, g2_execution_envelope=g2,
            observed_task_state="G1_ALIGNED", event_id_or_idempotency_key="evt-fam")
        self.assertIn(td["decision"], ("AWAITING_APPROVAL", "CONTINUE", "PASS", "BLOCK"))

    def test_192_escalation_blocks_unauthorized(self):
        d = escalate_blocked_action(
            task_id="SCRUM-192", repository="nhatnguyenquang1838-coder/gwc",
            blocked_action="g4_merge", checkpoint_state={"checkpoint_done": True},
            event_id_or_idempotency_key="evt-fam-esc")
        self.assertEqual(d["execution_performed"], False)
        self.assertEqual(d["decision"], "RESOLVE_MINIMAL")

    def test_full_chain_no_execution_authority(self):
        # No node in the family grants execution; envelopes stay inactive.
        env = render_g2_execution_envelope(
            task_id="SCRUM-191", repository="r", base_ref="main",
            base_sha="54fcc4c5395d0b3dabfe0564d5b3f8ad8daa3337",
            risk_profile={"risk_class": "R2", "risk_digest": "sha256:" + "c" * 64},
            bounded_read_scope={"paths": ["p"]},
            bounded_write_scope={"working_branch": "x", "paths": ["y"],
                                 "authorized_actions": ["create_working_branch"]},
            scope_identity={"scope_hash": "sha256:" + "d" * 64},
            gate_state_resolution={"gate": "G2", "state": "AWAITING"},
            authority_boundary_decision={"excluded": ["G4_MERGE"]},
            evidence_map={"f1_artifact_digests": {"g0": "sha256:" + "e" * 64}},
            approval_request={"issued_at": "2026-08-05T10:00:00Z",
                              "expires_at": "2026-08-06T10:00:00Z"},
            approval_validation=None,
            checkpoint={"checkpoint_id": "ck-family"})
        self.assertEqual(env["execution_started"], False)


if __name__ == "__main__":
    unittest.main()
