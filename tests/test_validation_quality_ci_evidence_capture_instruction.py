"""Focused regression tests for the validation_quality.ci-evidence-capture node
instruction + route wiring (SCRUM-337 recovery).

Scoped to the bounded S2 delta only. The route/instruction are resolved by
``current_node`` / ``route_id`` (never by positional index) so they stay stable
if the route-profile array is reordered.

The catalog descriptor id is kebab-case (``validation-quality-ci-evidence-capture``)
while the runtime/card/registry/route identifiers are dotted
(``validation_quality.ci-evidence-capture``). The deterministic identity bridge
reconciles them without weakening catalog validation (the descriptor is never
mutated to the dotted form).
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(path: str):
    text = (ROOT / path).read_text(encoding="utf-8")
    if path.endswith((".yaml", ".yml")):
        import yaml
        return yaml.safe_load(text)
    return json.loads(text)


def _module(name: str, rel: str):
    p = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def context(action: str = "ci_evidence_capture", mode: str = "normal"):
    envelope = {
        "task_id": "SCRUM-337",
        "authority_gate": "G3_PR",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "base_sha": "a" * 40,
        "working_branch": "auto/SCRUM-337-na81-recert-20260814-r10",
        "scope_hash": "sha256:" + "b" * 64,
    }
    loaded = {
        "g0_context": {"status": "READY"},
        "g1_decision": {"status": "PASS"},
        "g2_envelope": envelope,
        "approval_receipt": {"status": "VALID"},
        "task_claim": {"agent": "ChatGPT"},
        "base_sha_readback": {"sha": envelope["base_sha"]},
        "draft_pr_result": {"status": "success"},
    }
    profile = _load("core/node-architect/gate-node-route-profile.json")
    return {
        "task_id": "SCRUM-337",
        "gate": "G3_PR",
        "requested_action": action,
        "workflow_mode": mode,
        "repository": envelope["repository"],
        "base_sha": envelope["base_sha"],
        "working_branch": envelope["working_branch"],
        "scope_hash": envelope["scope_hash"],
        "expected_profile_revision": profile["revision"],
        "expected_graph_revision": profile["bound_graph_revision"],
        "available_connectors": ["GitHub.compare_commits"],
        "context": loaded,
    }


class CiEvidenceCaptureInstructionTests(unittest.TestCase):
    def setUp(self):
        self.res = _module("res_cec", "tools/node_architect/resolve_gate_node_route.py")
        self.vin = _module("vin_cec", "tools/node_architect/validate_node_instruction.py")
        self.profile = _load("core/node-architect/gate-node-route-profile.json")
        self.registry = _load("core/node-architect/node-registry.json")
        self.graph = _load("core/node-architect/runtime-graph-registry.json")
        self.route = next(
            r for r in self.profile["routes"]
            if r["current_node"] == "validation_quality.ci-evidence-capture"
            and r["route_id"] == "g3-ci-evidence-capture"
        )
        self.card = _load(self.route["node_instruction_ref"])
        self.desc = _load(self.route["node_descriptor_ref"])
        self.node = next(
            n for n in self.registry["nodes"] if n["id"] == self.route["current_node"]
        )

    def resolve(self, ctx=None, profile=None):
        return self.res.resolve_gate_node_route(
            profile=profile or self.profile, node_registry=self.registry,
            graph_registry=self.graph, context=ctx or context(), root=ROOT,
        )

    def validate(self, card=None, mode="normal"):
        return self.vin.validate_instruction(
            card=card or self.card,
            schema=_load("schemas/node-architect/node-instruction.schema.json"),
            descriptor=self.desc, registry_node=self.node,
            route=self.route, active_gate="G3_PR", mode=mode,
        )

    # --- positive: instruction + route resolve cleanly ---
    def test_instruction_validates(self):
        self.assertTrue(self.validate().valid)

    def test_route_selected_with_valid_instruction(self):
        result = self.resolve()
        self.assertEqual(result["outcome"], "ROUTE_SELECTED")
        self.assertEqual(result["current_node"], "validation_quality.ci-evidence-capture")
        self.assertIsNone(result["next_node"])
        self.assertEqual(result["next_action"], "complete_delivery_evidence")
        self.assertIsNone(result["next_gate"])
        self.assertTrue(result["instruction_validated"])
        self.assertTrue(result["mode_runtime_required"])
        self.assertFalse(result["authority_granted"])

    def test_supported_modes_still_require_instruction_runtime(self):
        for mode in ("normal", "fastlane", "e2e", "hotfix", "rescue"):
            with self.subTest(mode=mode):
                result = self.resolve(context(mode=mode))
                self.assertEqual(result["outcome"], "ROUTE_SELECTED")
                self.assertTrue(result["instruction_validated"])

    # --- identity bridge: kebab descriptor reconciles with dotted runtime ---
    def test_bridge_reconciles_kebab_descriptor_and_dotted_runtime(self):
        self.assertEqual(self.desc["node_id"], "validation-quality-ci-evidence-capture")
        self.assertEqual(self.card["node_id"], "validation_quality.ci-evidence-capture")
        self.assertEqual(self.route["current_node"], "validation_quality.ci-evidence-capture")
        self.assertEqual(self.node["id"], "validation_quality.ci-evidence-capture")
        self.assertEqual(
            self.vin.bridge_node_identity(self.desc["node_id"]),
            self.vin.bridge_node_identity(self.card["node_id"]),
        )

    def test_bridge_function_is_deterministic(self):
        self.assertEqual(
            self.vin.bridge_node_identity("validation_quality.ci-evidence-capture"),
            "validation-quality-ci-evidence-capture",
        )
        self.assertEqual(
            self.vin.bridge_node_identity("validation-quality-ci-evidence-capture"),
            "validation-quality-ci-evidence-capture",
        )
        self.assertEqual(self.vin.bridge_node_identity(""), "")

    def test_catalog_descriptor_kebab_preserved(self):
        # invariant: descriptor mutation to dotted id is forbidden
        self.assertEqual(self.desc["node_id"], "validation-quality-ci-evidence-capture")

    # --- authority boundary: instruction cannot grant authority ---
    def test_instruction_cannot_grant_authority(self):
        card = copy.deepcopy(self.card)
        card["authority_boundary"]["merge_authority_granted"] = True
        self.assertIn("NODE_AUTHORITY_ESCALATION_ATTEMPT", self.validate(card).reason_codes)

    def test_route_grants_no_merge_authority(self):
        result = self.resolve()
        self.assertFalse(result.get("pr_authority_granted", False))
        self.assertFalse(result.get("authority_granted", False))

    # --- negative: missing instruction fails closed ---
    def test_missing_instruction_fails_closed(self):
        profile = copy.deepcopy(self.profile)
        r = next(x for x in profile["routes"]
                 if x["current_node"] == "validation_quality.ci-evidence-capture")
        r["node_instruction_ref"] = "core/node-architect/node-instructions/missing.yaml"
        self.assertEqual(self.resolve(profile=profile)["reason_code"], "NODE_INSTRUCTION_MISSING")

    # --- negative: prohibited next-gate drift in instruction ---
    def test_missing_next_route_fails_closed(self):
        card = copy.deepcopy(self.card)
        card["next"]["pass"]["next_node"] = None
        card["next"]["pass"]["next_action"] = None
        card["next"]["pass"]["next_gate"] = None
        self.assertIn("NODE_NEXT_ROUTE_MISSING", self.validate(card).reason_codes)

    def test_next_gate_mismatch_fails_closed(self):
        card = copy.deepcopy(self.card)
        card["next"]["pass"]["next_gate"] = "G4_MERGE"
        self.assertIn("NODE_NEXT_ROUTE_MISSING", self.validate(card).reason_codes)

    # --- replay / idempotency: instruction requires idempotency + readback ---
    def test_instruction_requires_replay_readback(self):
        card = copy.deepcopy(self.card)
        retry = card.get("retry", {})
        self.assertIn("readback", retry.get("replay_check", "").lower())
        idem = retry.get("idempotency_key_fields", [])
        self.assertIn("scope_hash", idem)
        self.assertIn("task_id", idem)

    def test_instruction_forbids_pr_base_change_and_merge(self):
        forbidden = set(self.card["forbidden_actions"])
        self.assertIn("merge", forbidden)
        self.assertIn("auto_merge", forbidden)
        self.assertIn("force_push", forbidden)
        self.assertIn("pr_base_change", forbidden)

    # --- instruction-card artifact is well-formed and schema-valid ---
    def test_instruction_card_json_is_schema_valid(self):
        card = _load(
            "core/node-architect/node-instructions/validation_quality/ci-evidence-capture.node.instruction-card.json"
        )
        schema = _load("schemas/node-architect/instruction-card.schema.json")
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(card)
        self.assertEqual(card["node_id"], "validation_quality.ci-evidence-capture")

    # --- route shape invariants ---
    def test_route_appended_not_inserted(self):
        self.assertEqual(self.profile["routes"][1]["current_node"],
                         "repo_delivery.scoped-file-write")

    def test_route_binds_exact_descriptor_and_instruction(self):
        self.assertEqual(
            self.route["node_descriptor_ref"],
            "core/node-architect/node-catalog/validation_quality/ci-evidence-capture.node.json",
        )
        self.assertEqual(
            self.route["node_instruction_ref"],
            "core/node-architect/node-instructions/validation_quality/ci-evidence-capture.node-instruction.yaml",
        )


if __name__ == "__main__":
    unittest.main()
