from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, RefResolver


ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / "tools/node_architect/evaluate_gate_applicability.py"
RESOLVER = ROOT / "tools/node_architect/resolve_gate_node_route.py"
REGISTRY_VALIDATOR = ROOT / "tools/node_architect/validate_runtime_registry.py"
RUNTIME_SCHEMAS = ROOT / "schemas/runtime"
CANONICAL_GATES = {
    "G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR",
    "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA",
}


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
    return [error.message for error in Draft202012Validator(schema, resolver=resolver).iter_errors(instance)]


class WorkflowProfileGateApplicabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evaluator = load_module("workflow_gate_applicability_test", EVALUATOR)
        cls.resolver = load_module("workflow_gate_route_resolver_test", RESOLVER)
        cls.profile_registry = json.loads(
            (ROOT / "core/node-architect/profile-registry.json").read_text(encoding="utf-8")
        )
        cls.flow_profile = cls.profile_registry["profiles"][0]
        cls.policy_registry = json.loads(
            (ROOT / "core/node-architect/gate-applicability-policy-registry.json").read_text(encoding="utf-8")
        )
        cls.route_profile = json.loads(
            (ROOT / "core/node-architect/gate-node-route-profile.json").read_text(encoding="utf-8")
        )
        cls.node_registry = json.loads(
            (ROOT / "core/node-architect/node-registry.json").read_text(encoding="utf-8")
        )

    def evaluate(self, gate: str, context: dict) -> dict:
        return self.evaluator.evaluate_gate_applicability(
            flow_profile=self.flow_profile,
            policy_registry=self.policy_registry,
            gate=gate,
            context=context,
        )

    def test_runtime_registry_accepts_workflow_profile_v2(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REGISTRY_VALIDATOR), "--root", str(ROOT)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["outcome"], "PASS")
        self.assertEqual(report["counts"]["nodes"], 81)

    def test_workflow_contract_reuses_existing_nodes_only(self) -> None:
        workflow = self.flow_profile["workflow"]
        node_ids = {node["id"] for node in self.node_registry["nodes"]}
        referenced = set(workflow["entry_nodes"])
        referenced.update(item["node"] for item in workflow["terminal_nodes"])
        for edge in workflow["edges"]:
            referenced.add(edge["source"])
            referenced.add(edge["target"])
        self.assertLessEqual(referenced, node_ids)
        self.assertEqual(len(self.node_registry["nodes"]), 81)

    def test_workflow_binds_all_fixed_gates_without_embedding_policy_rules(self) -> None:
        bindings = self.flow_profile["workflow"]["gate_bindings"]
        self.assertEqual({item["gate"] for item in bindings}, CANONICAL_GATES)
        self.assertEqual(len(bindings), len(CANONICAL_GATES))
        for binding in bindings:
            self.assertEqual(set(binding), {"gate", "policy_ref"})

    def test_policy_registry_is_separate_schema_valid_and_fully_referenced(self) -> None:
        self.assertEqual(
            self.flow_profile["policy_registry_ref"],
            self.policy_registry["registry_id"],
        )
        self.assertEqual(schema_errors(self.policy_registry, "gate-applicability-policy-registry.schema.json"), [])
        policy_ids = [item["id"] for item in self.policy_registry["policies"]]
        self.assertEqual(len(policy_ids), len(set(policy_ids)))
        self.assertEqual(
            {item["policy_ref"] for item in self.flow_profile["workflow"]["gate_bindings"]},
            set(policy_ids),
        )

    def test_g0_and_g1_are_required_by_fixed_policy(self) -> None:
        self.assertEqual(self.evaluate("G0_CONTEXT", {})["decision"], "REQUIRED")
        self.assertEqual(self.evaluate("G1_ALIGNMENT", {})["decision"], "REQUIRED")

    def test_g5_is_not_applicable_without_deploy_effect(self) -> None:
        decision = self.evaluate("G5_DEPLOY", {"effects": {}})
        self.assertEqual(decision["decision"], "NOT_APPLICABLE")
        self.assertEqual(decision["reason_code"], "GATE_NOT_APPLICABLE_BY_DEFAULT")
        self.assertEqual(schema_errors(decision, "gate-applicability-decision.schema.json"), [])

    def test_g5_is_required_when_manual_deploy_requested(self) -> None:
        decision = self.evaluate(
            "G5_DEPLOY", {"effects": {"manual_deploy_requested": True}},
        )
        self.assertEqual(decision["decision"], "REQUIRED")
        self.assertEqual(decision["matched_rule"], "manual-deploy")

    def test_blocked_precedence_wins_over_required(self) -> None:
        decision = self.evaluate(
            "G5_DEPLOY",
            {"effects": {"manual_deploy_requested": True, "deploy_blocked": True}},
        )
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertEqual(decision["matched_rule"], "deploy-blocked")

    def test_g6_production_data_is_effect_driven(self) -> None:
        no_effect = self.evaluate("G6_PRODUCTION_DATA", {"effects": {}})
        production = self.evaluate(
            "G6_PRODUCTION_DATA", {"effects": {"production_config_change": True}},
        )
        self.assertEqual(no_effect["decision"], "NOT_APPLICABLE")
        self.assertEqual(production["decision"], "REQUIRED")

    def test_resolver_auto_loads_bound_flow_and_skips_not_applicable_gate(self) -> None:
        result = self.resolver.resolve_next_gate_applicability(
            route_profile=self.route_profile,
            flow_profile=None,
            next_gate="G5_DEPLOY",
            context={"effects": {}},
            root=ROOT,
        )
        self.assertEqual(result["outcome"], "PASS")
        self.assertIsNone(result["next_gate"])
        self.assertEqual(result["reason_code"], "NEXT_GATE_NOT_APPLICABLE")
        self.assertEqual(result["decision"]["policy_ref"], "g5-deploy-effect-driven")

    def test_resolver_keeps_required_next_gate(self) -> None:
        result = self.resolver.resolve_next_gate_applicability(
            route_profile=self.route_profile,
            flow_profile=None,
            next_gate="G5_DEPLOY",
            context={"effects": {"release_requested": True}},
            root=ROOT,
        )
        self.assertEqual(result["outcome"], "PASS")
        self.assertEqual(result["next_gate"], "G5_DEPLOY")
        self.assertEqual(result["reason_code"], "NEXT_GATE_REQUIRED")

    def test_legacy_route_profile_without_workflow_binding_is_preserved(self) -> None:
        legacy = deepcopy(self.route_profile)
        legacy.pop("workflow_profile_ref", None)
        legacy["schema_version"] = "1.1"
        result = self.resolver.resolve_next_gate_applicability(
            route_profile=legacy,
            flow_profile=None,
            next_gate="G5_DEPLOY",
            context={"effects": {}},
            root=ROOT,
        )
        self.assertEqual(result["outcome"], "PASS")
        self.assertEqual(result["next_gate"], "G5_DEPLOY")
        self.assertEqual(result["reason_code"], "GATE_APPLICABILITY_NOT_EVALUATED")

    def test_route_profile_must_bind_the_exact_flow_profile(self) -> None:
        drifted = deepcopy(self.flow_profile)
        drifted["id"] = "other-flow"
        result = self.resolver.resolve_next_gate_applicability(
            route_profile=self.route_profile,
            flow_profile=drifted,
            next_gate="G3_PR",
            context={},
            root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertEqual(result["reason_code"], "FLOW_PROFILE_BINDING_MISMATCH")

    def test_policy_registry_binding_drift_blocks(self) -> None:
        drifted = deepcopy(self.flow_profile)
        drifted["policy_registry_ref"] = "other-policy-registry"
        decision = self.evaluator.evaluate_gate_applicability(
            flow_profile=drifted,
            policy_registry=self.policy_registry,
            gate="G5_DEPLOY",
            context={"effects": {}},
        )
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertEqual(decision["reason_code"], "POLICY_REGISTRY_BINDING_MISMATCH")


if __name__ == "__main__":
    unittest.main()
