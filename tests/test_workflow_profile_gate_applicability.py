from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / "tools/node_architect/evaluate_gate_applicability.py"
RESOLVER = ROOT / "tools/node_architect/resolve_gate_node_route.py"
REGISTRY_VALIDATOR = ROOT / "tools/node_architect/validate_runtime_registry.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class WorkflowProfileGateApplicabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evaluator = load_module("workflow_gate_applicability_test", EVALUATOR)
        cls.resolver = load_module("workflow_gate_route_resolver_test", RESOLVER)
        cls.profile_registry = json.loads(
            (ROOT / "core/node-architect/profile-registry.json").read_text(encoding="utf-8")
        )
        cls.flow_profile = cls.profile_registry["profiles"][0]
        cls.route_profile = json.loads(
            (ROOT / "core/node-architect/gate-node-route-profile.json").read_text(encoding="utf-8")
        )
        cls.node_registry = json.loads(
            (ROOT / "core/node-architect/node-registry.json").read_text(encoding="utf-8")
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

    def test_gate_bindings_are_unique(self) -> None:
        gates = [item["gate"] for item in self.flow_profile["workflow"]["gate_bindings"]]
        self.assertEqual(len(gates), len(set(gates)))
        self.assertTrue({"G2_EXECUTION", "G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION"} <= set(gates))

    def test_g5_is_not_applicable_without_deploy_effect(self) -> None:
        decision = self.evaluator.evaluate_gate_applicability(
            flow_profile=self.flow_profile,
            gate="G5_DEPLOY",
            context={"effects": {}},
        )
        self.assertEqual(decision["decision"], "NOT_APPLICABLE")
        self.assertEqual(decision["reason_code"], "GATE_NOT_APPLICABLE_BY_DEFAULT")

    def test_g5_is_required_when_manual_deploy_requested(self) -> None:
        decision = self.evaluator.evaluate_gate_applicability(
            flow_profile=self.flow_profile,
            gate="G5_DEPLOY",
            context={"effects": {"manual_deploy_requested": True}},
        )
        self.assertEqual(decision["decision"], "REQUIRED")
        self.assertEqual(decision["matched_rule"], "manual-deploy")

    def test_blocked_precedence_wins_over_required(self) -> None:
        decision = self.evaluator.evaluate_gate_applicability(
            flow_profile=self.flow_profile,
            gate="G5_DEPLOY",
            context={"effects": {"manual_deploy_requested": True, "deploy_blocked": True}},
        )
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertEqual(decision["matched_rule"], "deploy-blocked")

    def test_g6_is_effect_driven(self) -> None:
        no_effect = self.evaluator.evaluate_gate_applicability(
            flow_profile=self.flow_profile,
            gate="G6_PRODUCTION",
            context={"effects": {}},
        )
        production = self.evaluator.evaluate_gate_applicability(
            flow_profile=self.flow_profile,
            gate="G6_PRODUCTION",
            context={"effects": {"production_config_change": True}},
        )
        self.assertEqual(no_effect["decision"], "NOT_APPLICABLE")
        self.assertEqual(production["decision"], "REQUIRED")

    def test_resolver_helper_skips_not_applicable_next_gate(self) -> None:
        result = self.resolver.resolve_next_gate_applicability(
            route_profile=self.route_profile,
            flow_profile=self.flow_profile,
            next_gate="G5_DEPLOY",
            context={"effects": {}},
            root=ROOT,
        )
        self.assertEqual(result["outcome"], "PASS")
        self.assertIsNone(result["next_gate"])
        self.assertEqual(result["reason_code"], "NEXT_GATE_NOT_APPLICABLE")

    def test_resolver_helper_keeps_required_next_gate(self) -> None:
        result = self.resolver.resolve_next_gate_applicability(
            route_profile=self.route_profile,
            flow_profile=self.flow_profile,
            next_gate="G5_DEPLOY",
            context={"effects": {"release_requested": True}},
            root=ROOT,
        )
        self.assertEqual(result["outcome"], "PASS")
        self.assertEqual(result["next_gate"], "G5_DEPLOY")
        self.assertEqual(result["reason_code"], "NEXT_GATE_REQUIRED")

    def test_legacy_resolver_behavior_is_preserved_without_flow_profile(self) -> None:
        result = self.resolver.resolve_next_gate_applicability(
            route_profile=self.route_profile,
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


if __name__ == "__main__":
    unittest.main()
