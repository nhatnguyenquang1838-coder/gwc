from __future__ import annotations

import json
from pathlib import Path
import unittest
from typing import Any

from jsonschema import Draft202012Validator

from tools.node_architect.base_drift_check import decide_base_drift
from tools.node_architect.branch_creation import decide_branch_creation
from tools.node_architect.scoped_file_write import decide_scoped_file_write

BASE = "78d596242a9e042d62d6174afc40aa4976eb3285"
OTHER = "4c3ca535a3e9d9c71fb4bd0ca7e0f0264e664f3a"
SCOPE = "sha256:2b7483530c3ebf5b7885de097b770a07b2c04ddaf7b7ec5e4dbe9b8c8199f6e2"
BRANCH = "codex/scrum-193-195-f3-repo-delivery-m5-20260801"


class RepoDeliveryM5BatchB1Tests(unittest.TestCase):
    def _validate(self, name: str, payload: dict) -> None:
        schema = json.loads((Path("schemas") / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)

    def test_branch_creation_ready_schema_valid(self) -> None:
        decision = decide_branch_creation({
            "repository": "nhatnguyenquang1838-coder/gwc",
            "branch_name": BRANCH,
            "approved_base_sha": BASE,
            "observed_current_base_sha": BASE,
            "idempotency_key": "scrum-193-branch-create",
        })
        self.assertEqual(decision["outcome"], "READY_TO_CREATE")
        self.assertTrue(decision["may_create_branch"])
        self.assertFalse(decision["merge_authority_granted"])
        self._validate("branch-creation-decision.schema.json", decision)

    def test_branch_creation_reconciles_existing_same_base(self) -> None:
        decision = decide_branch_creation({
            "repository": "nhatnguyenquang1838-coder/gwc",
            "branch_name": BRANCH,
            "approved_base_sha": BASE,
            "observed_current_base_sha": BASE,
            "existing_branch_sha": BASE,
            "idempotency_key": "scrum-193-branch-create",
        })
        self.assertEqual(decision["outcome"], "RECONCILED_EXISTING")
        self.assertFalse(decision["may_create_branch"])

    def test_branch_creation_blocks_base_drift_and_collision(self) -> None:
        drift = decide_branch_creation({
            "repository": "nhatnguyenquang1838-coder/gwc",
            "branch_name": BRANCH,
            "approved_base_sha": BASE,
            "observed_current_base_sha": OTHER,
            "idempotency_key": "scrum-193-branch-create",
        })
        collision = decide_branch_creation({
            "repository": "nhatnguyenquang1838-coder/gwc",
            "branch_name": BRANCH,
            "approved_base_sha": BASE,
            "observed_current_base_sha": BASE,
            "existing_branch_sha": OTHER,
            "idempotency_key": "scrum-193-branch-create",
        })
        self.assertEqual(drift["outcome"], "BLOCKED_BASE_DRIFT")
        self.assertTrue(drift["requires_reapproval"])
        self.assertEqual(collision["outcome"], "BLOCKED_BRANCH_COLLISION")

    def test_branch_creation_unknown_result_persists_pending_action(self) -> None:
        decision = decide_branch_creation({
            "repository": "nhatnguyenquang1838-coder/gwc",
            "branch_name": BRANCH,
            "approved_base_sha": BASE,
            "observed_current_base_sha": BASE,
            "create_result": "unknown",
            "idempotency_key": "scrum-193-branch-create",
        })
        self.assertEqual(decision["outcome"], "PENDING_READBACK_REQUIRED")
        self.assertEqual(decision["pending_action"], "branch-create:scrum-193-branch-create")
        self.assertFalse(decision["may_create_branch"])

    def test_base_drift_current_schema_valid(self) -> None:
        decision = decide_base_drift({
            "repository": "nhatnguyenquang1838-coder/gwc",
            "approved_base_sha": BASE,
            "observed_base_sha": BASE,
            "scope_hash": SCOPE,
        })
        self.assertEqual(decision["outcome"], "BASE_CURRENT")
        self.assertTrue(decision["may_continue"])
        self._validate("base-drift-check-decision.schema.json", decision)

    def test_base_drift_requires_reapproval_and_handles_observability(self) -> None:
        drift = decide_base_drift({
            "repository": "nhatnguyenquang1838-coder/gwc",
            "approved_base_sha": BASE,
            "observed_base_sha": OTHER,
            "scope_hash": SCOPE,
        })
        unavailable = decide_base_drift({
            "repository": "nhatnguyenquang1838-coder/gwc",
            "approved_base_sha": BASE,
            "observed_base_sha": BASE,
            "scope_hash": SCOPE,
            "connector_status": "ambiguous",
        })
        self.assertEqual(drift["outcome"], "BASE_DRIFT_REAPPROVAL_REQUIRED")
        self.assertTrue(drift["invalidates_approval"])
        self.assertEqual(unavailable["outcome"], "BASE_OBSERVABILITY_BLOCKED")

    def test_base_drift_reconciles_pending_action_first(self) -> None:
        decision = decide_base_drift({
            "repository": "nhatnguyenquang1838-coder/gwc",
            "approved_base_sha": BASE,
            "observed_base_sha": BASE,
            "scope_hash": SCOPE,
            "pending_action": "branch-create:scrum-193-branch-create",
        })
        self.assertEqual(decision["outcome"], "RECONCILE_PENDING_ACTION_FIRST")
        self.assertFalse(decision["may_continue"])

    def test_scoped_write_allowed_schema_valid(self) -> None:
        decision = decide_scoped_file_write({
            "approved_paths": ["tools/node_architect/branch_creation.py"],
            "requested_paths": ["tools/node_architect/branch_creation.py"],
            "observed_diff_paths": [],
            "idempotency_key": "scrum-195-write-scope",
        })
        self.assertEqual(decision["outcome"], "WRITE_ALLOWED")
        self.assertTrue(decision["may_write"])
        self._validate("scoped-file-write-decision.schema.json", decision)

    def test_scoped_write_blocks_out_of_scope_request_and_diff(self) -> None:
        request = decide_scoped_file_write({
            "approved_paths": ["tools/node_architect/branch_creation.py"],
            "requested_paths": ["tools/node_architect/branch_creation.py", "secrets/token.txt"],
            "observed_diff_paths": [],
            "idempotency_key": "scrum-195-write-scope",
        })
        diff = decide_scoped_file_write({
            "approved_paths": ["tools/node_architect/branch_creation.py"],
            "requested_paths": ["tools/node_architect/branch_creation.py"],
            "observed_diff_paths": ["tools/node_architect/branch_creation.py", "README.md"],
            "idempotency_key": "scrum-195-write-scope",
            "write_result": "success",
        })
        self.assertEqual(request["outcome"], "BLOCKED_OUT_OF_SCOPE_REQUEST")
        self.assertEqual(diff["outcome"], "BLOCKED_OUT_OF_SCOPE_DIFF")

    def test_scoped_write_reconciles_unknown_success_and_duplicate(self) -> None:
        unknown = decide_scoped_file_write({
            "approved_paths": ["tools/node_architect/branch_creation.py"],
            "requested_paths": ["tools/node_architect/branch_creation.py"],
            "observed_diff_paths": [],
            "idempotency_key": "scrum-195-write-scope",
            "write_result": "unknown",
        })
        success = decide_scoped_file_write({
            "approved_paths": ["tools/node_architect/branch_creation.py"],
            "requested_paths": ["tools/node_architect/branch_creation.py"],
            "observed_diff_paths": ["tools/node_architect/branch_creation.py"],
            "idempotency_key": "scrum-195-write-scope",
            "write_result": "success",
        })
        duplicate = decide_scoped_file_write({
            "approved_paths": ["tools/node_architect/branch_creation.py"],
            "requested_paths": ["tools/node_architect/branch_creation.py"],
            "observed_diff_paths": ["tools/node_architect/branch_creation.py"],
            "idempotency_key": "scrum-195-write-scope",
        })
        self.assertEqual(unknown["pending_action"], "scoped-write:scrum-195-write-scope")
        self.assertEqual(success["outcome"], "WRITE_RECONCILED")
        self.assertEqual(duplicate["outcome"], "DUPLICATE_EFFECT_REPLAYED")

    def test_fail_closed_and_authority_flags(self) -> None:
        decisions = [
            decide_branch_creation({}),
            decide_base_drift({}),
            decide_scoped_file_write({}),
        ]
        self.assertTrue(all(decision["outcome"] == "INVALID_INPUT" for decision in decisions))
        for decision in decisions:
            self.assertFalse(decision["merge_authority_granted"])
            self.assertFalse(decision["deployment_authority_granted"])
            self.assertFalse(decision["production_authority_granted"])


class RepoDeliverySCRUM316BranchCreationTests(unittest.TestCase):
    """Task-bound tests for SCRUM-316 (auto/* branch guard acceptance).

    Minimal DELTA_REQUIRED: the pure branch-creation guard must accept the
    canonical autonomous working branch `auto/SCRUM-316-na81-recert-20260814-r10`
    while preserving every existing allowed prefix and fail-closed behavior.

    Corrected at S2_CORRECTION (controller seq 5): BASE is bound to the exact
    current execution base `b8b3ab344b470b19e90a1aea408cba9675efa855` so the
    tests prove the commanded exact base, not a historical one. `OTHER` is a
    different valid 40-hex SHA used only for drift/collision scenarios.
    """

    BASE = "b8b3ab344b470b19e90a1aea408cba9675efa855"
    OTHER = "c3a5c2f0e1d4b8a7960f2c3d4e5a6b7c8d9e0f1a"
    TASK_BRANCH = "auto/SCRUM-316-na81-recert-20260814-r10"
    ID = "scrum-316-na81-recert"

    def _decide(self, **overrides: Any) -> dict:
        obs = {
            "repository": "nhatnguyenquang1838-coder/gwc",
            "branch_name": self.TASK_BRANCH,
            "approved_base_sha": self.BASE,
            "observed_current_base_sha": self.BASE,
            "idempotency_key": self.ID,
        }
        obs.update(overrides)
        return decide_branch_creation(obs)

    def test_auto_branch_ready_to_create_on_exact_current_base(self) -> None:
        decision = self._decide()
        self.assertEqual(decision["outcome"], "READY_TO_CREATE")
        self.assertTrue(decision["may_create_branch"])
        self.assertNotIn("INVALID_BRANCH_NAME", decision["reason_codes"])
        self.assertEqual(decision["base_sha"], self.BASE)
        self.assertFalse(decision["merge_authority_granted"])
        self.assertFalse(decision["deployment_authority_granted"])
        self.assertFalse(decision["production_authority_granted"])
        # Output contract must remain schema-valid (no contract change).
        self._validate("branch-creation-decision.schema.json", decision)

    def test_auto_branch_reconciles_existing_same_exact_base(self) -> None:
        decision = self._decide(existing_branch_sha=self.BASE)
        self.assertEqual(decision["outcome"], "RECONCILED_EXISTING")
        self.assertFalse(decision["may_create_branch"])

    def test_auto_branch_blocks_base_drift_and_collision(self) -> None:
        drift = self._decide(observed_current_base_sha=self.OTHER)
        collision = self._decide(existing_branch_sha=self.OTHER)
        self.assertEqual(drift["outcome"], "BLOCKED_BASE_DRIFT")
        self.assertTrue(drift["requires_reapproval"])
        self.assertEqual(collision["outcome"], "BLOCKED_BRANCH_COLLISION")

    def test_auto_branch_unknown_result_persists_pending_action(self) -> None:
        decision = self._decide(create_result="unknown")
        self.assertEqual(decision["outcome"], "PENDING_READBACK_REQUIRED")
        self.assertEqual(decision["pending_action"], f"branch-create:{self.ID}")
        self.assertFalse(decision["may_create_branch"])

    def test_auto_branch_idempotent_replay_success(self) -> None:
        decision = self._decide(create_result="success")
        self.assertEqual(decision["outcome"], "CREATED")
        self.assertEqual(decision["observed_ref_sha"], self.BASE)
        self.assertFalse(decision["may_create_branch"])

    def test_auto_branch_unknown_then_same_base_readback_reconciles(self) -> None:
        # Replay-safe: an unknown external write outcome must persist a pending
        # action, then authoritative same-base readback reconciles idempotently.
        unknown = self._decide(create_result="unknown")
        self.assertEqual(unknown["outcome"], "PENDING_READBACK_REQUIRED")
        self.assertEqual(unknown["pending_action"], f"branch-create:{self.ID}")
        # Later readback shows the branch already sits at the exact approved base.
        reconciled = self._decide(existing_branch_sha=self.BASE)
        self.assertEqual(reconciled["outcome"], "RECONCILED_EXISTING")
        self.assertFalse(reconciled["may_create_branch"])

    def test_protected_targets_main_and_preprod_denied(self) -> None:
        # Protected refs (main, pre-prod) are never valid working-branch targets.
        for protected_ref in ("main", "pre-prod"):
            decision = decide_branch_creation({
                "repository": "nhatnguyenquang1838-coder/gwc",
                "branch_name": protected_ref,
                "approved_base_sha": self.BASE,
                "observed_current_base_sha": self.BASE,
                "idempotency_key": self.ID,
            })
            self.assertEqual(decision["outcome"], "INVALID_INPUT", protected_ref)
            self.assertIn("INVALID_BRANCH_NAME", decision["reason_codes"], protected_ref)
            self.assertFalse(decision["may_create_branch"], protected_ref)
        # A non-allowlisted prefix is also denied by the fail-closed guard.
        non_prefix = decide_branch_creation({
            "repository": "nhatnguyenquang1838-coder/gwc",
            "branch_name": "release/SCRUM-316-na81-recert-20260814-r10",
            "approved_base_sha": self.BASE,
            "observed_current_base_sha": self.BASE,
            "idempotency_key": self.ID,
        })
        self.assertEqual(non_prefix["outcome"], "INVALID_INPUT")
        self.assertIn("INVALID_BRANCH_NAME", non_prefix["reason_codes"])

    def _validate(self, name: str, payload: dict) -> None:
        schema = json.loads((Path("schemas") / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)


if __name__ == "__main__":
    unittest.main()
