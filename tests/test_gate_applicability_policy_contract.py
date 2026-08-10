"""Focused E2E for the hardened Policy contract (SCRUM-390 / P0-B).

Covers the generic Policy semantics owned by this workstream:
authority selection, evidence binding, prohibitions, terminal acceptance,
exact policy/context digest binding, determinism/replay and fail-closed
behaviour. Workflow ordering/DAG internals and the cross-layer compiler are
out of scope here (SCRUM-389 / SCRUM-391).
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


def flow(policy_registry_ref: str = "test-registry") -> dict:
    return {
        "id": "test-flow",
        "version": "2.0.0",
        "policy_registry_ref": policy_registry_ref,
        "workflow": {
            "gate_bindings": [
                {"gate": "G4_MERGE", "policy_ref": "p-merge"},
                {"gate": "G5_DEPLOY", "policy_ref": "p-deploy"},
            ]
        },
    }


def registry(*policies: dict) -> dict:
    return {
        "schema_version": "1.1.0",
        "artifact_type": "gate-applicability-policy-registry",
        "registry_id": "test-registry",
        "revision": "test-r1",
        "policies": list(policies),
    }


MERGE_POLICY = {
    "id": "p-merge",
    "version": "1.1.0",
    "default": "REQUIRED",
    "required_when": [],
    "not_applicable_when": [],
    "blocked_when": [],
    "required_evidence": ["exact-head-binding"],
    "evidence_must_be_bound": True,
    "prohibitions": ["AUTHORITY_SELF_GRANT"],
    "authority": {
        "required": True,
        "allowed_sources": ["human", "standing-machine-authority"],
        "allowed_types": ["explicit-approval", "standing-exact-head"],
    },
    "terminal_effect": {"REQUIRED": "GATE_MUST_BE_SATISFIED_WITH_BOUND_AUTHORITY"},
}

DEPLOY_POLICY = {
    "id": "p-deploy",
    "version": "1.1.0",
    "default": "NOT_APPLICABLE",
    "required_when": [
        {"id": "manual-deploy", "field": "effects.manual_deploy_requested", "operator": "truthy"}
    ],
    "not_applicable_when": [],
    "blocked_when": [],
    "required_evidence": ["deploy-authorization"],
    "evidence_must_be_bound": True,
    "prohibitions": ["NOT_APPLICABLE_AS_PASS"],
    "terminal_effect": {"NOT_APPLICABLE": "GATE_SKIPPED_WITH_EXPLICIT_EVIDENCE_NO_DEPLOY_EFFECT"},
}

AUTHORIZED_MERGE_CONTEXT = {
    "binding": {"run_id": "r1", "task_id": "t1", "repository": "owner/repo"},
    "authority": {"source": "standing-machine-authority", "type": "standing-exact-head"},
    "evidence": {"exact-head-binding": "PRESENT"},
}


class PolicyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ev = load_module("policy_contract_evaluator", EVALUATOR)
        cls.live_registry = json.loads(
            (ROOT / "core/node-architect/gate-applicability-policy-registry.json").read_text(encoding="utf-8")
        )
        cls.live_flow = json.loads(
            (ROOT / "core/node-architect/profile-registry.json").read_text(encoding="utf-8")
        )["profiles"][0]

    def evaluate(self, gate, context, policies=(MERGE_POLICY, DEPLOY_POLICY), flow_profile=None):
        return self.ev.evaluate_gate_applicability(
            flow_profile=flow_profile or flow(),
            policy_registry=registry(*[deepcopy(p) for p in policies]),
            gate=gate,
            context=context,
        )

    def live(self, gate, context):
        return self.ev.evaluate_gate_applicability(
            flow_profile=self.live_flow,
            policy_registry=self.live_registry,
            gate=gate,
            context=context,
        )

    # --- contract shape -------------------------------------------------
    def test_decision_artifact_binds_identity_versions_and_digests(self) -> None:
        decision = self.evaluate("G4_MERGE", AUTHORIZED_MERGE_CONTEXT)
        self.assertEqual(schema_errors(decision, "gate-applicability-decision.schema.json"), [])
        self.assertEqual(decision["decision"], "REQUIRED")
        self.assertEqual(decision["binding"]["task_id"], "t1")
        self.assertEqual(decision["flow_profile_version"], "2.0.0")
        self.assertEqual(decision["policy_version"], "1.1.0")
        for field in ("flow_profile_digest", "policy_registry_digest", "policy_digest",
                      "context_digest", "decision_digest"):
            self.assertRegex(decision[field], r"^sha256:[0-9a-f]{64}$")

    def test_live_policy_registry_is_schema_valid(self) -> None:
        self.assertEqual(
            schema_errors(self.live_registry, "gate-applicability-policy-registry.schema.json"), []
        )

    # --- determinism ----------------------------------------------------
    def test_same_inputs_replay_to_identical_decision_digest(self) -> None:
        first = self.evaluate("G4_MERGE", deepcopy(AUTHORIZED_MERGE_CONTEXT))
        second = self.evaluate("G4_MERGE", deepcopy(AUTHORIZED_MERGE_CONTEXT))
        self.assertEqual(first, second)

    def test_policy_change_changes_policy_and_decision_digest(self) -> None:
        base = self.evaluate("G4_MERGE", AUTHORIZED_MERGE_CONTEXT)
        mutated = deepcopy(MERGE_POLICY)
        mutated["version"] = "1.2.0"
        other = self.evaluate("G4_MERGE", AUTHORIZED_MERGE_CONTEXT, policies=(mutated, DEPLOY_POLICY))
        self.assertNotEqual(base["policy_digest"], other["policy_digest"])
        self.assertNotEqual(base["decision_digest"], other["decision_digest"])

    def test_context_change_changes_context_digest(self) -> None:
        base = self.evaluate("G4_MERGE", AUTHORIZED_MERGE_CONTEXT)
        other_context = deepcopy(AUTHORIZED_MERGE_CONTEXT)
        other_context["binding"]["task_id"] = "t2"
        other = self.evaluate("G4_MERGE", other_context)
        self.assertNotEqual(base["context_digest"], other["context_digest"])

    # --- authority semantics -------------------------------------------
    def test_authority_source_is_selected_and_reported(self) -> None:
        decision = self.evaluate("G4_MERGE", AUTHORIZED_MERGE_CONTEXT)
        self.assertEqual(decision["authority_source"], "standing-machine-authority")
        self.assertEqual(decision["authority_type"], "standing-exact-head")

    def test_unresolved_required_authority_blocks(self) -> None:
        context = deepcopy(AUTHORIZED_MERGE_CONTEXT)
        context.pop("authority")
        decision = self.evaluate("G4_MERGE", context)
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertEqual(decision["reason_code"], "AUTHORITY_SOURCE_UNRESOLVED")

    def test_authority_source_outside_allowlist_blocks(self) -> None:
        context = deepcopy(AUTHORIZED_MERGE_CONTEXT)
        context["authority"]["source"] = "self-granted"
        decision = self.evaluate("G4_MERGE", context)
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertEqual(decision["reason_code"], "AUTHORITY_SOURCE_NOT_PERMITTED")

    def test_authority_type_outside_allowlist_blocks(self) -> None:
        context = deepcopy(AUTHORIZED_MERGE_CONTEXT)
        context["authority"]["type"] = "implicit"
        decision = self.evaluate("G4_MERGE", context)
        self.assertEqual(decision["reason_code"], "AUTHORITY_TYPE_NOT_PERMITTED")

    def test_authority_is_not_asserted_for_non_applicable_gate(self) -> None:
        decision = self.evaluate("G5_DEPLOY", {"effects": {}})
        self.assertEqual(decision["decision"], "NOT_APPLICABLE")
        self.assertIsNone(decision["authority_source"])

    # --- evidence semantics ---------------------------------------------
    def test_missing_bound_evidence_blocks(self) -> None:
        context = deepcopy(AUTHORIZED_MERGE_CONTEXT)
        context["evidence"] = {}
        decision = self.evaluate("G4_MERGE", context)
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertEqual(decision["reason_code"], "EVIDENCE_BINDING_MISSING")

    def test_stale_or_conflicting_evidence_blocks(self) -> None:
        for state in ("STALE", "CONFLICTING", "MISSING", "INVALID", "UNKNOWN"):
            with self.subTest(state=state):
                context = deepcopy(AUTHORIZED_MERGE_CONTEXT)
                context["evidence"]["exact-head-binding"] = state
                decision = self.evaluate("G4_MERGE", context)
                self.assertEqual(decision["decision"], "BLOCKED")
                self.assertEqual(decision["reason_code"], "EVIDENCE_BINDING_UNSATISFIED")

    def test_required_evidence_is_published_on_the_decision(self) -> None:
        decision = self.evaluate("G4_MERGE", AUTHORIZED_MERGE_CONTEXT)
        self.assertEqual(decision["required_evidence"], ["exact-head-binding"])

    # --- prohibitions / terminal acceptance -----------------------------
    def test_prohibitions_are_carried_into_the_decision(self) -> None:
        self.assertEqual(
            self.evaluate("G4_MERGE", AUTHORIZED_MERGE_CONTEXT)["prohibitions"],
            ["AUTHORITY_SELF_GRANT"],
        )

    def test_policy_can_tighten_terminal_acceptance(self) -> None:
        self.assertEqual(
            self.evaluate("G4_MERGE", AUTHORIZED_MERGE_CONTEXT)["terminal_effect"],
            "GATE_MUST_BE_SATISFIED_WITH_BOUND_AUTHORITY",
        )

    def test_not_applicable_is_explicit_evidence_never_pass(self) -> None:
        decision = self.evaluate("G5_DEPLOY", {"effects": {}})
        self.assertEqual(decision["decision"], "NOT_APPLICABLE")
        self.assertNotIn("PASS", decision["terminal_effect"])
        self.assertEqual(
            decision["terminal_effect"],
            "GATE_SKIPPED_WITH_EXPLICIT_EVIDENCE_NO_DEPLOY_EFFECT",
        )
        self.assertEqual(decision["reason_code"], "GATE_NOT_APPLICABLE_BY_DEFAULT")

    def test_default_terminal_effect_when_policy_is_silent(self) -> None:
        policy = deepcopy(DEPLOY_POLICY)
        policy.pop("terminal_effect")
        decision = self.evaluate("G5_DEPLOY", {"effects": {}}, policies=(MERGE_POLICY, policy))
        self.assertEqual(decision["terminal_effect"], "GATE_SKIPPED_WITH_EXPLICIT_EVIDENCE")

    # --- context binding / fail closed ----------------------------------
    def test_incomplete_required_context_fields_block(self) -> None:
        policy = deepcopy(MERGE_POLICY)
        policy["context_requirements"] = {"required_fields": ["merge.exact_head"]}
        decision = self.evaluate("G4_MERGE", AUTHORIZED_MERGE_CONTEXT, policies=(policy, DEPLOY_POLICY))
        self.assertEqual(decision["reason_code"], "CONTEXT_BINDING_INCOMPLETE")

    def test_context_digest_mismatch_blocks(self) -> None:
        policy = deepcopy(MERGE_POLICY)
        policy["context_requirements"] = {"expected_context_digest": "sha256:" + "0" * 64}
        context = deepcopy(AUTHORIZED_MERGE_CONTEXT)
        context["context_digest"] = "sha256:" + "1" * 64
        decision = self.evaluate("G4_MERGE", context, policies=(policy, DEPLOY_POLICY))
        self.assertEqual(decision["reason_code"], "CONTEXT_DIGEST_MISMATCH")

    def test_stale_context_blocks_and_unknown_age_blocks(self) -> None:
        policy = deepcopy(MERGE_POLICY)
        policy["context_requirements"] = {"max_context_age_seconds": 60}
        stale = deepcopy(AUTHORIZED_MERGE_CONTEXT)
        stale["context_age_seconds"] = 600
        self.assertEqual(
            self.evaluate("G4_MERGE", stale, policies=(policy, DEPLOY_POLICY))["reason_code"],
            "CONTEXT_STALE",
        )
        self.assertEqual(
            self.evaluate("G4_MERGE", AUTHORIZED_MERGE_CONTEXT, policies=(policy, DEPLOY_POLICY))["reason_code"],
            "CONTEXT_FRESHNESS_UNKNOWN",
        )

    def test_unversioned_policy_blocks(self) -> None:
        policy = deepcopy(MERGE_POLICY)
        policy.pop("version")
        decision = self.evaluate("G4_MERGE", AUTHORIZED_MERGE_CONTEXT, policies=(policy, DEPLOY_POLICY))
        self.assertEqual(decision["reason_code"], "GATE_POLICY_UNVERSIONED")

    def test_non_canonical_gate_is_blocked_not_invented(self) -> None:
        decision = self.evaluate("G7_INVENTED", {})
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertEqual(decision["reason_code"], "GATE_NOT_CANONICAL")

    def test_registry_binding_drift_blocks(self) -> None:
        decision = self.evaluate(
            "G4_MERGE", AUTHORIZED_MERGE_CONTEXT, flow_profile=flow("other-registry")
        )
        self.assertEqual(decision["reason_code"], "POLICY_REGISTRY_BINDING_MISMATCH")

    # --- live registry regression (route expressed by data, not code) ----
    def test_live_autonomous_regression_semantics(self) -> None:
        merged = {
            "binding": {"run_id": "r", "task_id": "SCRUM-390", "repository": "owner/repo"},
            "merge": {"target_branch": "pre-prod", "exact_head_verified": True},
            "effects": {},
            "evidence": {"gate-transition-decision": "PRESENT", "exact-head-binding": "PRESENT"},
            "authority": {"source": "standing-machine-authority", "type": "standing-exact-head"},
        }
        self.assertEqual(self.live("G4_MERGE", merged)["decision"], "REQUIRED")
        self.assertEqual(self.live("G5_DEPLOY", merged)["decision"], "NOT_APPLICABLE")
        self.assertEqual(self.live("G6_PRODUCTION_DATA", merged)["decision"], "NOT_APPLICABLE")

        with_deploy = deepcopy(merged)
        with_deploy["effects"]["manual_deploy_requested"] = True
        with_deploy["evidence"]["deploy-authorization"] = "PRESENT"
        # G5 authority is human-only in the live policy; a standing machine
        # authority must not be reusable for a deploy effect.
        self.assertEqual(self.live("G5_DEPLOY", with_deploy)["reason_code"],
                         "AUTHORITY_SOURCE_NOT_PERMITTED")
        with_deploy["authority"] = {"source": "human", "type": "explicit-approval"}
        deploy_decision = self.live("G5_DEPLOY", with_deploy)
        self.assertEqual(deploy_decision["decision"], "REQUIRED")
        self.assertEqual(deploy_decision["authority_source"], "human")

    def test_live_g4_blocks_when_exact_head_not_verified(self) -> None:
        context = {
            "binding": {"run_id": "r", "task_id": "SCRUM-390", "repository": "owner/repo"},
            "merge": {"target_branch": "pre-prod", "exact_head_verified": False},
            "effects": {},
        }
        decision = self.live("G4_MERGE", context)
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertEqual(decision["matched_rule"], "exact-head-unverified")

    def test_evaluator_source_has_no_route_or_task_specific_branch(self) -> None:
        source = EVALUATOR.read_text(encoding="utf-8")
        for forbidden in ("SCRUM-", "if autonomous", "AUTONOMOUS_TO_PREPROD", "pre-prod"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
