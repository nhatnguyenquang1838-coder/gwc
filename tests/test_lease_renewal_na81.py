"""NA81 current-task tests for SCRUM-330 (runtime_checkpoint.lease-renewal).

These tests validate the current brief's additional requirements that are NOT
proven by the historical SCRUM-207 test suite:
- SCRUM-330 / pre-prod / R4 binding (not SCRUM-207)
- renew only by the SAME actor/run (run_id binding, NA81 delta)
- different run rejected with RUN_ID_MISMATCH (fail-closed, never rebind to main)
- observed run mismatch rejected
- renewed lease preserves run_id lineage (owner/scope/authority unchanged)
- durable/idempotent readback: same inputs -> same renewed lease + same digest
- no regression: owner mismatch, expired lease still route to reconcile
"""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

# Make the repo ``tools/`` namespace package importable under bare
# ``python -m unittest discover -s tests`` (no PYTHONPATH set in CI — Python
# 3.12 namespace packages make only ``tools`` importable, not ``node_architect``).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from node_architect.lease_renewal import (
    Lease,
    LeaseRenewalError,
    RenewalDecision,
    evaluate_renewal,
    lease_digest,
    renew_lease,
)

TASK = "SCRUM-330"
RUN = "SCRUM-288-NA81-20260811-R4"
NODE = "runtime_checkpoint.lease-renewal"
REPO = "nhatnguyenquang1838-coder/gwc"
BRANCH = "auto/SCRUM-330-na81-20260810"
BASE = "173a2683908b349bb41e788008ed8f8679fe3bce"
SCOPE = "sha256:60a28922c6921e4fe6172aebef5a10a48f419427da132dc3e41f60c0856bcfa3"
NOW = "2026-08-12T06:40:00Z"


def _lease(run_id: str = RUN, **overrides) -> Lease:
    data = dict(
        lease_id="L-330",
        owner="Hermes",
        task_id=TASK,
        node_id=NODE,
        scope_hash=SCOPE,
        base_sha=BASE,
        fencing_token=5,
        issued_at=NOW,
        expires_at="2026-08-12T07:40:00Z",
        repository=REPO,
        run_id=run_id,
    )
    data.update(overrides)
    return Lease(**data)


def _renew_kwargs(**overrides):
    data = dict(
        task_id=TASK,
        node_id=NODE,
        scope_hash=SCOPE,
        base_sha=BASE,
        owner="Hermes",
        fencing_token=5,
        current_lease=_lease(),
        repository=REPO,
        now=NOW,
        run_id=RUN,
    )
    data.update(overrides)
    return data


class LeaseRenewalNa81Tests(unittest.TestCase):
    # Brief: renew only a currently valid lease held by the same actor/run.
    def test_valid_renewal_same_run_advances_token(self):
        d = evaluate_renewal(**_renew_kwargs())
        self.assertTrue(d.renewed)
        self.assertIsNone(d.reconcile_reason)
        self.assertEqual(d.lease.fencing_token, 6)

    # Brief: conflicting-owner renewals must fail deterministically (no hijack).
    def test_owner_mismatch_routes_reconcile(self):
        d = evaluate_renewal(**_renew_kwargs(owner="kilo"))
        self.assertFalse(d.renewed)
        self.assertEqual(d.reconcile_reason, "OWNER_MISMATCH")

    # NA81 delta: renewal under a different run must fail closed.
    def test_run_id_mismatch_routes_reconcile(self):
        d = evaluate_renewal(**_renew_kwargs(run_id="other-run-id"))
        self.assertFalse(d.renewed)
        self.assertEqual(d.reconcile_reason, "RUN_ID_MISMATCH")

    # NA81 delta: observed run differs from requested run -> fail closed.
    def test_observed_run_id_mismatch_routes_reconcile(self):
        d = evaluate_renewal(**_renew_kwargs(observed_run_id="other-observed-run"))
        self.assertFalse(d.renewed)
        self.assertEqual(d.reconcile_reason, "RUN_ID_MISMATCH")

    # Brief: renewal must not change owner/scope/authority; preserve run lineage.
    def test_renewed_lease_preserves_run_id_lineage(self):
        lease = renew_lease(**_renew_kwargs())
        self.assertEqual(lease.run_id, RUN)
        self.assertEqual(lease.owner, "Hermes")
        self.assertEqual(lease.task_id, TASK)
        self.assertEqual(lease.scope_hash, SCOPE)
        self.assertEqual(lease.base_sha, BASE)
        self.assertEqual(lease.repository, REPO)

    # Brief: expired lease renewal fails deterministically (no stale worker).
    def test_expired_lease_routes_reconcile(self):
        expired_lease = _lease(expires_at="2026-08-12T05:00:00Z")
        d = evaluate_renewal(**_renew_kwargs(current_lease=expired_lease))
        self.assertFalse(d.renewed)
        self.assertEqual(d.reconcile_reason, "LEASE_EXPIRED_NO_GRACE")

    # Brief: renewal must be idempotent/read back (same input -> same lease+digest).
    def test_idempotent_renewal_readback(self):
        l1 = renew_lease(**_renew_kwargs())
        l2 = renew_lease(**_renew_kwargs())
        self.assertEqual(l1.fencing_token, 6)
        self.assertEqual(lease_digest(l1), lease_digest(l2))

    # Brief: idempotent readback — identical renewal inputs produce an
    # identical digest (same evaluation time => same renewed lease identity).
    def test_deterministic_digest_same_inputs(self):
        a = evaluate_renewal(**_renew_kwargs(now="2026-08-12T06:40:00Z"))
        b = evaluate_renewal(**_renew_kwargs(now="2026-08-12T06:40:00Z"))
        self.assertEqual(lease_digest(a.lease), lease_digest(b.lease))

    # NA81 delta evidence: the run binding is captured in the lease digest, so a
    # renewal under a different run yields a distinct lease identity (readback
    # can distinguish run lineage). Construct leases manually to prove run_id is
    # part of the digest — two leases identical except run_id produce different
    # digests.
    def test_run_id_is_part_of_lease_digest(self):
        same = _lease(run_id=RUN)
        other = _lease(run_id="other-run-id")
        self.assertNotEqual(lease_digest(same), lease_digest(other))

    # renew_lease raises (not blind retry) on run mismatch.
    def test_renew_lease_raises_on_run_mismatch(self):
        with self.assertRaises(LeaseRenewalError) as ctx:
            renew_lease(**_renew_kwargs(run_id="other-run-id"))
        self.assertIn("RUN_ID_MISMATCH", str(ctx.exception))

    # Backward-compat: legacy lease with empty run_id still renews when no run
    # binding is requested (so historical SCRUM-207 flows keep working).
    def test_legacy_lease_without_run_id_still_renews(self):
        legacy = _lease(run_id="")
        d = evaluate_renewal(
            task_id=TASK, node_id=NODE, scope_hash=SCOPE, base_sha=BASE,
            owner="Hermes", fencing_token=5, current_lease=legacy,
            repository=REPO, now=NOW,
        )
        self.assertTrue(d.renewed)
        self.assertEqual(d.lease.run_id, "")


if __name__ == "__main__":
    unittest.main()
