import unittest

from tools.node_architect.human_takeover_packet import (
    TakeoverDecision,
    build_human_takeover_packet,
)


class HumanTakeoverPacketTests(unittest.TestCase):
    def packet(self, **overrides):
        data = {
            "task_id": "SCRUM-110",
            "run_id": "run-1",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "base_sha": "53b23f38cf7412fffd8bc1adce8c3d6b8277b1b6",
            "scope_hash": "sha256:" + "a" * 64,
            "graph_revision": "scrum-106-p2-scenario-matrix-r2",
            "node_id": "bounded-external-write",
            "scenario_id": "P2-BW-HUMAN_TAKEOVER",
            "boundary": "B4",
            "checkpoint_revision": 3,
            "fencing_token": 7,
            "lease_owner": "worker-b",
            "idempotency_key": "run-1:effect",
            "pending_action": "operator_decision",
            "attempts": ({"worker": "worker-a", "result": "timeout"},),
            "missing_facts": ("live effect count",),
            "evidence": ("intent#1", "checkpoint#3"),
            "allowed_decisions": (
                TakeoverDecision.REOBSERVE_EXACT_STATE,
                TakeoverDecision.ABORT,
            ),
        }
        data.update(overrides)
        return build_human_takeover_packet(**data)

    def test_packet_contains_exact_binding_and_bounded_decisions(self):
        payload = self.packet().as_dict()
        self.assertEqual(
            payload["base_sha"],
            "53b23f38cf7412fffd8bc1adce8c3d6b8277b1b6",
        )
        self.assertIn("blind_repeat_dispatch", payload["prohibited_actions"])
        self.assertEqual(
            payload["allowed_decisions"],
            ["reobserve_exact_state", "abort"],
        )

    def test_missing_ambiguity_facts_is_invalid(self):
        with self.assertRaises(ValueError):
            self.packet(missing_facts=())

    def test_scope_hash_is_exactly_validated(self):
        with self.assertRaises(ValueError):
            self.packet(scope_hash="bad")


if __name__ == "__main__":
    unittest.main()
