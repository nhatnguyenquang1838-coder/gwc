import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.node_architect.universal_run_gate_adapter import (  # noqa: E402
    accept_parent_g6,
    handle_gate,
)


class UniversalRunGateAdapterTests(unittest.TestCase):
    def test_generic_gate_namespace_routes_without_effect_gate_alias(self):
        target = {"run_id": "child-1"}
        result = handle_gate(gate="UR.G4", action="INTEGRATE", run_id="child-1",
                             manifest={"run_id": "child-1", "run_kind": "CHILD", "parent_run_ref": "parent"},
                             target_contract=target)
        self.assertEqual(result["status"], "ROUTE_SELECTED")
        self.assertEqual(result["gate"], "UR.G4")
        self.assertNotIn("G4_MERGE", result.values())

    def test_parent_g6_rejects_caller_status_receipts_and_requires_persisted_children(self):
        contract = {"schema_version": "1.0", "run_id": "parent", "target_id": "staging-a",
                    "required_children": ["child-1"]}
        result = accept_parent_g6(parent_run_id="parent", target_contract=contract)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason_code"], "PERSISTED_CHILD_RECEIPTS_REQUIRED")
        self.assertFalse(result["authority_granted"])

    def test_parent_g6_accepts_target_contract_without_c2_authority_for_empty_child_set(self):
        contract = {"schema_version": "1.0", "run_id": "parent", "target_id": "staging-a",
                    "required_children": []}
        result = accept_parent_g6(parent_run_id="parent", target_contract=contract)
        self.assertEqual(result["status"], "ACCEPTED")
        self.assertTrue(result["parent_receipt"]["target_contract_digest"].startswith("sha256:"))
        self.assertEqual(len(result["parent_receipt"]["target_contract_digest"]), 71)
        self.assertFalse(result["authority_granted"])
        self.assertEqual(result["accepted_child_run_ids"], [])

    def test_parent_g6_accepts_only_persisted_child_gate_receipts_and_readbacks(self):
        contract = {"schema_version": "1.0", "run_id": "parent", "target_id": "staging-a",
                    "required_children": ["child-1"]}
        from tools.node_architect.checkpoint_store import digest_payload
        state = {"run_receipts": {"child-1": {"run_id": "child-1", "status": "COMPLETED",
                  "g6_receipt": {"status": "ACCEPTED", "receipt_id": "child-g6"}}},
                 "child_manifests": {"child-1": {"run_id": "child-1", "parent_run_ref": "parent"}},
                 "target_contracts": {"child-1": {"schema_version": "1.0", "run_id": "child-1",
                                                    "target_id": "staging-a", "required_children": []}},
                 "gates": {"child-1": {
                     "G3": {"evidence": {"status": "verified"}},
                     "G4": {"target_readback": {"status": "VERIFIED"}},
                     "G5": {"target_readback": {"status": "VERIFIED"}},
                 }}}
        record = {"node_id": "recursive-dag:1:parent:receipt", "state": state,
                  "state_digest": digest_payload(state)}
        store = {**state, "revision": 1, "binding": {}, "lease_binding": {}, "events": [],
                 "checkpoints": {"checkpoint-1": record}, "effects": {}}
        store["store_digest"] = digest_payload({key: store[key] for key in (
            "revision", "binding", "lease_binding", "events", "checkpoints", "effects")})
        result = accept_parent_g6(parent_run_id="parent", target_contract=contract,
                                  internal_store=store, receipts_persisted=True)
        self.assertEqual(result["status"], "ACCEPTED")
        self.assertEqual(result["accepted_child_run_ids"], ["child-1"])
        self.assertFalse(result["authority_granted"])

    def test_parent_g6_rejects_target_contract_mismatch(self):
        result = accept_parent_g6(parent_run_id="parent", target_contract={"run_id": "other", "target_id": "x",
                                                                            "required_children": []})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason_code"], "TARGET_CONTRACT_INVALID")

    def test_all_generic_lifecycle_gates_have_distinct_target_neutral_actions(self):
        expected = {
            "UR.G0": "UNDERSTAND", "UR.G1": "PLAN", "UR.G2": "EXECUTE",
            "UR.G3": "VERIFY", "UR.G4": "INTEGRATE",
            "UR.G5": "VALIDATE-IN-TARGET", "UR.G6": "ACCEPT/HANDOFF",
        }
        for gate, action in expected.items():
            with self.subTest(gate=gate):
                result = handle_gate(
                    gate=gate, action=action, run_id="child-1",
                    manifest={"run_id": "child-1", "run_kind": "CHILD", "parent_run_ref": "parent"},
                    target_contract={"schema_version": "1.0", "run_id": "child-1", "target_id": "target", "required_children": []},
                )
                if gate == "UR.G2":
                    self.assertEqual(result["status"], "EFFECT_HOLD")
                    self.assertEqual(result["reason_code"], "AUTHORITY_TRUST_ANCHOR_UNAVAILABLE")
                elif gate == "UR.G6":
                    self.assertEqual(result["status"], "ACCEPTED")
                    self.assertFalse(result["authority_granted"])
                else:
                    self.assertEqual(result["status"], "ROUTE_SELECTED")
                self.assertNotIn(gate.replace("UR.", "G"), {"G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA"})

    def test_parent_g6_accepts_valid_target_contract_without_c2_trust(self):
        result = accept_parent_g6(parent_run_id="parent", target_contract={"schema_version": "1.0", "run_id": "parent", "target_id": "x",
                                                                           "required_children": []})
        self.assertEqual(result["status"], "ACCEPTED")
        self.assertFalse(result["authority_granted"])

    def test_ur_g2_holds_when_parent_grant_trust_anchor_unavailable(self):
        result = handle_gate(gate="UR.G2", action="EXECUTE", run_id="child-1",
                             manifest={"run_id": "child-1", "run_kind": "CHILD", "parent_run_ref": "parent"},
                             target_contract={"schema_version": "1.0", "run_id": "child-1", "target_id": "target", "required_children": []}, authority={"derived_receipt": {"digest": "x"}})
        self.assertEqual(result["status"], "EFFECT_HOLD")
        self.assertEqual(result["reason_code"], "AUTHORITY_TRUST_ANCHOR_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
