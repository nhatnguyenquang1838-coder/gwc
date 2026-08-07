#!/usr/bin/env python3
"""Tests for the ai-task-execution adapter (SCRUM-273).

Covers acceptance criteria AC-1..AC-6 using the DeterministicFakeProvider so the
contract is fully reproducible in CI without network or real agents.
"""
from __future__ import annotations

import copy
import importlib
import unittest

from tools.node_architect.ai_agent_adapter import (
    DeterministicFakeProvider,
    ProviderTimeout,
    ProviderUnavailable,
    execute,
)
from tools.node_architect.build_node_instruction_pack import build_node_instruction_pack
from tools.node_architect.validate_ai_agent_result import validate_ai_agent_result


def _base_request(**overrides) -> dict:
    req = {
        "schema_version": "1.0",
        "run_id": "run-273-1",
        "task_id": "SCRUM-273",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "preprod_base_sha": "f002859c5ea65850aa2b5449e1a2013d294ea3c9",
        "working_branch": "hermes/scrum-273-ai-agent-adapter-20260807",
        "scope_hash": "sha256:" + "a" * 64,
        "graph_revision": "graph-1",
        "policy_revision": "v1.0-20260807",
        "allowed_paths": [
            "tools/node_architect/scratch/foo.py",
            "tests/scratch/test_foo.py",
        ],
        "prohibited_paths": ["core/node-architect"],
        "authorized_actions": ["modify_approved_files", "create_commit"],
        "validation_commands": ["python -m pytest tests/scratch"],
        "idempotency_key": "idem-273-1",
    }
    req.update(overrides)
    return req


class RequestSchemaTest(unittest.TestCase):
    def test_request_pack_builds(self):
        pack = build_node_instruction_pack(_base_request())
        self.assertEqual(pack.task_id, "SCRUM-273")
        self.assertTrue(pack.content_digest.startswith("sha256:"))


class AC1FakeCompletes(unittest.TestCase):
    def test_deterministic_fake_success(self):
        store: dict = {}
        provider = DeterministicFakeProvider(
            changed_paths=["tools/node_architect/scratch/foo.py"],
            recorded_actions=["modify_approved_files"],
        )
        result = execute(_base_request(), provider=provider, idempotency_store=store)
        self.assertEqual(result["terminal_outcome"], "SUCCESS")
        self.assertIn("tools/node_architect/scratch/foo.py", result["changed_paths"])
        # Schema-valid (re-validate through the validator).
        errs = validate_ai_agent_result(
            result,
            request_identity=build_node_instruction_pack(_base_request()),
            authorized_actions=["modify_approved_files", "create_commit"],
            allowed_paths=["tools/node_architect/scratch/foo.py", "tests/scratch/test_foo.py"],
            prohibited_paths=["core/node-architect"],
        )
        self.assertEqual(errs, [])


class AC2FailClosed(unittest.TestCase):
    def test_out_of_scope_path(self):
        provider = DeterministicFakeProvider(
            changed_paths=["core/node-architect/secret.py"],  # not allowed
            recorded_actions=["modify_approved_files"],
        )
        result = execute(_base_request(), provider=provider, idempotency_store={})
        self.assertEqual(result["terminal_outcome"], "OUT_OF_SCOPE")
        self.assertFalse(result["g3_g4_g5_authority_granted"])

    def test_unknown_action(self):
        provider = DeterministicFakeProvider(
            changed_paths=["tools/node_architect/scratch/foo.py"],
            recorded_actions=["force_push"],  # not authorized
        )
        result = execute(_base_request(), provider=provider, idempotency_store={})
        self.assertEqual(result["terminal_outcome"], "OUT_OF_SCOPE")

    def test_malformed_output(self):
        provider = DeterministicFakeProvider(malformed=True)
        result = execute(_base_request(), provider=provider, idempotency_store={})
        self.assertEqual(result["terminal_outcome"], "MALFORMED_OUTPUT")

    def test_provider_timeout(self):
        provider = DeterministicFakeProvider(raise_timeout=True)
        result = execute(_base_request(), provider=provider, idempotency_store={})
        self.assertEqual(result["terminal_outcome"], "TIMEOUT")

    def test_provider_unavailable(self):
        provider = DeterministicFakeProvider(raise_unavailable=True)
        result = execute(_base_request(), provider=provider, idempotency_store={})
        self.assertEqual(result["terminal_outcome"], "FAIL_CLOSED")


class AC3NoHiddenFallback(unittest.TestCase):
    def test_no_fallback_used(self):
        # CustomRunnerProvider with no runner wired in must fail closed, not fallback.
        from tools.node_architect.ai_agent_adapter import CustomRunnerProvider

        provider = CustomRunnerProvider(run_fn=None)
        with self.assertRaises(ProviderUnavailable):
            provider.run(build_node_instruction_pack(_base_request()))
        result = execute(_base_request(), provider=provider, idempotency_store={})
        self.assertEqual(result["terminal_outcome"], "FAIL_CLOSED")
        self.assertIn("provider_unavailable", " ".join(result["findings"]))


class AC4NoG3G4G5Authority(unittest.TestCase):
    def test_authority_never_granted(self):
        provider = DeterministicFakeProvider(
            changed_paths=["tools/node_architect/scratch/foo.py"],
            recorded_actions=["modify_approved_files"],
        )
        result = execute(_base_request(), provider=provider, idempotency_store={})
        self.assertFalse(result["g3_g4_g5_authority_granted"])
        # The validator must forbid any recorded forbidden authority action. Build a
        # synthetic result that carries a forbidden recorded action and confirm rejection.
        bad = dict(result)
        bad["recorded_actions"] = ["merge_approved_pr"]
        errs = validate_ai_agent_result(
            bad,
            request_identity=build_node_instruction_pack(_base_request()),
            authorized_actions=["modify_approved_files", "create_commit"],
            allowed_paths=["tools/node_architect/scratch/foo.py"],
            prohibited_paths=["core/node-architect"],
        )
        self.assertTrue(any("forbidden_authority_action" in e for e in errs))


class AC5IdempotencyReplay(unittest.TestCase):
    def test_same_key_same_digest_returns_prior(self):
        store: dict = {}
        provider = DeterministicFakeProvider(
            changed_paths=["tools/node_architect/scratch/foo.py"],
            recorded_actions=["modify_approved_files"],
        )
        r1 = execute(_base_request(), provider=provider, idempotency_store=store)
        # Different provider instance, same request => prior result returned.
        provider2 = DeterministicFakeProvider(
            changed_paths=["tools/node_architect/scratch/foo.py"],
            recorded_actions=["modify_approved_files"],
        )
        r2 = execute(_base_request(), provider=provider2, idempotency_store=store)
        self.assertEqual(r2["terminal_outcome"], "SUCCESS")
        self.assertEqual(r2["final_head_sha"], r1["final_head_sha"])

    def test_same_key_diff_digest_replay_conflict(self):
        store: dict = {}
        p1 = DeterministicFakeProvider(changed_paths=["tools/node_architect/scratch/foo.py"])
        execute(_base_request(), provider=p1, idempotency_store=store)
        # Same idempotency key but a different scope_hash => different content digest.
        p2 = DeterministicFakeProvider(changed_paths=["tools/node_architect/scratch/foo.py"])
        r2 = execute(
            _base_request(scope_hash="sha256:" + "b" * 64),
            provider=p2,
            idempotency_store=store,
        )
        self.assertEqual(r2["terminal_outcome"], "REPLAY_CONFLICT")


class AC6NoSharedSurfaceMutation(unittest.TestCase):
    def test_control_plane_protected_blocked(self):
        # A path that is in allowed_paths but is a control-plane protected surface must
        # still be blocked (the task may not mutate the standing authority machinery).
        req = _base_request(
            allowed_paths=["tools/node_architect/scratch/x.py", "tools/node_architect/derive_task_authority.py"],
            prohibited_paths=[],
        )
        provider = DeterministicFakeProvider(
            changed_paths=["tools/node_architect/derive_task_authority.py"],
            recorded_actions=["modify_approved_files"],
        )
        result = execute(req, provider=provider, idempotency_store={})
        self.assertEqual(result["terminal_outcome"], "OUT_OF_SCOPE")
        self.assertTrue(any("control_plane_protected_path" in f for f in result["findings"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
