"""SCRUM-844: canonical G1->G2 approval preparation, never G2 execution.

This integration uses the production map, gate resolver, authority boundary,
risk classification, approval generator and envelope renderer. No fake
gate-state PASS is injected.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import unittest

from jsonschema import Draft202012Validator

from tools.node_architect.authority_boundary_check import (
    ACTION_TO_MINIMUM_GATE, SCOPE_IDENTITY_KEYS, check_authority_boundary,
)
from tools.node_architect.evidence_artifact_map import build_gate_evidence_artifact_map
from tools.node_architect.g2_approval_preparation import (
    G2PreparationBlocked, prepare_g2_approval,
)
from tools.node_architect.g2_execution_envelope_render import render_g2_execution_envelope
from tools.node_architect.risk_classification import (
    build_default_policy, render_risk_classification,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _module_from_test(filename: str):
    # Existing source-owned test helpers instantiate valid scopes and canonical
    # evidence candidate shapes; no hand-edited resolver output is used.
    path = ROOT / "tests" / filename
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


GS = _module_from_test("test_gate_authority_gate_state_resolution_m5.py")
RISK = _module_from_test("test_intake_context_risk_classification.py")
TASK, REPO, BASE = GS.TASK, GS.REPO, GS.BASE
ISSUED = "2026-10-17T07:00:00Z"
EXPIRES = "2026-10-17T09:00:00Z"


def make_input():
    scope = GS.scope(head_sha=BASE, authorized_actions=['run_sandboxed_validation'])
    # Deliberately no G2, G3, G4 artifacts. All 5 early entries are source-bound.
    early = [x for x in GS.candidates() if x["gate"] in ("G0_CONTEXT", "G1_ALIGNMENT")]
    evidence = build_gate_evidence_artifact_map(
        task_id=TASK, repository=REPO, base_sha=BASE, head_sha=BASE,
        evidence_candidates=early, policy_revision="gate-transition-map@1.0.1",
    )
    # Real risk-classifier producer (including real protected-base producer).
    facts = RISK.upstreams(signals=["schema_change"])
    for name, item in facts.items():
        if name == "protected_base_snapshot":
            facts[name] = RISK.PRODUCER.render_protected_base_capture(
                task_id=TASK, repository=REPO, protected_base_sha=BASE,
                evidence_source="github:exact-base", verified_sha=BASE,
            )
        else:
            item["repository"] = REPO
            item["base_sha"] = BASE
    risk_policy = build_default_policy()
    risk = render_risk_classification(
        task_id=TASK, repository=REPO, base_sha=BASE,
        request_intake=facts["request_intake"],
        source_resolution=facts["source_resolution"],
        repo_identity=facts["repo_identity"],
        protected_base_snapshot=facts["protected_base_snapshot"],
        policy=risk_policy, classified_at=ISSUED,
    )
    assert risk["outcome"] == "ACCEPTED" and risk["risk_level"] == "R2"
    return dict(
        task_id=TASK, repository=REPO, current_base_sha=BASE,
        scope_identity=scope, evidence_map=evidence, transition_map=GS.tmap(),
        risk_profile=risk, risk_producers={
            "request_intake": facts["request_intake"],
            "source_resolution": facts["source_resolution"],
            "repo_identity": facts["repo_identity"],
            "protected_base_capture": facts["protected_base_snapshot"],
        }, risk_policy=risk_policy,
        requested_action="run_sandboxed_validation",
        actor_target={"type": "user", "id": "approval-reviewer"},
        issued_at=ISSUED, expires_at=EXPIRES,
        event_id_or_idempotency_key="scrum844-g01-ready-01",
        checkpoint_id="scrum844-preparation-checkpoint",
    )


class G2BootstrapIntegration(unittest.TestCase):
    def test_real_source_can_request_approval_without_envelope(self):
        inputs = make_input()
        result = prepare_g2_approval(**inputs)
        gs = result["gate_state_resolution"]
        self.assertEqual((gs["current_gate"], gs["gate_status"], gs["last_passed_gate"]),
                         ("G2_EXECUTION", "BLOCKED", "G1_ALIGNMENT"))
        self.assertIn(".gwc/tasks/SCRUM-184/g2/execution-envelope.yaml",
                      gs["missing_evidence"])
        self.assertEqual(result["authority_boundary_decision"]["decision"], "REQUIRE_APPROVAL")
        self.assertFalse(result["authority_boundary_decision"]["write_authority_granted"])
        self.assertEqual(result["status"], "AWAITING_HUMAN_APPROVAL")
        self.assertEqual(result["approval_request"]["gate"], "G2_EXECUTION")
        self.assertTrue(result["approval_request"]["approval_command"].startswith("APPROVE G2 "))
        self.assertFalse(result["approval_request"]["authority_granted"])
        env = result["pending_g2_envelope"]
        self.assertEqual(env["activation_state"], "AWAITING_APPROVAL")
        self.assertFalse(env["execution_started"])
        self.assertIsNone(env["approval_validation_ref"])
        for name, path, value in (
            ("request", "schemas/gate-approval-request.schema.json", result["approval_request"]),
            ("pending", "schemas/g2-execution-envelope.schema.json", env),
        ):
            with self.subTest(name=name):
                schema = json.loads((ROOT / path).read_text())
                errors = list(Draft202012Validator(schema).iter_errors(value))
                self.assertEqual([], [e.message for e in errors])

    def test_native_execution_boundary_still_blocks(self):
        inputs = make_input()
        res = prepare_g2_approval(**inputs)
        native = check_authority_boundary(
            task_id=TASK, repository=REPO, requested_action="run_sandboxed_validation",
            gate_state_resolution=res["gate_state_resolution"],
            scope_identity={k: v for k, v in inputs["scope_identity"].items()
                            if k in SCOPE_IDENTITY_KEYS},
            gate_policy={"action_map": ACTION_TO_MINIMUM_GATE},
            risk_class="R2", production_scope_applicable=False,
            manual_g5_action=False,
            event_id_or_idempotency_key="scrum844-check-execution",
        )
        self.assertEqual((native["decision"], native["primary_reason_code"]),
                         ("BLOCK", "AUTHORITY_GATE_INSUFFICIENT"))
        self.assertFalse(native["write_authority_granted"])

    def test_same_input_same_approval_and_envelope_digest(self):
        kw = make_input()
        x, y = prepare_g2_approval(**kw), prepare_g2_approval(**copy.deepcopy(kw))
        self.assertEqual(x["approval_request"]["request_digest"],
                         y["approval_request"]["request_digest"])
        self.assertEqual(x["pending_g2_envelope"]["envelope_digest"],
                         y["pending_g2_envelope"]["envelope_digest"])

    def test_real_readback_schema_and_risk_cannot_be_forged(self):
        for field, bad in (
            ("risk_level", "R0"), ("outcome", "BLOCKED"),
            ("base_sha", "a" * 40), ("decision_digest", "fake"),
            ("required_gate", "G3_PR")
        ):
            with self.subTest(field=field):
                kw = make_input()
                kw["risk_profile"][field] = bad
                with self.assertRaises(G2PreparationBlocked):
                    prepare_g2_approval(**kw)

    def test_forged_risk_digest_with_valid_shape_is_rejected(self):
        kw = make_input()
        kw["risk_profile"]["decision_digest"] = "sha256:" + "b" * 64
        with self.assertRaisesRegex(G2PreparationBlocked, "G2_PREP_RISK_SOURCE_MISMATCH"):
            prepare_g2_approval(**kw)

    def test_changed_risk_policy_digest_is_rejected(self):
        kw = make_input()
        kw["risk_policy"]["digest"] = "sha256:" + "e" * 64
        with self.assertRaisesRegex(G2PreparationBlocked, "G2_PREP_RISK_SOURCE_MISMATCH"):
            prepare_g2_approval(**kw)

    def test_early_evidence_missing_or_stale_denied(self):
        for variant in ("missing_g1", "stale_g0", "broken_digest"):
            with self.subTest(variant=variant):
                kw = make_input()
                if variant == "missing_g1":
                    cs = [c for c in GS.candidates()
                          if c["gate"] in ("G0_CONTEXT", "G1_ALIGNMENT")][:-1]
                    kw["evidence_map"] = build_gate_evidence_artifact_map(
                        task_id=TASK, repository=REPO, base_sha=BASE,
                        head_sha=BASE, evidence_candidates=cs,
                        policy_revision="gate-transition-map@1.0.1")
                elif variant == "stale_g0":
                    cs = [c for c in GS.candidates()
                          if c["gate"] in ("G0_CONTEXT", "G1_ALIGNMENT")]
                    cs[0]["freshness_status"] = "STALE"
                    kw["evidence_map"] = build_gate_evidence_artifact_map(
                        task_id=TASK, repository=REPO, base_sha=BASE,
                        head_sha=BASE, evidence_candidates=cs,
                        policy_revision="gate-transition-map@1.0.1")
                else:
                    kw["evidence_map"]["map_digest"] = "sha256:" + "0" * 64
                with self.assertRaises(G2PreparationBlocked):
                    prepare_g2_approval(**kw)

    def test_denied_actions_not_promoted(self):
        for case in ("unknown", "excluded", "policy"):
            with self.subTest(case=case):
                kw = make_input()
                if case == "unknown":
                    kw["requested_action"] = "merge"
                elif case == "excluded":
                    # Scope identity is source hash bound; an approved action
                    # cannot be smuggled in via an untrusted mutated list.
                    kw["scope_identity"]["excluded_actions"] = ["run_sandboxed_validation"]
                else:
                    kw["gate_policy"] = {"action_map": {"run_sandboxed_validation": "G0_CONTEXT"}}
                with self.assertRaises(G2PreparationBlocked):
                    prepare_g2_approval(**kw)

    def test_scrum809_canonical_development_action_can_prepare_nonexecuting_request(self):
        kw = make_input()
        kw["scope_identity"] = GS.scope(
            head_sha=BASE, authorized_actions=["modify_approved_files"])
        kw["requested_action"] = "modify_approved_files"
        result = prepare_g2_approval(**kw)
        assert result["status"] == "AWAITING_HUMAN_APPROVAL"
        assert result["pending_g2_envelope"]["activation_state"] == "AWAITING_APPROVAL"
        assert result["pending_g2_envelope"]["execution_started"] is False
        assert result["authority_boundary_decision"]["write_authority_granted"] is False

    def test_foreign_scope_or_changed_base_denied(self):
        for variant in ("base", "task", "hash", "risk"):
            with self.subTest(variant=variant):
                kw = make_input()
                if variant == "base":
                    kw["current_base_sha"] = "b" * 40
                if variant == "task":
                    kw["task_id"] = "SCRUM-841"
                if variant == "hash":
                    kw["scope_identity"]["scope_hash"] = "sha256:" + "f" * 64
                if variant == "risk":
                    kw["scope_identity"]["risk_class"] = "R3"
                with self.assertRaises(G2PreparationBlocked):
                    prepare_g2_approval(**kw)

    def test_missing_or_expired_human_request_denied(self):
        for variant in ("actor", "expiry"):
            kw = make_input()
            if variant == "actor":
                kw["actor_target"] = {}
            else:
                kw["expires_at"] = "2026-10-16T00:00:00Z"
            with self.subTest(variant=variant):
                with self.assertRaises(ValueError):
                    prepare_g2_approval(**kw)

    def test_no_forged_approval_can_activate_blocked_gate(self):
        kw = make_input()
        res = prepare_g2_approval(**kw)
        env = res["pending_g2_envelope"]
        # A spoofed VALID response is not enough: native gate_state still
        # lacks the completed G2 envelope and is correctly BLOCKED.
        from tools.node_architect.g2_execution_envelope_render import (
            render_g2_execution_envelope,
        )
        val = {
            "outcome": "VALID", "scope_hash": kw["scope_identity"]["scope_hash"],
            "task_id": TASK, "repository": REPO, "base_sha": BASE,
            "working_branch": kw["scope_identity"]["working_branch"],
            "risk_class": "R2",
            "authorized_actions": list(kw["scope_identity"]["authorized_actions"]),
        }
        act = render_g2_execution_envelope(
            task_id=TASK, repository=REPO, base_ref=kw["scope_identity"]["base_ref"],
            base_sha=BASE,
            risk_profile={"risk_class": "R2",
                          "risk_digest": kw["risk_profile"]["decision_digest"]},
            bounded_read_scope={"paths": []},
            bounded_write_scope={
                "working_branch": kw["scope_identity"]["working_branch"],
                "paths": kw["scope_identity"]["authorized_paths"],
                "authorized_actions": kw["scope_identity"]["authorized_actions"],
            },
            scope_identity=kw["scope_identity"],
            gate_state_resolution=res["gate_state_resolution"],
            authority_boundary_decision=res["authority_boundary_decision"],
            evidence_map=kw["evidence_map"],
            approval_request=res["approval_request"],
            approval_validation=val,
            checkpoint={"checkpoint_id": kw["checkpoint_id"]},
            rendered_at=kw["issued_at"],
        )
        self.assertEqual(act["activation_state"], "BLOCKED")
        self.assertFalse(act["execution_started"])
        self.assertNotEqual(env["envelope_digest"], act["envelope_digest"])

    def test_prior_state_replay_conflict_denied(self):
        kw = make_input()
        first = prepare_g2_approval(**kw)
        prior = copy.deepcopy(first["gate_state_resolution"])
        # Same event, different semantic digest cannot be reused.
        prior["resolution_digest"] = "sha256:" + "0" * 64
        kw["prior_resolution"] = prior
        with self.assertRaises(G2PreparationBlocked):
            prepare_g2_approval(**kw)


if __name__ == "__main__":
    unittest.main()
