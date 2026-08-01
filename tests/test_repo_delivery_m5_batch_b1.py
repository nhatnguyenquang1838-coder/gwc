from __future__ import annotations

import json
from pathlib import Path
import unittest

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


if __name__ == "__main__":
    unittest.main()
