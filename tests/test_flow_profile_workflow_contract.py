"""Flow-only focused tests for the SCRUM-392 Flow Profile v2 workflow contract.

Scope: composition contract only. No policy evaluation, no authority, no runtime
state assertions (owned by other lanes).
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
VALIDATOR = ROOT / "tools/node_architect/validate_flow_profile_workflow.py"
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


class FlowProfileWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.flow = load_module("flow_workflow_contract_under_test", VALIDATOR)
        cls.registry = json.loads(
            (ROOT / "core/node-architect/profile-registry.json").read_text(encoding="utf-8")
        )
        cls.profile = cls.registry["profiles"][0]
        cls.node_registry = json.loads(
            (ROOT / "core/node-architect/node-registry.json").read_text(encoding="utf-8")
        )

    def validate(self, profile):
        return self.flow.validate_flow_profile_workflow(profile, root=ROOT)

    # --- schema + baseline compatibility ---------------------------------

    def test_shipped_registry_validates_against_schemas(self) -> None:
        self.assertEqual(schema_errors(self.registry, "profile-registry.schema.json"), [])
        self.assertEqual(schema_errors(self.profile, "flow-profile.schema.json"), [])

    def test_shipped_profile_passes_workflow_contract(self) -> None:
        result = self.validate(deepcopy(self.profile))
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["outcome"], "PASS")
        self.assertEqual(result["reason_code"], "WORKFLOW_CONTRACT_VALID")

    def test_81_canonical_node_identities_unchanged(self) -> None:
        self.assertEqual(self.node_registry["declared_slot_count"], 81)
        self.assertEqual(len(self.node_registry["nodes"]), 81)

    def test_v1_profile_remains_compatible(self) -> None:
        legacy = deepcopy(self.profile)
        legacy["version"] = "1.4.0"
        for key in ("workflow", "registry_bindings", "compatibility", "compiled", "policy_registry_ref"):
            legacy.pop(key, None)
        self.assertEqual(schema_errors(legacy, "flow-profile.schema.json"), [])
        result = self.validate(legacy)
        self.assertEqual(result["outcome"], "PASS")
        self.assertEqual(result["reason_code"], "FLOW_PROFILE_V1_COMPATIBLE")

    def test_v1_edge_kinds_map_deterministically_to_v2_semantics(self) -> None:
        self.assertEqual(self.flow.canonical_edge_kind("runtime"), "continue")
        self.assertEqual(self.flow.canonical_edge_kind("human_authority"), "human_required")
        self.assertEqual(self.flow.canonical_edge_kind("compensate"), "compensate")
        self.assertIsNone(self.flow.canonical_edge_kind("not-a-kind"))

    # --- composition boundary --------------------------------------------

    def test_flow_does_not_own_policy_logic(self) -> None:
        for binding in self.profile["workflow"]["gate_bindings"]:
            self.assertEqual(set(binding), {"gate", "policy_ref"})
        self.assertEqual({b["gate"] for b in self.profile["workflow"]["gate_bindings"]}, CANONICAL_GATES)
        serialized = json.dumps(self.profile)
        for forbidden in ("required_when", "not_applicable_when", "blocked_when", "authority_provider", "runtime_state"):
            self.assertNotIn(forbidden, serialized)

    def test_inline_policy_condition_in_gate_binding_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["workflow"]["gate_bindings"][0]["required_when"] = [{"fact": "x"}]
        self.assertNotEqual(schema_errors(broken, "flow-profile.schema.json"), [])
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_INLINE_POLICY_FORBIDDEN", [f["code"] for f in result["findings"]])

    def test_unresolved_policy_ref_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["workflow"]["gate_bindings"][0]["policy_ref"] = "ghost-policy"
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_POLICY_REF_UNRESOLVED", [f["code"] for f in result["findings"]])

    def test_missing_gate_binding_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["workflow"]["gate_bindings"] = broken["workflow"]["gate_bindings"][:6]
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_GATE_BINDING_INCOMPLETE", [f["code"] for f in result["findings"]])

    # --- DAG semantics ----------------------------------------------------

    def test_every_participant_has_gate_or_gate_neutral(self) -> None:
        for item in self.profile["workflow"]["participants"]:
            self.assertTrue(("gate" in item) ^ (item.get("gate_neutral") is True))

    def test_participant_with_both_gate_and_gate_neutral_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["workflow"]["participants"][0]["gate_neutral"] = True
        self.assertNotEqual(schema_errors(broken, "flow-profile.schema.json"), [])
        result = self.validate(broken)
        self.assertIn("WORKFLOW_PARTICIPANT_GATE_AMBIGUOUS", [f["code"] for f in result["findings"]])

    def test_undeclared_participant_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["workflow"]["participants"] = broken["workflow"]["participants"][:2]
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_PARTICIPANT_UNDECLARED", [f["code"] for f in result["findings"]])

    def test_orphan_node_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["workflow"]["edges"].append({
            "source": "intake_context.context-gap-escalation",
            "target": "validation_quality.ci-evidence-capture",
            "kind": "continue",
            "runtime_executable": True,
        })
        broken["workflow"]["participants"].append({
            "participant": "intake_context.context-gap-escalation",
            "participant_kind": "node",
            "gate_neutral": True,
        })
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_ORPHAN_NODE", [f["code"] for f in result["findings"]])

    def test_unknown_node_reference_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["workflow"]["edges"][0]["target"] = "ghost_family.ghost-node"
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_NODE_NOT_IN_REGISTRY", [f["code"] for f in result["findings"]])

    def test_untyped_edge_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["workflow"]["edges"][0]["kind"] = "mystery"
        self.assertNotEqual(schema_errors(broken, "flow-profile.schema.json"), [])
        result = self.validate(broken)
        self.assertIn("WORKFLOW_EDGE_KIND_UNTYPED", [f["code"] for f in result["findings"]])

    def test_conditional_edge_requires_condition_id(self) -> None:
        broken = deepcopy(self.profile)
        broken["workflow"]["edges"][0]["kind"] = "conditional"
        self.assertNotEqual(schema_errors(broken, "flow-profile.schema.json"), [])
        result = self.validate(broken)
        self.assertIn("WORKFLOW_CONDITIONAL_EDGE_UNBOUND", [f["code"] for f in result["findings"]])

    def test_accidental_cycle_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["workflow"]["edges"].append({
            "source": "validation_quality.ci-evidence-capture",
            "target": "repo_delivery.ci-run-capture",
            "kind": "continue",
            "runtime_executable": True,
        })
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_INVALID_CYCLE", [f["code"] for f in result["findings"]])

    def test_typed_retry_cycle_is_accepted(self) -> None:
        ok = deepcopy(self.profile)
        ok["workflow"]["edges"].append({
            "source": "runtime_checkpoint.checkpoint-persist",
            "target": "repo_delivery.ci-run-capture",
            "kind": "retry",
            "runtime_executable": True,
            "cycle_allowed": True,
        })
        ok.pop("compiled", None)
        self.assertEqual(schema_errors(ok, "flow-profile.schema.json"), [])
        result = self.validate(ok)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["outcome"], "PASS")

    def test_retry_edge_without_cycle_declaration_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["workflow"]["edges"].append({
            "source": "runtime_checkpoint.checkpoint-persist",
            "target": "repo_delivery.ci-run-capture",
            "kind": "retry",
            "runtime_executable": True,
        })
        self.assertNotEqual(schema_errors(broken, "flow-profile.schema.json"), [])
        result = self.validate(broken)
        self.assertIn("WORKFLOW_CYCLE_EDGE_NOT_DECLARED", [f["code"] for f in result["findings"]])

    def test_terminal_reachability_is_deterministic(self) -> None:
        broken = deepcopy(self.profile)
        broken["workflow"]["terminal_nodes"] = [
            item for item in broken["workflow"]["terminal_nodes"]
            if item["node"] != "failure_recovery.timeout-recovery"
        ]
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_TERMINAL_UNREACHABLE", [f["code"] for f in result["findings"]])

    def test_terminal_node_with_outgoing_edge_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["workflow"]["edges"].append({
            "source": "validation_quality.ci-evidence-capture",
            "target": "failure_recovery.timeout-recovery",
            "kind": "continue",
            "runtime_executable": True,
        })
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_TERMINAL_NOT_TERMINAL", [f["code"] for f in result["findings"]])

    # --- registry binding / staleness -------------------------------------

    def test_stale_registry_revision_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        for binding in broken["registry_bindings"]:
            if binding["registry"] == "node":
                binding["revision"] = "stale-revision-0000"
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("REGISTRY_BINDING_STALE", [f["code"] for f in result["findings"]])

    def test_registry_digest_drift_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        for binding in broken["registry_bindings"]:
            if binding["registry"] == "graph":
                binding["digest"] = "sha256:" + "0" * 64
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("REGISTRY_BINDING_DIGEST_MISMATCH", [f["code"] for f in result["findings"]])

    def test_missing_registry_binding_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["registry_bindings"] = [
            item for item in broken["registry_bindings"] if item["registry"] != "scenario"
        ]
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("REGISTRY_BINDING_MISSING", [f["code"] for f in result["findings"]])

    def test_policy_registry_binding_mismatch_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["policy_registry_ref"] = "other-policy-registry"
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("POLICY_REGISTRY_BINDING_MISMATCH", [f["code"] for f in result["findings"]])

    # --- compiled projection ----------------------------------------------

    def test_compiled_digest_is_deterministic_and_order_independent(self) -> None:
        shuffled = deepcopy(self.profile)
        shuffled["workflow"]["edges"] = list(reversed(shuffled["workflow"]["edges"]))
        shuffled["workflow"]["participants"] = list(reversed(shuffled["workflow"]["participants"]))
        first = self.flow.compile_workflow_projection(self.profile)["workflow_digest"]
        second = self.flow.compile_workflow_projection(shuffled)["workflow_digest"]
        self.assertEqual(first, second)
        self.assertEqual(first, self.profile["compiled"]["workflow_digest"])

    def test_compiled_digest_changes_with_composition(self) -> None:
        changed = deepcopy(self.profile)
        changed["workflow"]["participants"][0]["gate"] = "G4_MERGE"
        self.assertNotEqual(
            self.flow.compile_workflow_projection(changed)["workflow_digest"],
            self.profile["compiled"]["workflow_digest"],
        )

    def test_declared_digest_drift_fails_closed(self) -> None:
        broken = deepcopy(self.profile)
        broken["compiled"]["workflow_digest"] = "sha256:" + "1" * 64
        result = self.validate(broken)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_DIGEST_MISMATCH", [f["code"] for f in result["findings"]])

    def test_registry_level_validation_passes(self) -> None:
        result = self.flow.validate_profile_registry(self.registry, root=ROOT)
        self.assertEqual(result["outcome"], "PASS")

    def test_cli_entrypoint_exits_zero(self) -> None:
        self.assertEqual(self.flow.main(["--root", str(ROOT), "--emit-digest"]), 0)


if __name__ == "__main__":
    unittest.main()
