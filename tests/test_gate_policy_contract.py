"""Focused tests for the generic Policy contract and evaluator (SCRUM-393).

Policy-only: no Flow files, resolver, or runtime-registry validator are touched.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / "tools/node_architect/evaluate_gate_applicability.py"
RUNTIME_SCHEMAS = ROOT / "schemas/runtime"
REGISTRY_PATH = ROOT / "core/node-architect/gate-applicability-policy-registry.json"
CANONICAL_GATES = [
    "G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR",
    "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA",
]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def schema_errors(instance, schema_name: str) -> list[str]:
    schema = json.loads((RUNTIME_SCHEMAS / schema_name).read_text(encoding="utf-8"))
    store = {}
    for candidate in RUNTIME_SCHEMAS.glob("*.schema.json"):
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        if payload.get("$id"):
            store[payload["$id"]] = payload
    resolver = RefResolver(schema.get("$id"), schema, store)
    return [e.message for e in Draft202012Validator(schema, resolver=resolver).iter_errors(instance)]


def flow_stub(registry_id: str) -> dict:
    return {
        "id": "policy-contract-test-flow",
        "policy_registry_ref": registry_id,
        "workflow": {
            "gate_bindings": [
                {"gate": "G0_CONTEXT", "policy_ref": "g0-context-required"},
                {"gate": "G1_ALIGNMENT", "policy_ref": "g1-alignment-required"},
                {"gate": "G2_EXECUTION", "policy_ref": "g2-execution-required"},
                {"gate": "G3_PR", "policy_ref": "g3-pr-required"},
                {"gate": "G4_MERGE", "policy_ref": "g4-merge-required"},
                {"gate": "G5_DEPLOY", "policy_ref": "g5-deploy-effect-driven"},
                {"gate": "G6_PRODUCTION_DATA", "policy_ref": "g6-production-effect-driven"},
            ]
        },
    }


class GatePolicyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module("gate_policy_contract_test", EVALUATOR)
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        cls.flow = flow_stub(cls.registry["registry_id"])

    def evaluate(self, gate: str, context: dict, *, registry=None, flow=None) -> dict:
        return self.mod.evaluate_gate_applicability(
            flow_profile=flow or self.flow,
            policy_registry=registry or self.registry,
            gate=gate,
            context=context,
        )

    # --- contract shape -------------------------------------------------
    def test_registry_is_schema_valid_and_independently_versioned(self) -> None:
        self.assertEqual(schema_errors(self.registry, "gate-applicability-policy-registry.schema.json"), [])
        self.assertEqual(self.registry["policy_contract_version"], "2.0.0")
        self.assertTrue(self.registry["tighten_only"])

    def test_every_canonical_gate_has_exactly_one_policy(self) -> None:
        ids = [p["id"] for p in self.registry["policies"]]
        self.assertEqual(len(ids), len(set(ids)))
        bound = {b["policy_ref"] for b in self.flow["workflow"]["gate_bindings"]}
        self.assertEqual(bound, set(ids))

    def test_policy_never_defines_node_ordering(self) -> None:
        forbidden = {"nodes", "edges", "entry_nodes", "terminal_nodes", "order", "next"}
        for policy in self.registry["policies"]:
            self.assertEqual(forbidden & set(policy), set())

    def test_decision_artifact_is_schema_valid_for_every_gate(self) -> None:
        for gate in CANONICAL_GATES:
            decision = self.evaluate(gate, {"effects": {}})
            self.assertEqual(schema_errors(decision, "gate-applicability-decision.schema.json"), [], gate)

    # --- decision states ------------------------------------------------
    def test_baseline_decisions_preserved(self) -> None:
        self.assertEqual(self.evaluate("G0_CONTEXT", {})["decision"], "REQUIRED")
        self.assertEqual(self.evaluate("G1_ALIGNMENT", {})["decision"], "REQUIRED")
        na = self.evaluate("G5_DEPLOY", {"effects": {}})
        self.assertEqual(na["decision"], "NOT_APPLICABLE")
        self.assertEqual(na["reason_code"], "GATE_NOT_APPLICABLE_BY_DEFAULT")
        self.assertEqual(
            self.evaluate("G5_DEPLOY", {"effects": {"manual_deploy_requested": True}})["decision"],
            "REQUIRED",
        )

    def test_not_applicable_is_explicit_evidence_never_implicit_pass(self) -> None:
        decision = self.evaluate("G6_PRODUCTION_DATA", {"effects": {}})
        self.assertEqual(decision["decision"], "NOT_APPLICABLE")
        self.assertNotIn("PASS", decision["reason_code"])
        self.assertTrue(decision["decision_digest"].startswith("sha256:"))
        self.assertTrue(decision["policy_digest"].startswith("sha256:"))

    def test_blocked_precedence_wins_over_required(self) -> None:
        decision = self.evaluate(
            "G5_DEPLOY", {"effects": {"manual_deploy_requested": True, "deploy_blocked": True}})
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertEqual(decision["matched_rule"], "deploy-blocked")

    # --- fail closed ----------------------------------------------------
    def test_non_canonical_gate_is_blocked(self) -> None:
        decision = self.evaluate("G7_INVENTED", {})
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertEqual(decision["reason_code"], "GATE_NOT_CANONICAL")

    def test_registry_binding_drift_blocks(self) -> None:
        drifted = deepcopy(self.flow)
        drifted["policy_registry_ref"] = "other-policy-registry"
        decision = self.evaluate("G5_DEPLOY", {"effects": {}}, flow=drifted)
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertEqual(decision["reason_code"], "POLICY_REGISTRY_BINDING_MISMATCH")

    def test_unknown_policy_ref_blocks(self) -> None:
        drifted = deepcopy(self.flow)
        drifted["workflow"]["gate_bindings"][3]["policy_ref"] = "does-not-exist"
        decision = self.evaluate("G3_PR", {}, flow=drifted)
        self.assertEqual(decision["reason_code"], "GATE_POLICY_MISSING")

    def test_ambiguous_binding_blocks(self) -> None:
        drifted = deepcopy(self.flow)
        drifted["workflow"]["gate_bindings"].append({"gate": "G3_PR", "policy_ref": "g3-pr-required"})
        self.assertEqual(self.evaluate("G3_PR", {}, flow=drifted)["reason_code"], "GATE_BINDING_AMBIGUOUS")

    def test_expired_policy_blocks_and_unknown_now_fails_closed(self) -> None:
        registry = deepcopy(self.registry)
        registry["policies"][3]["expires_at"] = "2020-01-01T00:00:00Z"
        expired = self.evaluate("G3_PR", {"now": "2026-08-11T00:00:00Z"}, registry=registry)
        self.assertEqual(expired["reason_code"], "POLICY_EXPIRED")
        unknown = self.evaluate("G3_PR", {}, registry=registry)
        self.assertEqual(unknown["reason_code"], "POLICY_FRESHNESS_UNKNOWN")

    # --- authority ------------------------------------------------------
    def test_authority_requirements_are_reported_not_granted(self) -> None:
        decision = self.evaluate("G4_MERGE", {})
        req = decision["authority_requirements"][0]
        self.assertFalse(req["satisfied"])
        self.assertEqual(req["reason_code"], "AUTHORITY_MISSING")
        self.assertEqual(decision["decision"], "REQUIRED")

    def test_authority_provider_binding_and_expiry_constraints(self) -> None:
        base = {
            "now": "2026-08-11T00:00:00Z",
            "authority": [{
                "authority_type": "merge_approval",
                "provider": "human",
                "issued_at": "2026-08-11T00:00:00Z",
                "bindings": {"head_sha": "abc", "target_branch": "pre-prod"},
            }],
        }
        ok = self.evaluate("G4_MERGE", base)["authority_requirements"][0]
        self.assertTrue(ok["satisfied"])

        bad_provider = deepcopy(base)
        bad_provider["authority"][0]["provider"] = "unknown-bot"
        self.assertEqual(
            self.evaluate("G4_MERGE", bad_provider)["authority_requirements"][0]["reason_code"],
            "AUTHORITY_PROVIDER_NOT_ALLOWED")

        missing_binding = deepcopy(base)
        missing_binding["authority"][0]["bindings"].pop("head_sha")
        self.assertEqual(
            self.evaluate("G4_MERGE", missing_binding)["authority_requirements"][0]["reason_code"],
            "AUTHORITY_BINDING_MISSING")

        stale = deepcopy(base)
        stale["authority"][0]["issued_at"] = "2026-08-01T00:00:00Z"
        self.assertEqual(
            self.evaluate("G4_MERGE", stale)["authority_requirements"][0]["reason_code"],
            "AUTHORITY_EXPIRED")

    def test_equivalence_only_accepted_when_declared(self) -> None:
        context = {
            "now": "2026-08-11T00:00:00Z",
            "authority": [{
                "authority_type": "derived_child_approval",
                "provider": "standing_authority",
                "issued_at": "2026-08-11T00:00:00Z",
                "bindings": {"scope_hash": "s", "base_sha": "b"},
            }],
        }
        self.assertTrue(self.evaluate("G2_EXECUTION", context)["authority_requirements"][0]["satisfied"])
        # G4 declares no equivalence -> the same substitute is not accepted.
        g4 = deepcopy(context)
        g4["authority"][0]["bindings"] = {"head_sha": "h", "target_branch": "pre-prod"}
        self.assertEqual(
            self.evaluate("G4_MERGE", g4)["authority_requirements"][0]["reason_code"],
            "AUTHORITY_MISSING")

    # --- evidence / prohibitions / terminal ------------------------------
    def test_evidence_acceptance_predicates(self) -> None:
        missing = self.evaluate("G3_PR", {})["evidence_requirements"][0]
        self.assertEqual(missing["reason_code"], "EVIDENCE_MISSING")
        rejected = self.evaluate(
            "G3_PR", {"evidence": [{"evidence_type": "diff_readback", "verified": False}]}
        )["evidence_requirements"][0]
        self.assertEqual(rejected["reason_code"], "EVIDENCE_NOT_ACCEPTED")
        accepted = self.evaluate(
            "G3_PR", {"evidence": [{"evidence_type": "diff_readback", "verified": True}]}
        )["evidence_requirements"][0]
        self.assertTrue(accepted["satisfied"])

    def test_prohibited_actions_are_machine_readable(self) -> None:
        self.assertIn("merge_without_approval", self.evaluate("G4_MERGE", {})["prohibited_actions"])
        self.assertIn("write_outside_declared_scope",
                      self.evaluate("G2_EXECUTION", {})["prohibited_actions"])

    def test_terminal_acceptance_is_separate_from_workflow_terminal_nodes(self) -> None:
        unmet = self.evaluate("G4_MERGE", {"pr": {"state": "OPEN"}})["terminal_acceptance"]
        self.assertFalse(unmet["accepted"])
        self.assertEqual(unmet["unmet"], ["merge-complete"])
        met = self.evaluate("G4_MERGE", {"pr": {"state": "MERGED"}})["terminal_acceptance"]
        self.assertTrue(met["accepted"])

    # --- tighten_only ----------------------------------------------------
    def test_tighten_only_blocks_weaker_decision(self) -> None:
        weak = deepcopy(self.registry)
        weak["policies"][0]["default"] = "NOT_APPLICABLE"
        decision = self.evaluate("G0_CONTEXT", {}, registry=weak)
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertEqual(decision["reason_code"], "POLICY_WEAKENS_CANONICAL_MINIMUM")

    def test_tighten_only_blocks_dropped_authority_evidence_prohibition(self) -> None:
        weak = deepcopy(self.registry)
        weak["policies"][4].pop("authority_requirements")
        self.assertEqual(self.evaluate("G4_MERGE", {}, registry=weak)["reason_code"],
                         "POLICY_WEAKENS_CANONICAL_AUTHORITY")
        weak2 = deepcopy(self.registry)
        weak2["policies"][3].pop("evidence_requirements")
        self.assertEqual(self.evaluate("G3_PR", {}, registry=weak2)["reason_code"],
                         "POLICY_WEAKENS_CANONICAL_EVIDENCE")
        weak3 = deepcopy(self.registry)
        weak3["policies"][4].pop("prohibited_actions")
        self.assertEqual(self.evaluate("G4_MERGE", {}, registry=weak3)["reason_code"],
                         "POLICY_WEAKENS_CANONICAL_PROHIBITIONS")

    def test_tightening_is_allowed(self) -> None:
        strict = deepcopy(self.registry)
        strict["policies"][5]["default"] = "REQUIRED"
        self.assertEqual(self.evaluate("G5_DEPLOY", {"effects": {}}, registry=strict)["decision"], "REQUIRED")

    # --- determinism / replay --------------------------------------------
    def test_same_bound_input_replays_identically(self) -> None:
        context = {"effects": {"release_requested": True}, "now": "2026-08-11T00:00:00Z"}
        first = self.evaluate("G5_DEPLOY", context)
        second = self.evaluate("G5_DEPLOY", deepcopy(context))
        self.assertEqual(first, second)
        self.assertEqual(first["decision_digest"], second["decision_digest"])

    def test_context_drift_changes_digest(self) -> None:
        a = self.evaluate("G5_DEPLOY", {"effects": {}})
        b = self.evaluate("G5_DEPLOY", {"effects": {"note": "changed"}})
        self.assertNotEqual(a["context_digest"], b["context_digest"])
        self.assertNotEqual(a["decision_digest"], b["decision_digest"])

    def test_policy_digest_is_independent_of_workflow(self) -> None:
        other_flow = deepcopy(self.flow)
        other_flow["id"] = "another-flow"
        a = self.evaluate("G5_DEPLOY", {"effects": {}})
        b = self.evaluate("G5_DEPLOY", {"effects": {}}, flow=other_flow)
        self.assertEqual(a["policy_digest"], b["policy_digest"])
        self.assertNotEqual(a["decision_digest"], b["decision_digest"])

    def test_provenance_is_emitted(self) -> None:
        provenance = self.evaluate("G0_CONTEXT", {})["provenance"]
        self.assertEqual(provenance["evaluator"], "evaluate_gate_applicability")
        self.assertEqual(provenance["policy_contract_version"], "2.0.0")
        self.assertTrue(provenance["tighten_only"])


if __name__ == "__main__":
    unittest.main()
