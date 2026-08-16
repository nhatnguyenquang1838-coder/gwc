"""M5 tests for deterministic G2 execution envelope rendering (SCRUM-191)."""
from __future__ import annotations

import copy
import unittest

from tools.node_architect.g2_execution_envelope_render import (
    render_g2_execution_envelope,
)

_SCOPE = "sha256:" + "a" * 64
_RISK_DIGEST = "sha256:" + "b" * 64


def _base_kwargs(approval_request=None, approval_validation=None, bind=True):
    # Producer-shaped happy-path defaults so ACTIVE is reachable: each required
    # input carries its canonical *accepted* state (same keys the producers emit).
    base = dict(
        task_id="SCRUM-191",
        repository="nhatnguyenquang1838-coder/gwc",
        base_ref="main",
        base_sha="54fcc4c5395d0b3dabfe0564d5b3f8ad8daa3337",
        risk_profile={"risk_class": "R2", "risk_digest": _RISK_DIGEST},
        bounded_read_scope={"paths": [".gwc/tasks/SCRUM-191/**"]},
        bounded_write_scope={
            "working_branch": "hermes/scrum-191-x",
            "paths": ["schemas/g2-execution-envelope.schema.json",
                      "tools/node_architect/g2_execution_envelope_render.py"],
            "authorized_actions": ["create_working_branch", "add_files",
                                    "run_sandboxed_validation", "stage_commit_push"],
        },
        scope_identity={"scope_hash": _SCOPE},
        # gate_state_resolution: canonical PASS / NO_DRIFT / not replay-conflicted,
        # carrying its real top-level identity (task_id, repository,
        # current_base_sha, scope_hash).
        gate_state_resolution={
            "task_id": "SCRUM-191",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "current_base_sha": "54fcc4c5395d0b3dabfe0564d5b3f8ad8daa3337",
            "scope_hash": _SCOPE,
            "gate_status": "PASS",
            "drift_decision": {"status": "NO_DRIFT", "reason_codes": []},
            "replay_status": "FIRST_SEEN",
            "reason_codes": ["GATE_STATE_RESOLVED", "GATE_STATE_G6_NOT_APPLICABLE"],
        },
        # authority_boundary_decision: decision REQUIRE_APPROVAL, not prohibited,
        # with its real top-level identity + nested scope_identity (which carries
        # task/repo/base/scope/risk/branch/actions identity for this G2 render).
        authority_boundary_decision={
            "decision": "REQUIRE_APPROVAL",
            "approval_required": True,
            "prohibited": False,
            "replay_status": "FIRST_SEEN",
            "stale_evidence": False,
            "reason_codes": ["AUTHORITY_APPROVAL_REQUIRED"],
            "task_id": "SCRUM-191",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "current_base_sha": "54fcc4c5395d0b3dabfe0564d5b3f8ad8daa3337",
            "scope_hash": _SCOPE,
            "risk_class": "R2",
            "scope_identity": {
                "task_id": "SCRUM-191",
                "repository": "nhatnguyenquang1838-coder/gwc",
                "base_sha": "54fcc4c5395d0b3dabfe0564d5b3f8ad8daa3337",
                "head_sha": "54fcc4c5395d0b3dabfe0564d5b3f8ad8daa3337",
                "scope_hash": _SCOPE,
                "working_branch": "hermes/scrum-191-x",
                "authorized_actions": ["create_working_branch", "add_files",
                                       "run_sandboxed_validation", "stage_commit_push"],
            },
        },
        # evidence_artifact_map: READY with no blocker reasons / missing / stale.
        # Real emitted identity = task_id / repository / base_sha (no scope_hash).
        evidence_map={
            "task_id": "SCRUM-191",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "base_sha": "54fcc4c5395d0b3dabfe0564d5b3f8ad8daa3337",
            "outcome": "READY",
            "reason_codes": ["EVIDENCE_MAP_READY"],
            "missing_required": [],
            "stale_required": [],
            "projection_only": [],
            "f1_artifact_digests": {"g0": "sha256:" + "c" * 64},
        },
        approval_request=approval_request or {
            "issued_at": "2026-08-05T22:40:00Z",
            "expires_at": "2026-08-06T22:40:00Z",
        },
        checkpoint=dict(checkpoint_id="ck-191-1"),
    )
    # Always pass approval_validation explicitly (renderer requires it); it may be
    # None or a non-dict (both fail closed inside the renderer). When bind=True an
    # explicit VALID approval has every material binding injected + overridable.
    base["approval_validation"] = approval_validation
    if approval_validation is not None and bind:
        base["approval_validation"] = {
            "outcome": "VALID",
            "scope_hash": _SCOPE,
            "task_id": "SCRUM-191",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "base_sha": "54fcc4c5395d0b3dabfe0564d5b3f8ad8daa3337",
            "working_branch": "hermes/scrum-191-x",
            "risk_class": "R2",
            "authorized_actions": ["create_working_branch", "add_files",
                                   "run_sandboxed_validation", "stage_commit_push"],
            **approval_validation,
        }
    return base


class TestRenderingShape(unittest.TestCase):
    def test_closed_schema_keys(self):
        env = render_g2_execution_envelope(**_base_kwargs())
        required = ["schema_version", "artifact_type", "activation_state",
                    "task_id", "repository", "base_sha", "scope_hash",
                    "checkpoint_id", "issued_at", "expires_at",
                    "envelope_digest", "exclusions", "execution_started"]
        for k in required:
            self.assertIn(k, env)
        self.assertEqual(env["artifact_type"], "g2-execution-envelope")
        self.assertEqual(env["execution_started"], False)
        self.assertEqual(env["exclusions"], ["G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION"])

    def test_excluded_later_gates_present(self):
        env = render_g2_execution_envelope(**_base_kwargs())
        for a in ["open_draft_pr", "mark_pr_ready", "merge", "auto_merge",
                  "force_push", "branch_deletion", "protected_branch_write",
                  "deploy", "release", "production_data_change",
                  "production_config_change", "g3_pr_promotion", "g4_merge",
                  "g5_deploy", "g6_production"]:
            self.assertIn(a, env["excluded_actions"])


class TestActivationStates(unittest.TestCase):
    def test_awaiting_when_no_validation(self):
        env = render_g2_execution_envelope(**_base_kwargs(approval_validation=None))
        self.assertEqual(env["activation_state"], "AWAITING_APPROVAL")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AWAITING_APPROVAL")

    def test_active_when_valid_and_scope_match(self):
        av = {"outcome": "VALID", "scope_hash": _SCOPE}
        env = render_g2_execution_envelope(**_base_kwargs(approval_validation=av))
        self.assertEqual(env["activation_state"], "ACTIVE")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_ACTIVE")

    def test_blocked_when_validation_invalid(self):
        av = {"outcome": "INVALID", "scope_hash": _SCOPE}
        env = render_g2_execution_envelope(**_base_kwargs(approval_validation=av))
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_APPROVAL_INVALID")

    def test_blocked_when_scope_drift(self):
        av = {"outcome": "VALID", "scope_hash": "sha256:" + "d" * 64}
        env = render_g2_execution_envelope(**_base_kwargs(approval_validation=av))
        self.assertEqual(env["activation_state"], "BLOCKED")


class TestExpiryAndIntegrity(unittest.TestCase):
    def test_expired(self):
        req = {"issued_at": "2026-08-05T22:40:00Z", "expires_at": "2026-08-06T22:40:00Z"}
        av = {"outcome": "VALID", "scope_hash": _SCOPE}
        env = render_g2_execution_envelope(
            **_base_kwargs(approval_request=req, approval_validation=av),
            rendered_at="2026-08-07T00:00:00Z")
        self.assertEqual(env["activation_state"], "EXPIRED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_EXPIRED")

    def test_scope_hash_must_be_sha256(self):
        bad = copy.deepcopy(_base_kwargs())
        bad["scope_identity"] = {"scope_hash": "not-a-hash"}
        with self.assertRaises(ValueError):
            render_g2_execution_envelope(**bad)

    def test_replay_deterministic(self):
        a = render_g2_execution_envelope(**_base_kwargs())
        b = render_g2_execution_envelope(**_base_kwargs())
        self.assertEqual(a["envelope_digest"], b["envelope_digest"])

    def test_no_secret_leakage(self):
        env = render_g2_execution_envelope(**_base_kwargs())
        blob = repr(env).lower()
        for secret in ["token", "secret", "password", "credential", "api_key"]:
            self.assertNotIn(secret, blob)


class TestS1FailClosedBindingSCRUM314(unittest.TestCase):
    """SCRUM-314: ACTIVE is impossible unless the approval asserts and matches
    every material binding; any missing/ambiguous/mismatched/stale binding
    (wrong task/base/branch/risk/action/scope) fails closed to BLOCKED."""

    def test_accepted_current_inputs_are_usable_envelope(self):
        env = render_g2_execution_envelope(
            **_base_kwargs(approval_validation={"outcome": "VALID", "scope_hash": _SCOPE}))
        self.assertEqual(env["activation_state"], "ACTIVE")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_ACTIVE")
        self.assertEqual(env["execution_started"], False)
        for a in ["g3_pr_promotion", "g4_merge", "g5_deploy", "g6_production"]:
            self.assertIn(a, env["excluded_actions"])

    def test_blocked_when_task_mismatch(self):
        env = render_g2_execution_envelope(
            **_base_kwargs(approval_validation={"outcome": "VALID",
                                               "scope_hash": _SCOPE,
                                               "task_id": "SCRUM-999"}))
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_BINDING_MISMATCH")

    def test_blocked_when_base_sha_mismatch(self):
        env = render_g2_execution_envelope(
            **_base_kwargs(approval_validation={"outcome": "VALID",
                                               "scope_hash": _SCOPE,
                                               "base_sha": "0" * 40}))
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_BINDING_MISMATCH")

    def test_blocked_when_working_branch_mismatch(self):
        env = render_g2_execution_envelope(
            **_base_kwargs(approval_validation={"outcome": "VALID",
                                               "scope_hash": _SCOPE,
                                               "working_branch": "auto/SCRUM-000-x"}))
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_BINDING_MISMATCH")

    def test_blocked_when_risk_class_mismatch(self):
        env = render_g2_execution_envelope(
            **_base_kwargs(approval_validation={"outcome": "VALID",
                                               "scope_hash": _SCOPE,
                                               "risk_class": "R9"}))
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_BINDING_MISMATCH")

    def test_blocked_when_authorized_actions_mismatch(self):
        env = render_g2_execution_envelope(
            **_base_kwargs(approval_validation={"outcome": "VALID",
                                               "scope_hash": _SCOPE,
                                               "authorized_actions": ["create_working_branch"]}))
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_BINDING_MISMATCH")

    def test_blocked_when_approval_ambiguous_missing_outcome(self):
        env = render_g2_execution_envelope(
            **_base_kwargs(approval_validation={"scope_hash": _SCOPE}, bind=False))
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_APPROVAL_AMBIGUOUS")

    def test_blocked_when_approval_validation_not_a_dict(self):
        env = render_g2_execution_envelope(
            **_base_kwargs(approval_validation="not-a-dict", bind=False))
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_APPROVAL_AMBIGUOUS")

    def test_digest_changes_on_material_drift(self):
        a = render_g2_execution_envelope(
            **_base_kwargs(approval_validation={"outcome": "VALID", "scope_hash": _SCOPE}))
        b = render_g2_execution_envelope(
            **_base_kwargs(approval_validation={"outcome": "VALID",
                                               "scope_hash": _SCOPE,
                                               "base_sha": "f" * 40}))
        self.assertNotEqual(a["envelope_digest"], b["envelope_digest"])

    def test_replay_deterministic_after_hardening(self):
        a = render_g2_execution_envelope(
            **_base_kwargs(approval_validation={"outcome": "VALID", "scope_hash": _SCOPE}))
        b = render_g2_execution_envelope(
            **_base_kwargs(approval_validation={"outcome": "VALID", "scope_hash": _SCOPE}))
        self.assertEqual(a["envelope_digest"], b["envelope_digest"])


class TestS2RequiredInputFailClosedSCRUM314(unittest.TestCase):
    """SCRUM-314 S2 repair (independent-review intercept): a VALID approval must
    NOT reach ACTIVE while any required input (gate_state_resolution,
    authority_boundary_decision, evidence_artifact_map) is in a blocking,
    stale, drifted, replay-conflicted, prohibited, or malformed state. Each case
    fails closed to BLOCKED with its own reason code. Canonical blocker
    semantics mirror the producer modules (gate_state_resolution.py /
    authority_boundary_check.py / evidence_artifact_map.py)."""

    def _accepted(self):
        return _base_kwargs(approval_validation={"outcome": "VALID", "scope_hash": _SCOPE})

    # ---- gate_state_resolution ----
    def test_blocked_when_gate_state_failed(self):
        kw = self._accepted()
        kw["gate_state_resolution"] = dict(kw["gate_state_resolution"])
        kw["gate_state_resolution"]["gate_status"] = "FAILED"
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_GATE_STATE_BLOCKED")

    def test_blocked_when_gate_state_blocked(self):
        kw = self._accepted()
        kw["gate_state_resolution"] = dict(kw["gate_state_resolution"])
        kw["gate_state_resolution"]["gate_status"] = "BLOCKED"
        kw["gate_state_resolution"]["reason_codes"] = ["GATE_STATE_REQUIRED_EVIDENCE_MISSING"]
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_GATE_STATE_BLOCKED")

    def test_blocked_when_gate_state_drift(self):
        kw = self._accepted()
        kw["gate_state_resolution"] = dict(kw["gate_state_resolution"])
        kw["gate_state_resolution"]["drift_decision"] = {
            "status": "REAPPROVE", "reason_codes": ["BASE_SHA_DRIFT"]}
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_GATE_STATE_BLOCKED")

    def test_blocked_when_gate_state_evidence_stale(self):
        kw = self._accepted()
        kw["gate_state_resolution"] = dict(kw["gate_state_resolution"])
        kw["gate_state_resolution"]["reason_codes"] = ["GATE_STATE_EVIDENCE_STALE"]
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_GATE_STATE_BLOCKED")

    def test_blocked_when_gate_state_replay_conflict(self):
        kw = self._accepted()
        kw["gate_state_resolution"] = dict(kw["gate_state_resolution"])
        kw["gate_state_resolution"]["replay_status"] = "REPLAY_CONFLICT"
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_GATE_STATE_BLOCKED")

    def test_blocked_when_gate_state_not_a_dict(self):
        kw = self._accepted()
        kw["gate_state_resolution"] = "not-a-dict"
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_GATE_STATE_BLOCKED")

    # ---- authority_boundary_decision ----
    def test_blocked_when_authority_decision_block(self):
        kw = self._accepted()
        kw["authority_boundary_decision"] = dict(kw["authority_boundary_decision"])
        kw["authority_boundary_decision"]["decision"] = "BLOCK"
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_BLOCKED")

    def test_blocked_when_authority_prohibited(self):
        kw = self._accepted()
        kw["authority_boundary_decision"] = dict(kw["authority_boundary_decision"])
        kw["authority_boundary_decision"]["prohibited"] = True
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_BLOCKED")

    def test_blocked_when_authority_replay_conflict(self):
        kw = self._accepted()
        kw["authority_boundary_decision"] = dict(kw["authority_boundary_decision"])
        kw["authority_boundary_decision"]["replay_status"] = "REPLAY_CONFLICT"
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_BLOCKED")

    def test_blocked_when_authority_stale_evidence(self):
        kw = self._accepted()
        kw["authority_boundary_decision"] = dict(kw["authority_boundary_decision"])
        kw["authority_boundary_decision"]["stale_evidence"] = True
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_BLOCKED")

    def test_blocked_when_authority_not_a_dict(self):
        kw = self._accepted()
        kw["authority_boundary_decision"] = None
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_BLOCKED")

    # ---- evidence_artifact_map ----
    def test_blocked_when_evidence_outcome_blocked(self):
        kw = self._accepted()
        kw["evidence_map"] = dict(kw["evidence_map"])
        kw["evidence_map"]["outcome"] = "BLOCKED"
        kw["evidence_map"]["reason_codes"] = ["EVIDENCE_REQUIRED_MISSING"]
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_EVIDENCE_BLOCKED")

    def test_blocked_when_evidence_stale(self):
        kw = self._accepted()
        kw["evidence_map"] = dict(kw["evidence_map"])
        kw["evidence_map"]["reason_codes"] = ["EVIDENCE_STALE"]
        kw["evidence_map"]["stale_required"] = [".gwc/tasks/SCRUM-191/g0/context-snapshot.yaml"]
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_EVIDENCE_BLOCKED")

    def test_blocked_when_evidence_required_missing(self):
        kw = self._accepted()
        kw["evidence_map"] = dict(kw["evidence_map"])
        kw["evidence_map"]["reason_codes"] = ["EVIDENCE_REQUIRED_MISSING"]
        kw["evidence_map"]["missing_required"] = [".gwc/tasks/SCRUM-191/g1/intake/g1-intake-brief.yaml"]
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_EVIDENCE_BLOCKED")

    def test_blocked_when_evidence_conflict(self):
        kw = self._accepted()
        kw["evidence_map"] = dict(kw["evidence_map"])
        kw["evidence_map"]["reason_codes"] = ["EVIDENCE_CONFLICT"]
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_EVIDENCE_BLOCKED")

    def test_blocked_when_evidence_not_a_dict(self):
        kw = self._accepted()
        kw["evidence_map"] = "not-a-dict"
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_EVIDENCE_BLOCKED")

    # ---- digest must change with material input, not merely bindings ----
    def test_digest_changes_when_gate_state_blocks(self):
        a = render_g2_execution_envelope(**self._accepted())
        kw = self._accepted()
        kw["gate_state_resolution"] = dict(kw["gate_state_resolution"])
        kw["gate_state_resolution"]["gate_status"] = "BLOCKED"
        b = render_g2_execution_envelope(**kw)
        self.assertNotEqual(a["envelope_digest"], b["envelope_digest"])

    def test_digest_changes_when_evidence_blocks(self):
        a = render_g2_execution_envelope(**self._accepted())
        kw = self._accepted()
        kw["evidence_map"] = dict(kw["evidence_map"])
        kw["evidence_map"]["reason_codes"] = ["EVIDENCE_STALE"]
        kw["evidence_map"]["stale_required"] = ["x"]
        b = render_g2_execution_envelope(**kw)
        self.assertNotEqual(a["envelope_digest"], b["envelope_digest"])


class TestS2RequiredInputIdentitySCRUM314(unittest.TestCase):
    """SCRUM-314 final identity-gap repair (controller intercept d836): a VALID
    approval must NOT reach ACTIVE when any required producer input's *identity*
    (task/repo/base/scope/risk/branch/actions) is missing or belongs to another
    task. Identity is read from each producer's real emitted keys:
      - gate_state_resolution: task_id, repository, current_base_sha, scope_hash
      - authority_boundary_decision: task_id, repository, current_base_sha,
        scope_hash, risk_class + nested scope_identity (task/repo/base/scope/
        branch/actions)
      - evidence_artifact_map: task_id, repository, base_sha (no scope_hash)
    A generic NOT_APPLICABLE is never accepted by name alone (fail closed)."""

    def _accepted(self):
        return _base_kwargs(approval_validation={"outcome": "VALID", "scope_hash": _SCOPE})

    # ---- gate_state_resolution identity ----
    def test_blocked_when_gate_identity_foreign_task(self):
        kw = self._accepted()
        kw["gate_state_resolution"] = dict(kw["gate_state_resolution"])
        kw["gate_state_resolution"]["task_id"] = "SCRUM-999"
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_GATE_STATE_IDENTITY_MISMATCH")

    def test_blocked_when_gate_identity_foreign_base(self):
        kw = self._accepted()
        kw["gate_state_resolution"] = dict(kw["gate_state_resolution"])
        kw["gate_state_resolution"]["current_base_sha"] = "0" * 40
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_GATE_STATE_IDENTITY_MISMATCH")

    def test_blocked_when_gate_identity_missing_fields(self):
        kw = self._accepted()
        g = dict(kw["gate_state_resolution"])
        del g["task_id"]
        del g["repository"]
        kw["gate_state_resolution"] = g
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_GATE_STATE_IDENTITY_MISMATCH")

    def test_blocked_when_gate_status_not_applicable(self):
        # Generic NOT_APPLICABLE is never accepted by name alone -> fail closed.
        kw = self._accepted()
        kw["gate_state_resolution"] = dict(kw["gate_state_resolution"])
        kw["gate_state_resolution"]["gate_status"] = "NOT_APPLICABLE"
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_GATE_STATE_BLOCKED")

    # ---- authority_boundary_decision identity ----
    def test_blocked_when_authority_identity_foreign_task(self):
        kw = self._accepted()
        kw["authority_boundary_decision"] = dict(kw["authority_boundary_decision"])
        kw["authority_boundary_decision"]["task_id"] = "SCRUM-999"
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_blocked_when_authority_identity_foreign_base(self):
        kw = self._accepted()
        kw["authority_boundary_decision"] = dict(kw["authority_boundary_decision"])
        kw["authority_boundary_decision"]["current_base_sha"] = "0" * 40
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_blocked_when_authority_identity_foreign_scope(self):
        kw = self._accepted()
        kw["authority_boundary_decision"] = dict(kw["authority_boundary_decision"])
        kw["authority_boundary_decision"]["scope_hash"] = "sha256:" + "f" * 64
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_blocked_when_authority_identity_foreign_risk_class(self):
        kw = self._accepted()
        kw["authority_boundary_decision"] = dict(kw["authority_boundary_decision"])
        kw["authority_boundary_decision"]["risk_class"] = "R9"
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_blocked_when_authority_scope_identity_foreign_branch(self):
        kw = self._accepted()
        si = dict(kw["authority_boundary_decision"]["scope_identity"])
        si["working_branch"] = "auto/SCRUM-000-x"
        kw["authority_boundary_decision"] = dict(kw["authority_boundary_decision"])
        kw["authority_boundary_decision"]["scope_identity"] = si
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_blocked_when_authority_scope_identity_foreign_actions(self):
        kw = self._accepted()
        si = dict(kw["authority_boundary_decision"]["scope_identity"])
        si["authorized_actions"] = ["create_working_branch", "g3_pr_promotion"]
        kw["authority_boundary_decision"] = dict(kw["authority_boundary_decision"])
        kw["authority_boundary_decision"]["scope_identity"] = si
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_blocked_when_authority_identity_missing_fields(self):
        kw = self._accepted()
        a = dict(kw["authority_boundary_decision"])
        del a["task_id"]
        del a["current_base_sha"]
        kw["authority_boundary_decision"] = a
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_blocked_when_authority_decision_not_applicable(self):
        # Generic NOT_APPLICABLE is never accepted by name alone -> fail closed.
        kw = self._accepted()
        kw["authority_boundary_decision"] = dict(kw["authority_boundary_decision"])
        kw["authority_boundary_decision"]["decision"] = "NOT_APPLICABLE"
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_BLOCKED")

    # ---- micro-intercept 121a: strict authority schema identity ----
    def test_blocked_when_authority_missing_scope_identity(self):
        kw = self._accepted()
        a = dict(kw["authority_boundary_decision"])
        del a["scope_identity"]
        kw["authority_boundary_decision"] = a
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_blocked_when_authority_scope_identity_not_dict(self):
        kw = self._accepted()
        a = dict(kw["authority_boundary_decision"])
        a["scope_identity"] = "not-a-dict"
        kw["authority_boundary_decision"] = a
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_blocked_when_authority_missing_risk_class(self):
        kw = self._accepted()
        a = dict(kw["authority_boundary_decision"])
        del a["risk_class"]
        kw["authority_boundary_decision"] = a
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_blocked_when_authority_risk_class_mismatch(self):
        kw = self._accepted()
        a = dict(kw["authority_boundary_decision"])
        a["risk_class"] = "R9"
        kw["authority_boundary_decision"] = a
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_blocked_when_authority_scope_identity_missing_required_key(self):
        # Drop a required nested key (head_sha) -> malformed -> fail closed.
        kw = self._accepted()
        a = dict(kw["authority_boundary_decision"])
        si = dict(a["scope_identity"])
        del si["head_sha"]
        a["scope_identity"] = si
        kw["authority_boundary_decision"] = a
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_blocked_when_authority_actions_subset(self):
        # Fewer actions than the envelope = authority expansion -> rejected.
        kw = self._accepted()
        a = dict(kw["authority_boundary_decision"])
        si = dict(a["scope_identity"])
        si["authorized_actions"] = ["create_working_branch", "add_files"]
        a["scope_identity"] = si
        kw["authority_boundary_decision"] = a
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_blocked_when_authority_actions_superset(self):
        # More actions than the envelope = over-privilege -> rejected.
        kw = self._accepted()
        a = dict(kw["authority_boundary_decision"])
        si = dict(a["scope_identity"])
        si["authorized_actions"] = list(si["authorized_actions"]) + ["g4_pr_merge"]
        a["scope_identity"] = si
        kw["authority_boundary_decision"] = a
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH")

    def test_active_when_authority_actions_reordered(self):
        # Same actions in a different order are still exactly equal -> ACTIVE.
        kw = self._accepted()
        a = dict(kw["authority_boundary_decision"])
        si = dict(a["scope_identity"])
        si["authorized_actions"] = list(reversed(si["authorized_actions"]))
        a["scope_identity"] = si
        kw["authority_boundary_decision"] = a
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "ACTIVE")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_ACTIVE")

    # ---- evidence_artifact_map identity ----
    def test_blocked_when_evidence_identity_foreign_task(self):
        kw = self._accepted()
        kw["evidence_map"] = dict(kw["evidence_map"])
        kw["evidence_map"]["task_id"] = "SCRUM-999"
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_EVIDENCE_IDENTITY_MISMATCH")

    def test_blocked_when_evidence_identity_foreign_repo(self):
        kw = self._accepted()
        kw["evidence_map"] = dict(kw["evidence_map"])
        kw["evidence_map"]["repository"] = "other-org/other-repo"
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_EVIDENCE_IDENTITY_MISMATCH")

    def test_blocked_when_evidence_identity_foreign_base(self):
        kw = self._accepted()
        kw["evidence_map"] = dict(kw["evidence_map"])
        kw["evidence_map"]["base_sha"] = "0" * 40
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_EVIDENCE_IDENTITY_MISMATCH")

    def test_blocked_when_evidence_identity_missing_fields(self):
        kw = self._accepted()
        e = dict(kw["evidence_map"])
        del e["task_id"]
        del e["repository"]
        kw["evidence_map"] = e
        env = render_g2_execution_envelope(**kw)
        self.assertEqual(env["activation_state"], "BLOCKED")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_EVIDENCE_IDENTITY_MISMATCH")

    # ---- happy path: real producer-shaped current inputs activate ----
    def test_active_when_all_identities_current(self):
        env = render_g2_execution_envelope(**self._accepted())
        self.assertEqual(env["activation_state"], "ACTIVE")
        self.assertEqual(env["reason_code"], "G2_ENVELOPE_ACTIVE")
        self.assertEqual(env["execution_started"], False)

    # ---- digest must change when a required input carries foreign identity ----
    def test_digest_changes_when_gate_identity_foreign(self):
        a = render_g2_execution_envelope(**self._accepted())
        kw = self._accepted()
        kw["gate_state_resolution"] = dict(kw["gate_state_resolution"])
        kw["gate_state_resolution"]["task_id"] = "SCRUM-999"
        b = render_g2_execution_envelope(**kw)
        self.assertNotEqual(a["envelope_digest"], b["envelope_digest"])

    def test_digest_changes_when_evidence_identity_foreign(self):
        a = render_g2_execution_envelope(**self._accepted())
        kw = self._accepted()
        kw["evidence_map"] = dict(kw["evidence_map"])
        kw["evidence_map"]["task_id"] = "SCRUM-999"
        b = render_g2_execution_envelope(**kw)
        self.assertNotEqual(a["envelope_digest"], b["envelope_digest"])


if __name__ == "__main__":
    unittest.main()
