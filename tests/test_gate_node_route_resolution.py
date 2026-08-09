from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def module():
    path = ROOT / "tools/node_architect/resolve_gate_node_route.py"
    spec = importlib.util.spec_from_file_location("resolver263", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def context(action: str = "repository_write", mode: str = "normal"):
    envelope = {
        "task_id": "SCRUM-263",
        "authority_gate": "G2_EXECUTION",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "base_sha": "a" * 40,
        "working_branch": "feature/scrum-263-node-instruction-evidence-ledger",
        "scope_hash": "sha256:" + "b" * 64,
    }
    loaded = {
        "g0_context": {"status": "READY"},
        "g1_decision": {"status": "PASS"},
        "g2_envelope": envelope,
        "approval_receipt": {"status": "VALID"},
        "task_claim": {"agent": "ChatGPT"},
        "base_sha_readback": {"sha": envelope["base_sha"]},
    }
    if action in {"post_write_readback", "resolve_gate_transition"}:
        loaded["write_result"] = {"status": "success"}
    if action == "resolve_gate_transition":
        loaded["diff_readback"] = {"status": "PASS"}
    return {
        "task_id": "SCRUM-263",
        "gate": "G2_EXECUTION",
        "requested_action": action,
        "workflow_mode": mode,
        "repository": envelope["repository"],
        "base_sha": envelope["base_sha"],
        "working_branch": envelope["working_branch"],
        "scope_hash": envelope["scope_hash"],
        "expected_profile_revision": "scrum-288-entry-schema-validation-20260809-r1",
        "expected_graph_revision": "scrum-104-20260726",
        "available_connectors": ["GitHub.compare_commits"],
        "context": loaded,
    }


class TestGateNodeRouteResolution(unittest.TestCase):
    def setUp(self):
        self.mod = module()
        self.profile = load("core/node-architect/gate-node-route-profile.json")
        self.nodes = load("core/node-architect/node-registry.json")
        self.graph = load("core/node-architect/runtime-graph-registry.json")
        self.decision_schema = load("schemas/node-architect/gate-node-route-decision.schema.json")
        self.profile_schema = load("schemas/node-architect/gate-node-route-profile.schema.json")

    def resolve(self, ctx=None, profile=None, nodes=None, graph=None, root=ROOT):
        return self.mod.resolve_gate_node_route(
            profile=profile or self.profile,
            node_registry=nodes or self.nodes,
            graph_registry=graph or self.graph,
            context=ctx or context(),
            root=root,
        )

    def test_profile_schema(self):
        Draft202012Validator(self.profile_schema).validate(self.profile)

    def test_g2_repository_write_routes_to_scoped_write(self):
        result = self.resolve()
        self.assertEqual(result["outcome"], "ROUTE_SELECTED")
        self.assertEqual(result["current_node"], "repo_delivery.scoped-file-write")
        self.assertEqual(result["next_node"], "repo_delivery.diff-readback")
        self.assertFalse(result["authority_granted"])
        Draft202012Validator(self.decision_schema).validate(result)

    def test_route_selected_requires_valid_instruction_contract(self):
        result = self.resolve()
        self.assertTrue(result["instruction_validated"])
        self.assertTrue(result["evidence_contract_valid"])
        self.assertTrue(result["log_contract_valid"])
        self.assertTrue(result["next_route_contract_valid"])
        self.assertTrue(result["mode_runtime_required"])
        self.assertTrue(result["instruction_digest"].startswith("sha256:"))

    def test_full_g2_repository_write_vertical_slice(self):
        first = self.resolve(context("resolve_execution_node"))
        self.assertEqual(first["current_node"], "gate_authority.gate-state-resolution")
        self.assertEqual(first["next_node"], "repo_delivery.scoped-file-write")

        write = self.resolve(context("repository_write"))
        self.assertEqual(write["current_node"], "repo_delivery.scoped-file-write")
        self.assertEqual(write["next_node"], "repo_delivery.diff-readback")

        readback = self.resolve(context("post_write_readback"))
        self.assertEqual(readback["current_node"], "repo_delivery.diff-readback")
        self.assertEqual(readback["next_node"], "gate_authority.gate-transition-decision")

        transition = self.resolve(context("resolve_gate_transition"))
        self.assertEqual(transition["current_node"], "gate_authority.gate-transition-decision")
        self.assertEqual(transition["next_gate"], "G3_PR")
        self.assertFalse(transition["pr_authority_granted"])

    def test_post_write_routes_to_diff_readback(self):
        result = self.resolve(context("post_write_readback"))
        self.assertEqual(result["current_node"], "repo_delivery.diff-readback")
        self.assertEqual(result["next_node"], "gate_authority.gate-transition-decision")

    def test_transition_routes_to_g3_boundary(self):
        result = self.resolve(context("resolve_gate_transition"))
        self.assertEqual(result["next_gate"], "G3_PR")
        self.assertFalse(result["pr_authority_granted"])

    def test_missing_context_fails_closed(self):
        ctx = context()
        del ctx["context"]["approval_receipt"]
        result = self.resolve(ctx)
        self.assertEqual(result["reason_code"], "NODE_CONTEXT_NOT_LOADED")

    def test_empty_context_artifact_is_not_loaded(self):
        ctx = context()
        ctx["context"]["approval_receipt"] = {}
        result = self.resolve(ctx)
        self.assertEqual(result["reason_code"], "NODE_CONTEXT_NOT_LOADED")

    def test_invalid_authority_readback_fails_closed(self):
        ctx = context()
        ctx["context"]["approval_receipt"] = {"status": "EXPIRED"}
        result = self.resolve(ctx)
        self.assertEqual(result["reason_code"], "GATE_NODE_BINDING_MISMATCH")

    def test_missing_route_fails_closed(self):
        ctx = context("not-defined")
        self.assertEqual(self.resolve(ctx)["reason_code"], "NODE_ROUTE_MISSING")

    def test_ambiguous_route_fails_closed(self):
        profile = copy.deepcopy(self.profile)
        profile["routes"].append(copy.deepcopy(profile["routes"][1]))
        self.assertEqual(self.resolve(profile=profile)["reason_code"], "NODE_ROUTE_AMBIGUOUS")

    def test_gate_binding_mismatch_fails_closed(self):
        ctx = context()
        ctx["context"]["g2_envelope"]["working_branch"] = "other"
        self.assertEqual(self.resolve(ctx)["reason_code"], "GATE_NODE_BINDING_MISMATCH")

    def test_graph_revision_drift_fails_closed(self):
        ctx = context()
        ctx["expected_graph_revision"] = "other"
        self.assertEqual(self.resolve(ctx)["reason_code"], "GRAPH_REVISION_DRIFT")

    def test_profile_revision_drift_fails_closed(self):
        ctx = context()
        ctx["expected_profile_revision"] = "other"
        self.assertEqual(self.resolve(ctx)["reason_code"], "PROFILE_REVISION_DRIFT")

    def test_catalog_only_node_fails_without_override(self):
        profile = copy.deepcopy(self.profile)
        profile["routes"][1]["allow_proposed_with_implementation"] = False
        self.assertEqual(self.resolve(profile=profile)["reason_code"], "NODE_NOT_EXECUTABLE_AT_MATURITY")

    def test_maturity_ineligible_fails_closed(self):
        profile = copy.deepcopy(self.profile)
        profile["routes"][1]["minimum_maturity"] = "stable"
        self.assertEqual(self.resolve(profile=profile)["reason_code"], "NODE_NOT_EXECUTABLE_AT_MATURITY")

    def test_missing_implementation_fails_closed(self):
        profile = copy.deepcopy(self.profile)
        profile["routes"][1]["implementation"]["ref"] = "missing.py:run"
        self.assertEqual(self.resolve(profile=profile)["reason_code"], "NODE_IMPLEMENTATION_UNAVAILABLE")

    def test_python_implementation_check_does_not_execute_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            implementation = root / "dangerous.py"
            implementation.write_text(
                'raise RuntimeError("must not execute")\n\ndef run():\n    return True\n',
                encoding="utf-8",
            )
            available = self.mod._implementation_available(
                root,
                {"kind": "python", "ref": "dangerous.py:run"},
                {},
            )
        self.assertTrue(available)

    def test_missing_contract_fails_closed(self):
        profile = copy.deepcopy(self.profile)
        profile["routes"][1]["node_descriptor_ref"] = "missing.json"
        self.assertEqual(self.resolve(profile=profile)["reason_code"], "NODE_CONTRACT_MISSING")

    def test_missing_instruction_fails_closed(self):
        profile = copy.deepcopy(self.profile)
        profile["routes"][1]["node_instruction_ref"] = "missing.yaml"
        self.assertEqual(self.resolve(profile=profile)["reason_code"], "NODE_INSTRUCTION_MISSING")

    def test_supported_modes_still_require_instruction_runtime(self):
        for mode in ("normal", "fastlane", "e2e", "hotfix", "rescue"):
            with self.subTest(mode=mode):
                result = self.resolve(context(mode=mode))
                self.assertEqual(result["outcome"], "ROUTE_SELECTED")
                self.assertTrue(result["instruction_validated"])
                self.assertTrue(result["mode_runtime_required"])

    def test_unknown_mode_fails_closed(self):
        result = self.resolve(context(mode="bypass"))
        self.assertEqual(result["reason_code"], "MODE_BYPASSES_NODE_RUNTIME")

    def test_decision_digest_is_deterministic(self):
        self.assertEqual(self.resolve()["decision_digest"], self.resolve()["decision_digest"])


if __name__ == "__main__":
    unittest.main()
