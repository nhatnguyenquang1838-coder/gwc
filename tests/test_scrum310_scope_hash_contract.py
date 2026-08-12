"""Current SCRUM-310 contract tests for canonical scope identity."""
import unittest
from tools.node_architect.scope_hash_calculation import calculate_gate_scope_identity

BASE = dict(
    task_id="SCRUM-310",
    repository="nhatnguyenquang1838-coder/gwc",
    base_ref="pre-prod",
    base_sha="52fb8db72b6e391c2c7562ef777bbf75019ae6c9",
    working_branch="auto/SCRUM-310-na81-20260810",
    head_sha=None,
    risk_class="R2",
    authorized_paths=[
        "core/node-architect/node-catalog/gate_authority/scope-hash-calculation.node.json",
        "schemas/gate-scope-identity.schema.json",
    ],
    authorized_actions=["modify_approved_files", "create_commit", "push_working_branch"],
    excluded_actions=["merge_approved_pr", "deploy_approved_release"],
    additional_bindings=[],
)


class Scr310ScopeHashContractTests(unittest.TestCase):
    def test_current_pair_resolves_ready_without_authority(self):
        result = calculate_gate_scope_identity(**BASE)
        self.assertEqual(result["outcome"], "READY")
        self.assertEqual(result["reason_codes"], ["SCOPE_HASH_CALCULATED"])
        self.assertRegex(result["scope_hash"], r"^sha256:[0-9a-f]{64}$")
        self.assertFalse(result["authority_granted"])

    def test_equivalent_path_order_and_format_have_same_identity(self):
        reordered = dict(
            BASE,
            authorized_paths=[
                "./schemas\\gate-scope-identity.schema.json",
                "./core/node-architect/node-catalog/gate_authority/scope-hash-calculation.node.json",
            ],
        )
        self.assertEqual(
            calculate_gate_scope_identity(**BASE)["scope_hash"],
            calculate_gate_scope_identity(**reordered)["scope_hash"],
        )

    def test_equivalent_binding_order_has_same_identity(self):
        a = dict(BASE, additional_bindings=[
            {"key": "environment", "value": "pre-prod"},
            {"key": "evidence_digest", "value": "sha256:" + "a" * 64},
        ])
        b = dict(BASE, additional_bindings=list(reversed(a["additional_bindings"])))
        self.assertEqual(
            calculate_gate_scope_identity(**a)["scope_hash"],
            calculate_gate_scope_identity(**b)["scope_hash"],
        )

    def test_material_head_drift_changes_identity(self):
        a = dict(BASE, head_sha="a" * 40, authorized_actions=["open_or_update_draft_pr"])
        b = dict(BASE, head_sha="b" * 40, authorized_actions=["open_or_update_draft_pr"])
        self.assertNotEqual(
            calculate_gate_scope_identity(**a)["scope_hash"],
            calculate_gate_scope_identity(**b)["scope_hash"],
        )

    def test_blocked_input_never_exposes_usable_identity(self):
        blocked = dict(BASE, authorized_paths=["../secrets"])
        result = calculate_gate_scope_identity(**blocked)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIsNone(result["scope_hash"])
        self.assertFalse(result["authority_granted"])

    def test_write_scope_requires_branch_and_paths(self):
        result = calculate_gate_scope_identity(
            **dict(BASE, working_branch=None, authorized_paths=[])
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("SCOPE_BINDING_REQUIRED", result["reason_codes"])
        self.assertIn("SCOPE_WRITE_SET_EMPTY", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
