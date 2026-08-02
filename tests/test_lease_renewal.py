#!/usr/bin/env python3
"""Unit tests for runtime_checkpoint.lease-renewal (MAT-F4-N06, M5_REPLAY_SAFE)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from node_architect.lease_renewal import (
    Lease,
    LeaseRenewalError,
    RenewalDecision,
    evaluate_renewal,
    lease_digest,
    renew_lease,
)

NOW = "2026-08-02T23:30:00Z"
LATER = "2026-08-02T23:35:00Z"
BASE_SHA = "65c93c5927013c750631933495c5ecb5e22fae88"
SCOPE = "sha256:39b17f86e89b29876ac025dccfe36e1d24d03f678dd7b731775ec1e61ae1f0e7"


def _lease(**overrides) -> Lease:
    data = dict(
        lease_id="L-1",
        owner="hermes",
        task_id="SCRUM-207",
        node_id="runtime_checkpoint.lease-renewal",
        scope_hash=SCOPE,
        base_sha=BASE_SHA,
        fencing_token=5,
        issued_at=NOW,
        expires_at="2026-08-02T23:40:00Z",
        repository="nhatnguyenquang1838-coder/gwc",
    )
    data.update(overrides)
    return Lease(**data)


class TestBindingFailClosed(unittest.TestCase):
    def test_missing_owner_rejected(self):
        with self.assertRaises(LeaseRenewalError):
            evaluate_renewal(
                task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
                scope_hash=SCOPE, base_sha=BASE_SHA, owner="", fencing_token=5,
                current_lease=_lease(), repository="nhatnguyenquang1838-coder/gwc", now=NOW,
            )

    def test_bad_base_sha_rejected(self):
        with self.assertRaises(LeaseRenewalError):
            evaluate_renewal(
                task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
                scope_hash=SCOPE, base_sha="zzz", owner="hermes", fencing_token=5,
                current_lease=_lease(), repository="nhatnguyenquang1838-coder/gwc", now=NOW,
            )

    def test_bad_scope_prefix_rejected(self):
        with self.assertRaises(LeaseRenewalError):
            evaluate_renewal(
                task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
                scope_hash="md5:abc", base_sha=BASE_SHA, owner="hermes", fencing_token=5,
                current_lease=_lease(), repository="nhatnguyenquang1838-coder/gwc", now=NOW,
            )


class TestContractRequirements(unittest.TestCase):
    # EARS #1: renew inside approved G2 scope -> new lease, token +1
    def test_renew_inside_scope_advances_token(self):
        d = evaluate_renewal(
            task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
            scope_hash=SCOPE, base_sha=BASE_SHA, owner="hermes", fencing_token=5,
            current_lease=_lease(), repository="nhatnguyenquang1838-coder/gwc", now=NOW,
        )
        self.assertTrue(d.renewed)
        self.assertEqual(d.lease.fencing_token, 6)
        self.assertEqual(d.reconcile_reason, None)

    # EARS #2: must not hide base drift
    def test_base_drift_routes_reconcile(self):
        d = evaluate_renewal(
            task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
            scope_hash=SCOPE, base_sha="0" * 40, owner="hermes", fencing_token=5,
            current_lease=_lease(), repository="nhatnguyenquang1838-coder/gwc", now=NOW,
        )
        self.assertFalse(d.renewed)
        self.assertEqual(d.reconcile_reason, "BASE_DRIFT")

    # EARS #2: must not hide scope drift
    def test_scope_drift_routes_reconcile(self):
        d = evaluate_renewal(
            task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
            scope_hash="sha256:" + "f" * 64, base_sha=BASE_SHA, owner="hermes",
            fencing_token=5, current_lease=_lease(),
            repository="nhatnguyenquang1838-coder/gwc", now=NOW,
        )
        self.assertFalse(d.renewed)
        self.assertEqual(d.reconcile_reason, "SCOPE_DRIFT")

    # EARS #2: must not hide approval expiry
    def test_approval_expired_routes_reconcile(self):
        d = evaluate_renewal(
            task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
            scope_hash=SCOPE, base_sha=BASE_SHA, owner="hermes", fencing_token=5,
            current_lease=_lease(), repository="nhatnguyenquang1838-coder/gwc",
            now=NOW, approval_expires_at="2026-08-02T23:25:00Z",
        )
        self.assertFalse(d.renewed)
        self.assertEqual(d.reconcile_reason, "APPROVAL_EXPIRED")

    # EARS #2: must not hide stale worker (expired lease, no grace)
    def test_expired_lease_no_grace_routes_reconcile(self):
        d = evaluate_renewal(
            task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
            scope_hash=SCOPE, base_sha=BASE_SHA, owner="hermes", fencing_token=5,
            current_lease=_lease(expires_at="2026-08-02T23:00:00Z"),
            repository="nhatnguyenquang1838-coder/gwc", now=NOW,
        )
        self.assertFalse(d.renewed)
        self.assertEqual(d.reconcile_reason, "LEASE_EXPIRED_NO_GRACE")

    # EARS #3: fencing token must remain monotonic
    def test_fencing_not_monotonic_routes_reconcile(self):
        d = evaluate_renewal(
            task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
            scope_hash=SCOPE, base_sha=BASE_SHA, owner="hermes", fencing_token=4,
            current_lease=_lease(fencing_token=5),
            repository="nhatnguyenquang1838-coder/gwc", now=NOW,
        )
        self.assertFalse(d.renewed)
        self.assertEqual(d.reconcile_reason, "FENCING_NOT_MONOTONIC")

    # EARS #3: owner mismatch routes to reconcile (no hijack)
    def test_owner_mismatch_routes_reconcile(self):
        d = evaluate_renewal(
            task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
            scope_hash=SCOPE, base_sha=BASE_SHA, owner="kilo", fencing_token=5,
            current_lease=_lease(), repository="nhatnguyenquang1838-coder/gwc", now=NOW,
        )
        self.assertFalse(d.renewed)
        self.assertEqual(d.reconcile_reason, "OWNER_MISMATCH")

    # EARS #4: failed renewal routes to reconciliation, never blind retry
    def test_renew_lease_raises_on_reconcile(self):
        with self.assertRaises(LeaseRenewalError) as ctx:
            renew_lease(
                task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
                scope_hash=SCOPE, base_sha=BASE_SHA, owner="kilo", fencing_token=5,
                current_lease=_lease(), repository="nhatnguyenquang1838-coder/gwc", now=NOW,
            )
        self.assertIn("OWNER_MISMATCH", str(ctx.exception))


class TestReplaySafeDeterminism(unittest.TestCase):
    # EARS #4: same input -> same renewed lease + same digest (replay-safe)
    def test_deterministic_renewal_and_digest(self):
        args = dict(
            task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
            scope_hash=SCOPE, base_sha=BASE_SHA, owner="hermes", fencing_token=5,
            current_lease=_lease(), repository="nhatnguyenquang1838-coder/gwc", now=NOW,
        )
        l1 = renew_lease(**args)
        l2 = renew_lease(**args)
        self.assertEqual(l1.fencing_token, 6)
        self.assertEqual(lease_digest(l1), lease_digest(l2))

    def test_renewed_lease_carries_latest_token(self):
        lease = renew_lease(
            task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
            scope_hash=SCOPE, base_sha=BASE_SHA, owner="hermes", fencing_token=5,
            current_lease=_lease(), repository="nhatnguyenquang1838-coder/gwc", now=NOW,
        )
        self.assertEqual(lease.fencing_token, 6)
        self.assertEqual(lease.owner, "hermes")
        self.assertEqual(lease.base_sha, BASE_SHA)

    def test_grace_window_renewable(self):
        # expires exactly at NOW but within default 10-min grace from NOW onward
        d = evaluate_renewal(
            task_id="SCRUM-207", node_id="runtime_checkpoint.lease-renewal",
            scope_hash=SCOPE, base_sha=BASE_SHA, owner="hermes", fencing_token=5,
            current_lease=_lease(expires_at="2026-08-02T23:30:00Z"),
            repository="nhatnguyenquang1838-coder/gwc", now=NOW,
        )
        self.assertTrue(d.renewed)


if __name__ == "__main__":
    unittest.main()
