from __future__ import annotations

import unittest

from tools.node_architect.reproducibility_check import (
    BLOCKED,
    PASS,
    REPRO_VOLATILE_DIFF,
    check_reproducibility,
    check_reproducibility_na81,
)

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "1" * 40
HEAD = "2" * 40
SCOPE = "sha256:" + "3" * 64
BRANCH = "codex/scrum-339-validation-quality-reproducibility-r10-20260814"


_ENV_DEFAULT = object()


def _state(tool="t1", runtime="rt1", input_="i1", dependency="d1", policy="p1",
           environment=_ENV_DEFAULT, result="sha256:" + "9" * 64, volatile=None):
    if environment is _ENV_DEFAULT:
        environment = {"python": "3.12", "os": "linux", "toolchain": "gcc-13"}
    return {
        "tool": {"id": tool},
        "runtime": {"id": runtime},
        "input": {"id": input_},
        "dependency": {"id": dependency},
        "policy": {"id": policy},
        "environment": environment,
        "result_digest": result,
        "volatile_fields": volatile or [],
    }


def evidence(**overrides) -> dict:
    payload = {
        "task_id": "SCRUM-339",
        "repository": REPO,
        "branch": BRANCH,
        "base_sha": BASE,
        "head_sha": HEAD,
        "scope_hash": SCOPE,
        "graph_revision": "scrum-339-route-v1",
        "idempotency_key": "scrum-339-repro-1",
        "captured": _state(),
        "rerun": _state(),
    }
    payload.update(overrides)
    return payload


class ReproducibilityCheckM5Tests(unittest.TestCase):
    def test_accepts_equivalent_rerun(self):
        result = check_reproducibility(evidence())
        self.assertEqual(result["status"], PASS)
        self.assertEqual(result["reason_codes"], ["REPRO_ACCEPTED"])
        self.assertFalse(result["merge_authority_granted"])
        self.assertFalse(result["deployment_authority_granted"])
        self.assertFalse(result["production_authority_granted"])

    def test_blocks_tool_input_dependency_policy_drift(self):
        # drift in a stable dimension (tool) with no declared volatility -> BLOCKED.
        value = evidence()
        value["rerun"] = _state(tool="t2")
        result = check_reproducibility(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("REPRO_TOOL_DRIFT", result["reason_codes"])

        # input drift
        value = evidence()
        value["rerun"] = _state(input_="i2")
        self.assertIn("REPRO_INPUT_DRIFT", check_reproducibility(value)["reason_codes"])

        # dependency drift
        value = evidence()
        value["rerun"] = _state(dependency="d2")
        self.assertIn("REPRO_DEPENDENCY_DRIFT", check_reproducibility(value)["reason_codes"])

        # policy drift
        value = evidence()
        value["rerun"] = _state(policy="p2")
        self.assertIn("REPRO_POLICY_DRIFT", check_reproducibility(value)["reason_codes"])

    def test_blocks_missing_environment(self):
        # Missing environment evidence on the captured side MUST NOT PASS.
        value = evidence()
        value["captured"] = _state(environment=None)
        result = check_reproducibility(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("REPRO_ENVIRONMENT_EVIDENCE_MISSING", result["reason_codes"])

        # Missing environment evidence on the rerun side also blocks.
        value = evidence()
        value["rerun"] = _state(environment=None)
        self.assertIn("REPRO_ENVIRONMENT_EVIDENCE_MISSING", check_reproducibility(value)["reason_codes"])

    def test_allows_volatile_only_differences(self):
        # Declared volatile field (runtime) differs but is not evidence-blocking.
        value = evidence()
        value["captured"] = _state(runtime="rt1", volatile=["runtime"])
        value["rerun"] = _state(runtime="rt2", volatile=["runtime"])
        result = check_reproducibility(value)
        self.assertEqual(result["status"], PASS)
        self.assertIn(REPRO_VOLATILE_DIFF, result["reason_codes"])
        self.assertIn("REPRO_ACCEPTED", result["reason_codes"])

    def test_blocks_unexplained_nondeterminism(self):
        # Result differs while every stable dimension matches -> nondeterminism.
        value = evidence()
        value["rerun"] = _state(result="sha256:" + "a" * 64)
        result = check_reproducibility(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("REPRO_NONDETERMINISM", result["reason_codes"])

    def test_replay_is_deterministic(self):
        cache = {}
        first = check_reproducibility(evidence(), replay_cache=cache)
        second = check_reproducibility(evidence(), replay_cache=cache)
        self.assertEqual(first["repro_digest"], second["repro_digest"])
        self.assertTrue(second["replayed"])

    def test_na81_layer_fail_closed(self):
        # NA81 layer reuses the core and stays BLOCKED on drift, asserting NA81_FAIL_CLOSED.
        value = evidence()
        value["rerun"] = _state(tool="t2")
        na81 = check_reproducibility_na81(value)
        self.assertEqual(na81["status"], BLOCKED)
        self.assertIn("NA81_FAIL_CLOSED", na81["reason_codes"])
        self.assertFalse(na81["approval_authority_granted"])
        self.assertFalse(na81["na81"]["approval_authority_granted"])
        self.assertTrue(na81["na81"]["fail_closed"])
        self.assertEqual(na81["decision"]["status"], BLOCKED)

        # NA81 layer passes an equivalent rerun and embeds the core decision.
        na81_ok = check_reproducibility_na81(evidence())
        self.assertEqual(na81_ok["status"], PASS)
        self.assertEqual(na81_ok["decision"]["status"], PASS)
        self.assertTrue(na81_ok["na81"]["non_authoritative"])


if __name__ == "__main__":
    unittest.main()
