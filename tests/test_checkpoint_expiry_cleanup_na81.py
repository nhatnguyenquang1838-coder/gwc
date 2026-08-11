"""NA81 current-task tests for SCRUM-333 (runtime_checkpoint.checkpoint-expiry-cleanup).

These tests validate the current brief's additional requirements that are NOT
proven by the historical M5 test suite:
- approval/CI/PR/merge/G0-G6 evidence retained even when mislabeled disposable
- ambiguous artifact_type or retention_class defaults to retain (fail-closed)
- concurrent resume race: only the active-resume entry is protected
- idempotent rerun under canonical-evidence presence
- destructive-negative: canonical evidence is never tombstoned
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from node_architect.checkpoint_expiry_cleanup import (
    PROTECTED_CANONICAL_TYPES,
    CleanupEntry,
    CleanupPolicy,
    apply_cleanup,
    classify_entry,
    is_replay_equivalent,
    plan_cleanup,
)


def entry(**overrides: Any) -> CleanupEntry:
    data: dict[str, Any] = dict(
        entry_id="hint-1",
        artifact_type="resume-hint",
        retention_class="disposable",
        created_at_epoch_ms=1000,
        expires_at_epoch_ms=2000,
        tombstoned=False,
    )
    data.update(overrides)
    return CleanupEntry(**data)


def policy(**overrides: Any) -> CleanupPolicy:
    data: dict[str, Any] = dict(now_epoch_ms=3000, retention_window_ms=1000)
    data.update(overrides)
    return CleanupPolicy(**data)


def apply(entries, pol, cleanup_id="cleanup-na81"):
    return apply_cleanup(entries, pol, cleanup_id=cleanup_id)


class SCRUM333NA81Tests(unittest.TestCase):
    """NA81 requirement→code→test evidence map for SCRUM-333."""

    # --- approval / CI / PR / merge / G0-G6 evidence retained ---

    def test_approval_evidence_retained_even_when_mislabeled_disposable(self):
        # Defense-in-depth: approval-evidence must not be tombstoned even if
        # retention_class is mistakenly set to disposable.
        result = apply(
            [entry(entry_id="appr-1", artifact_type="approval-evidence",
                   retention_class="disposable", expires_at_epoch_ms=1)],
            policy(now_epoch_ms=999999),
        )
        self.assertEqual(result["entries_tombstoned"], 0)
        self.assertIn("appr-1", result["retained_canonical_evidence"])
        self.assertEqual(result["registry"][0]["tombstoned"], False)

    def test_ci_evidence_retained(self):
        result = apply(
            [entry(entry_id="ci-1", artifact_type="ci-evidence",
                   retention_class="canonical", expires_at_epoch_ms=1)],
            policy(now_epoch_ms=999999),
        )
        self.assertEqual(result["entries_tombstoned"], 0)
        self.assertIn("ci-1", result["retained_canonical_evidence"])

    def test_pr_evidence_retained(self):
        result = apply(
            [entry(entry_id="pr-1", artifact_type="pr-evidence",
                   retention_class="canonical", expires_at_epoch_ms=1)],
            policy(now_epoch_ms=999999),
        )
        self.assertEqual(result["entries_tombstoned"], 0)
        self.assertIn("pr-1", result["retained_canonical_evidence"])

    def test_merge_evidence_retained(self):
        result = apply(
            [entry(entry_id="mrg-1", artifact_type="merge-evidence",
                   retention_class="canonical", expires_at_epoch_ms=1)],
            policy(now_epoch_ms=999999),
        )
        self.assertEqual(result["entries_tombstoned"], 0)
        self.assertIn("mrg-1", result["retained_canonical_evidence"])

    def test_g0_g6_evidence_retained(self):
        for gate in range(7):
            art = f"g{gate}-evidence"
            result = apply(
                [entry(entry_id=f"g{gate}-1", artifact_type=art,
                       retention_class="canonical", expires_at_epoch_ms=1)],
                policy(now_epoch_ms=999999),
            )
            self.assertEqual(result["entries_tombstoned"], 0, msg=art)
            self.assertIn(f"g{gate}-1", result["retained_canonical_evidence"])

    # --- ambiguous reference fail-closed ---

    def test_ambiguous_artifact_type_fail_closed(self):
        # Unknown artifact_type must default to retain (RETAIN_VALID).
        self.assertEqual(
            classify_entry(entry(artifact_type="weird-unknown-type"), policy(now_epoch_ms=3000)),
            "RETAIN_VALID",
        )

    def test_ambiguous_retention_class_fail_closed(self):
        # Known disposable type but unknown retention_class defaults to retain.
        self.assertEqual(
            classify_entry(entry(retention_class="undefined-class"), policy(now_epoch_ms=3000)),
            "RETAIN_VALID",
        )

    # --- concurrent resume race ---

    def test_concurrent_resume_race_only_active_protected(self):
        # Multiple disposable hints; only the one matching active_resume_entry_id
        # is protected. Others with expired tokens are tombstoned.
        result = apply(
            [
                entry(entry_id="hint-a", expires_at_epoch_ms=2000),
                entry(entry_id="hint-b", expires_at_epoch_ms=2000),
                entry(entry_id="hint-c", expires_at_epoch_ms=3000),
            ],
            policy(
                now_epoch_ms=4000,
                active_resume_entry_id="hint-c",
                resume_token_expires_epoch_ms=5000,
            ),
        )
        self.assertEqual(result["entries_tombstoned"], 2)
        tombstoned_ids = {m["entry_id"] for m in result["tombstoned"]}
        self.assertIn("hint-a", tombstoned_ids)
        self.assertIn("hint-b", tombstoned_ids)
        self.assertNotIn("hint-c", tombstoned_ids)
        registry_ids = {e["entry_id"] for e in result["registry"]}
        self.assertIn("hint-c", registry_ids)
        hint_c_reg = next(e for e in result["registry"] if e["entry_id"] == "hint-c")
        self.assertFalse(hint_c_reg["tombstoned"])

    # --- idempotent rerun with canonical evidence ---

    def test_idempotent_rerun_with_canonical_evidence(self):
        entries = [
            entry(entry_id="hint-1", expires_at_epoch_ms=2000),
            entry(entry_id="appr-1", artifact_type="approval-evidence",
                   retention_class="canonical", expires_at_epoch_ms=1),
        ]
        first = apply(entries, policy(now_epoch_ms=3000), cleanup_id="c1")
        second = apply(entries, policy(now_epoch_ms=3000), cleanup_id="c2")
        self.assertTrue(is_replay_equivalent(first, second))
        self.assertEqual(first["entries_tombstoned"], 1)
        self.assertEqual(second["entries_tombstoned"], 1)

    # --- destructive-negative: canonical evidence never tombstoned ---

    def test_destructive_negative_canonical_evidence_never_tombstoned(self):
        entries = [
            entry(entry_id="gov-1", artifact_type="governance-evidence",
                   retention_class="governance", expires_at_epoch_ms=1),
            entry(entry_id="ci-1", artifact_type="ci-evidence",
                   retention_class="canonical", expires_at_epoch_ms=1),
            entry(entry_id="pr-1", artifact_type="pr-evidence",
                   retention_class="canonical", expires_at_epoch_ms=1),
            entry(entry_id="mrge-1", artifact_type="merge-evidence",
                   retention_class="canonical", expires_at_epoch_ms=1),
            entry(entry_id="hint-1", artifact_type="resume-hint",
                   retention_class="disposable", expires_at_epoch_ms=100),
        ]
        result = apply(entries, policy(now_epoch_ms=999999))
        self.assertEqual(result["entries_tombstoned"], 1)
        self.assertEqual(result["tombstoned"][0]["entry_id"], "hint-1")
        self.assertIn("gov-1", result["retained_governance_or_audit"])
        self.assertIn("ci-1", result["retained_canonical_evidence"])
        self.assertIn("pr-1", result["retained_canonical_evidence"])
        self.assertIn("mrge-1", result["retained_canonical_evidence"])

    # --- protected type list must be non-empty and cover the brief ---

    def test_protected_canonical_types_non_empty(self):
        self.assertTrue(len(PROTECTED_CANONICAL_TYPES) >= 11)

    def test_protected_canonical_types_contains_approval_ci_pr_merge(self):
        required = {"approval-evidence", "ci-evidence", "pr-evidence", "merge-evidence"}
        self.assertTrue(required.issubset(PROTECTED_CANONICAL_TYPES))

    def test_protected_canonical_types_contains_g0_to_g6(self):
        required = {f"g{i}-evidence" for i in range(7)}
        self.assertTrue(required.issubset(PROTECTED_CANONICAL_TYPES))


if __name__ == "__main__":
    unittest.main()
