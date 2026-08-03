from __future__ import annotations

import unittest
from typing import Any

from tools.node_architect.checkpoint_expiry_cleanup import (
    CleanupEntry,
    CleanupPolicy,
    apply_cleanup,
    classify_entry,
    is_replay_equivalent,
    plan_cleanup,
)

BASE = "3abc72eb8dc30759e5731d0c9492b11262567f56"
HEAD = "a" * 40


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


def apply(entries: list[CleanupEntry], pol: CleanupPolicy, cleanup_id: str = "cleanup-1"):
    return apply_cleanup(entries, pol, cleanup_id=cleanup_id)


class CheckpointExpiryCleanupTests(unittest.TestCase):
    # EARS #1: expired disposable hints + interrupt frames selected.
    def test_expired_hint_is_tombstoned(self):
        result = apply([entry(expires_at_epoch_ms=2000)], policy(now_epoch_ms=3000))
        self.assertEqual(result["entries_tombstoned"], 1)
        self.assertEqual(result["tombstoned"][0]["entry_id"], "hint-1")
        self.assertEqual(result["registry"][0]["tombstoned"], True)

    def test_expired_interrupt_frame_is_tombstoned(self):
        result = apply(
            [entry(entry_id="ifr-1", artifact_type="interrupt-frame")],
            policy(now_epoch_ms=3000),
        )
        self.assertEqual(result["entries_tombstoned"], 1)
        self.assertEqual(result["tombstoned"][0]["reason"], "EXPIRED_DISPOSABLE_HINT")

    # EARS #2: governance / audit / append-only evidence retained.
    def test_governance_evidence_retained(self):
        result = apply(
            [entry(entry_id="gov-1", artifact_type="governance-evidence", retention_class="governance", expires_at_epoch_ms=None)],
            policy(now_epoch_ms=999999),
        )
        self.assertEqual(result["entries_tombstoned"], 0)
        self.assertIn("gov-1", result["retained_governance_or_audit"])

    def test_audit_evidence_retained(self):
        result = apply(
            [entry(entry_id="aud-1", artifact_type="audit-evidence", retention_class="audit", expires_at_epoch_ms=None)],
            policy(now_epoch_ms=999999),
        )
        self.assertEqual(result["entries_tombstoned"], 0)

    def test_append_only_event_retained(self):
        result = apply(
            [entry(entry_id="evt-1", artifact_type="runtime-event", retention_class="runtime", expires_at_epoch_ms=1)],
            policy(now_epoch_ms=999999),
        )
        self.assertEqual(result["entries_tombstoned"], 0)
        self.assertFalse(result["registry"][0]["tombstoned"])

    # Active token preservation: unexpired disposable hint is retained.
    def test_unexpired_hint_preserved(self):
        result = apply([entry(expires_at_epoch_ms=2000)], policy(now_epoch_ms=1500))
        self.assertEqual(result["entries_tombstoned"], 0)
        self.assertFalse(result["registry"][0]["tombstoned"])

    # EARS #3: concurrent resume wins over cleanup for valid active path.
    def test_valid_active_resume_path_preserved(self):
        result = apply(
            [
                entry(
                    entry_id="hint-active",
                    artifact_type="resume-hint",
                    retention_class="disposable",
                    expires_at_epoch_ms=2000,
                ),
                entry(
                    entry_id="hint-other",
                    artifact_type="resume-hint",
                    retention_class="disposable",
                    expires_at_epoch_ms=2000,
                ),
            ],
            policy(
                now_epoch_ms=3000,
                active_resume_entry_id="hint-active",
                resume_token_expires_epoch_ms=5000,
            ),
        )
        # Only hint-other should be tombstoned; active resume path retained.
        self.assertEqual(result["entries_tombstoned"], 1)
        self.assertEqual(result["tombstoned"][0]["entry_id"], "hint-other")

    def test_expired_active_resume_token_no_longer_protects(self):
        result = apply(
            [entry(entry_id="hint-active", expires_at_epoch_ms=2000)],
            policy(
                now_epoch_ms=3000,
                active_resume_entry_id="hint-active",
                resume_token_expires_epoch_ms=2500,
            ),
        )
        self.assertEqual(result["entries_tombstoned"], 1)

    # EARS #4: auditable tombstone + replay-equivalent cleanup.
    def test_tombstone_marker_is_auditable(self):
        result = apply([entry(expires_at_epoch_ms=2000)], policy(now_epoch_ms=3000))
        marker = result["tombstoned"][0]
        self.assertEqual(marker["marker"], "TOMBSTONE")
        self.assertIn("tombstone_digest", marker)
        self.assertIn("reason", marker)

    def test_cleanup_is_replay_equivalent(self):
        entries = [entry(expires_at_epoch_ms=2000)]
        first = apply(entries, policy(now_epoch_ms=3000), cleanup_id="c1")
        second = apply(entries, policy(now_epoch_ms=3000), cleanup_id="c2")
        self.assertTrue(is_replay_equivalent(first, second))

    def test_cleanup_is_idempotent_on_already_tombstoned(self):
        entries = [entry(expires_at_epoch_ms=2000, tombstoned=True)]
        result = apply(entries, policy(now_epoch_ms=3000))
        self.assertEqual(result["entries_tombstoned"], 0)
        self.assertEqual(result["entries_retained"], 1)

    # Replay after cleanup: plan + apply produce a stable disposition.
    def test_plan_matches_apply(self):
        entries = [
            entry(entry_id="a", expires_at_epoch_ms=2000),
            entry(entry_id="b", artifact_type="governance-evidence", retention_class="governance", expires_at_epoch_ms=None),
        ]
        pol = policy(now_epoch_ms=3000)
        planned = plan_cleanup(entries, pol)
        self.assertIn("a", planned["tombstone"])
        self.assertIn("b", planned["retain"])

    def test_classify_combinatorial(self):
        # Expired disposable -> TOMBSTONE_EXPIRED
        self.assertEqual(classify_entry(entry(expires_at_epoch_ms=2000), policy(now_epoch_ms=3000)), "TOMBSTONE_EXPIRED")
        # Unexpired disposable -> RETAIN_VALID
        self.assertEqual(classify_entry(entry(expires_at_epoch_ms=2000), policy(now_epoch_ms=1500)), "RETAIN_VALID")
        # Governance -> RETAIN_GOVERNANCE
        self.assertEqual(
            classify_entry(entry(artifact_type="governance-evidence", retention_class="governance", expires_at_epoch_ms=None), policy(now_epoch_ms=3000)),
            "RETAIN_GOVERNANCE",
        )
        # Valid active resume -> RETAIN_ACTIVE_RESUME
        self.assertEqual(
            classify_entry(
                entry(entry_id="hint-active", expires_at_epoch_ms=2000),
                policy(now_epoch_ms=3000, active_resume_entry_id="hint-active", resume_token_expires_epoch_ms=5000),
            ),
            "RETAIN_ACTIVE_RESUME",
        )


if __name__ == "__main__":
    unittest.main()
