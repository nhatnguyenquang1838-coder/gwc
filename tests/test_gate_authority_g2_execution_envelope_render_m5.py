"""M5 tests for deterministic G2 execution envelope rendering (SCRUM-191)."""
from __future__ import annotations

import copy
import unittest

from tools.node_architect.g2_execution_envelope_render import (
    render_g2_execution_envelope,
)

_SCOPE = "sha256:" + "a" * 64
_RISK_DIGEST = "sha256:" + "b" * 64


def _base_kwargs(approval_request=None, approval_validation=None):
    return dict(
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
        gate_state_resolution={"gate": "G2", "state": "AWAITING"},
        authority_boundary_decision={"excluded": ["G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION"]},
        evidence_map={"f1_artifact_digests": {"g0": "sha256:" + "c" * 64}},
        approval_request=approval_request or {
            "issued_at": "2026-08-05T22:40:00Z",
            "expires_at": "2026-08-06T22:40:00Z",
        },
        approval_validation=approval_validation,
        checkpoint={"checkpoint_id": "ck-191-1"},
    )


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


if __name__ == "__main__":
    unittest.main()
