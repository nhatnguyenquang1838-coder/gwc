"""RED→GREEN tests for SCRUM-187 gate-scope-identity canonicalizer (MAT-F2-N04).

Covers the canonical semantic-hash boundary defined in the issue:
  * order-independent, timestamp-independent, drift-sensitive hash;
  * fail-closed on malformed SHA / repo, path traversal, root wildcard,
    unknown action, unknown binding, authorized/excluded conflict,
    missing gate-specific binding, empty write scope.

Run: python -m unittest tests.test_gate_authority_scope_hash_calculation_m4 -v
"""

import unittest

from tools.node_architect.scope_hash_calculation import calculate_gate_scope_identity


def _ok_kwargs(**over):
    base = dict(
        task_id="SCRUM-187",
        repository="nhatnguyenquang1838-coder/gwc",
        base_ref="main",
        base_sha="1db5cdde7666e95e0a5d864633a3255a2a6ad40e",
        working_branch="feat/scrum-187",
        head_sha=None,
        risk_class="R2",
        authorized_paths=["tools/node_architect/scope_hash_calculation.py"],
        authorized_actions=["modify_approved_files", "create_commit", "push_working_branch"],
        excluded_actions=["merge"],
        additional_bindings=[],
    )
    base.update(over)
    return base


class ScopeHashCalculationTests(unittest.TestCase):
    # --- Happy path -------------------------------------------------------
    def test_valid_calculates_ready(self):
        out = calculate_gate_scope_identity(**_ok_kwargs())
        self.assertEqual(out["outcome"], "READY")
        self.assertIn("SCOPE_HASH_CALCULATED", out["reason_codes"])
        self.assertTrue(out["scope_hash"].startswith("sha256:"))
        self.assertEqual(len(out["scope_hash"]), 71)
        self.assertFalse(out["authority_granted"])

    def test_order_independent_hash(self):
        a = calculate_gate_scope_identity(
            **_ok_kwargs(authorized_actions=["modify_approved_files", "create_commit"])
        )
        b = calculate_gate_scope_identity(
            **_ok_kwargs(authorized_actions=["create_commit", "modify_approved_files"])
        )
        self.assertEqual(a["scope_hash"], b["scope_hash"])

    def test_drift_sensitive_hash(self):
        a = calculate_gate_scope_identity(**_ok_kwargs(risk_class="R1"))
        b = calculate_gate_scope_identity(**_ok_kwargs(risk_class="R2"))
        self.assertNotEqual(a["scope_hash"], b["scope_hash"])

    def test_timestamp_independent_hash(self):
        a = calculate_gate_scope_identity(**_ok_kwargs(calculated_at="2026-08-02T00:00:00Z"))
        b = calculate_gate_scope_identity(**_ok_kwargs(calculated_at="2026-08-03T00:00:00Z"))
        self.assertEqual(a["scope_hash"], b["scope_hash"])

    def test_duplicate_ordering_deduped(self):
        out = calculate_gate_scope_identity(
            **_ok_kwargs(authorized_paths=[
                "tools/node_architect/scope_hash_calculation.py",
                "tools/node_architect/scope_hash_calculation.py",
            ])
        )
        self.assertEqual(len(out["authorized_paths"]), 1)

    def test_readonly_allows_empty_paths(self):
        out = calculate_gate_scope_identity(
            **_ok_kwargs(authorized_paths=[], authorized_actions=["read_repository"])
        )
        self.assertEqual(out["outcome"], "READY")

    # --- Fail-closed ------------------------------------------------------
    def test_malformed_sha_blocks(self):
        out = calculate_gate_scope_identity(**_ok_kwargs(base_sha="zzz"))
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("SCOPE_INPUT_INVALID", out["reason_codes"])

    def test_bad_repo_blocks(self):
        out = calculate_gate_scope_identity(**_ok_kwargs(repository="not-a-repo"))
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("SCOPE_INPUT_INVALID", out["reason_codes"])

    def test_path_traversal_blocks(self):
        out = calculate_gate_scope_identity(**_ok_kwargs(authorized_paths=["../secrets"]))
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("SCOPE_PATH_INVALID", out["reason_codes"])

    def test_absolute_path_blocks(self):
        out = calculate_gate_scope_identity(**_ok_kwargs(authorized_paths=["/etc/passwd"]))
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("SCOPE_PATH_INVALID", out["reason_codes"])

    def test_root_wildcard_blocks(self):
        out = calculate_gate_scope_identity(**_ok_kwargs(authorized_paths=["*"]))
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("SCOPE_PATH_OVERBROAD", out["reason_codes"])

    def test_action_conflict_blocks(self):
        out = calculate_gate_scope_identity(
            **_ok_kwargs(authorized_actions=["modify_approved_files", "merge"],
                         excluded_actions=["merge"])
        )
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("SCOPE_ACTION_CONFLICT", out["reason_codes"])

    def test_unknown_action_blocks(self):
        out = calculate_gate_scope_identity(**_ok_kwargs(authorized_actions=["frobnicate"]))
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("SCOPE_UNKNOWN_SEMANTIC", out["reason_codes"])

    def test_unknown_binding_blocks(self):
        out = calculate_gate_scope_identity(
            **_ok_kwargs(additional_bindings=[{"key": "bogus", "value": "x"}])
        )
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("SCOPE_UNKNOWN_SEMANTIC", out["reason_codes"])

    def test_missing_branch_binding_blocks(self):
        out = calculate_gate_scope_identity(
            **_ok_kwargs(working_branch=None, authorized_actions=["create_guarded_branch"])
        )
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("SCOPE_BINDING_REQUIRED", out["reason_codes"])

    def test_missing_head_binding_blocks(self):
        out = calculate_gate_scope_identity(
            **_ok_kwargs(head_sha=None, authorized_actions=["open_or_update_draft_pr"])
        )
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("SCOPE_BINDING_REQUIRED", out["reason_codes"])

    def test_empty_write_set_for_write_action_blocks(self):
        out = calculate_gate_scope_identity(
            **_ok_kwargs(authorized_paths=[], authorized_actions=["modify_approved_files"])
        )
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("SCOPE_WRITE_SET_EMPTY", out["reason_codes"])


if __name__ == "__main__":
    unittest.main()
