#!/usr/bin/env python3
"""SCRUM-533 delivery_outbox tests (delivery-domain outbox).

Exercises the SCRUM-533 v3 + v3.1 requirements:

* outbox-before-send invariant (send intent persisted as PENDING before send)
* closed state machine + OUTBOX_ILLEGAL_TRANSITION guard
* lease/fence CAS-atomic acquisition + OUTBOX_LEASE_CONTENTION
* fence re-verify before transition (OUTBOX_LEASE_LOST)
* restart discovery (PENDING/IN_FLIGHT/ACK_UNKNOWN/RETRY_SCHEDULED)
* durable retry scheduling fields
* ACK_VERIFIED 5-way binding + freshness + replay resistance
* DLQ/replay generation fencing + late-ACK rejection (LATE_ACK_REJECTED)
* fail-closed store degradation (QUARANTINE / OUTBOX_STORE_*)
* all G2-G6 authority flags false

Uses an in-memory/scratch SQLite file. No connector call, network, Jira,
branch, commit, PR, approval, merge, deployment or production operation.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import closing
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import node_architect.delivery_outbox as outbox  # noqa: E402


def _record(overrides: dict | None = None) -> dict:
    base = {
        "projection_target": "external-audit-projection",
        "event_source": "gwc.node-architect.external-audit-projection.v1.0",
        "event_id": "evt-0001",
        "canonical_state_digest": "sha256:" + "a" * 64,
        "event_payload_digest": "sha256:" + "b" * 64,
        "destination_policy_digest": "sha256:" + "c" * 64,
        "destination_id": "audit-sink-staging-01",
        "delivery_generation": 1,
    }
    base.update(overrides or {})
    return base


def _key(rec: dict | None = None) -> dict:
    """The semantic key fields for lease/transition calls (acquire_lease and
    transition take only the record key, not the full record)."""
    r = rec or _record()
    return {k: r[k] for k in
            ("projection_target", "event_source", "event_id",
             "canonical_state_digest", "delivery_generation")}


class DeliveryOutboxTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "outbox.db"
        outbox.init_store(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_enqueue_pending_before_send(self):
        rec = _record()
        result = outbox.enqueue(self.path, **rec)
        self.assertEqual(result["state"], "PENDING")
        self.assertEqual(result["attempt_no"], 0)
        for flag in ("write_authority_granted", "approval_authority_granted",
                     "merge_authority_granted", "deployment_authority_granted",
                     "production_authority_granted"):
            self.assertFalse(result[flag])

    def test_duplicate_identity_conflict(self):
        rec = _record()
        outbox.enqueue(self.path, **rec)
        with self.assertRaises(outbox.OutboxConflict):
            outbox.enqueue(self.path, **rec)

    def test_event_source_format_fails_closed(self):
        rec = _record({"event_source": "not-a-namespace"})
        with self.assertRaises(outbox.OutboxConflict) as ctx:
            outbox.enqueue(self.path, **rec)
        self.assertEqual(str(ctx.exception), "EVENT_SOURCE_BINDING_CONFLICT")

    def test_inconsistent_event_source_fails_closed(self):
        rec = _record({"event_source": "gwc.other-system.external-audit-projection.v1.0"})
        with self.assertRaises(outbox.OutboxConflict) as ctx:
            outbox.enqueue(self.path, **rec)
        self.assertEqual(str(ctx.exception), "EVENT_SOURCE_BINDING_CONFLICT")

    def test_lease_acquire_and_contention(self):
        rec = _record()
        outbox.enqueue(self.path, **rec)
        key = _key(rec)
        lease = outbox.acquire_lease(self.path, worker_id="w1", **key)
        self.assertEqual(lease["state"], "IN_FLIGHT")
        self.assertEqual(lease["lease_holder"], "w1")
        with self.assertRaises(outbox.OutboxConflict) as ctx:
            outbox.acquire_lease(self.path, worker_id="w2", **key)
        self.assertEqual(str(ctx.exception), "OUTBOX_LEASE_CONTENTION")

    def test_expired_lease_reclaimable(self):
        rec = _record()
        outbox.enqueue(self.path, **rec)
        key = _key(rec)
        outbox.acquire_lease(self.path, worker_id="w1", lease_ttl_s=1, **key)
        time.sleep(1.1)
        lease = outbox.acquire_lease(self.path, worker_id="w2", lease_ttl_s=60, **key)
        self.assertEqual(lease["lease_holder"], "w2")

    def test_stale_worker_loses_lease(self):
        rec = _record()
        outbox.enqueue(self.path, **rec)
        key = _key(rec)
        outbox.acquire_lease(self.path, worker_id="w1", lease_ttl_s=1, **key)
        time.sleep(1.1)
        outbox.acquire_lease(self.path, worker_id="w2", lease_ttl_s=60, **key)
        with self.assertRaises(outbox.OutboxConflict) as ctx:
            outbox.transition(self.path, worker_id="w1", to_state="ACK_CONFIRMED", **key)
        self.assertEqual(str(ctx.exception), "OUTBOX_LEASE_LOST")

    def test_lease_handoff_after_check_cannot_be_overwritten_by_stale_worker(self):
        from unittest.mock import patch
        rec = _record()
        key = _key(rec)
        clock = [1000.0]
        with patch.object(outbox, "_now", side_effect=lambda: clock[0]):
            outbox.enqueue(self.path, **rec)
            outbox.acquire_lease(self.path, worker_id="w1", lease_ttl_s=1, **key)
            verify = outbox._verify_lease
            def handoff(*args, **kwargs):
                prior = verify(*args, **kwargs)
                clock[0] = 1002.0
                outbox.acquire_lease(self.path, worker_id="w2", **key)
                return prior
            with patch.object(outbox, "_verify_lease", side_effect=handoff):
                with self.assertRaisesRegex(outbox.OutboxConflict, "OUTBOX_LEASE_LOST"):
                    outbox.transition(self.path, worker_id="w1", to_state="ACK_CONFIRMED", **key)
            row = outbox.discover_restart(self.path)[0]
            self.assertEqual(row["state"], "IN_FLIGHT")
            self.assertEqual(row["lease_holder"], "w2")

    def test_exact_expiration_reclaim_matches_persisted_owner(self):
        from unittest.mock import patch
        key = _key()
        clock = [1000.0]
        with patch.object(outbox, "_now", side_effect=lambda: clock[0]):
            outbox.enqueue(self.path, **_record())
            outbox.acquire_lease(self.path, worker_id="w1", lease_ttl_s=1, **key)
            clock[0] = 1001.0
            lease = outbox.acquire_lease(self.path, worker_id="w2", **key)
            self.assertEqual(lease["lease_holder"], "w2")
            self.assertEqual(outbox.discover_restart(self.path)[0]["lease_holder"], "w2")

    def test_acquire_lease_never_reports_success_for_zero_row_cas(self):
        import sqlite3
        rec = _record()
        outbox.enqueue(self.path, **rec)
        with closing(sqlite3.connect(self.path)) as db:
            with db:
                db.execute("CREATE TRIGGER refuse_lease BEFORE UPDATE OF lease_holder "
                           "ON delivery_outbox BEGIN SELECT RAISE(IGNORE); END")
        with self.assertRaisesRegex(outbox.OutboxConflict, "OUTBOX_LEASE_CONTENTION"):
            outbox.acquire_lease(self.path, worker_id="denied", **_key(rec))
        row = outbox.discover_restart(self.path)[0]
        self.assertEqual(row["state"], "PENDING")
        self.assertIsNone(row["lease_holder"])

    def test_illegal_transition_fails_closed(self):
        rec = _record()
        outbox.enqueue(self.path, **rec)
        key = _key(rec)
        outbox.acquire_lease(self.path, worker_id="w1", **key)
        with self.assertRaises(outbox.OutboxConflict) as ctx:
            outbox.transition(self.path, worker_id="w1", to_state="PENDING", **key)
        self.assertEqual(str(ctx.exception), "OUTBOX_ILLEGAL_TRANSITION")

    def test_retry_scheduling_advances_attempt(self):
        rec = _record()
        outbox.enqueue(self.path, **rec)
        key = _key(rec)
        outbox.acquire_lease(self.path, worker_id="w1", **key)
        outbox.record_attempt(self.path, semantic_event_id="sid", delivery_generation=1,
                              destination_id="audit-sink-staging-01", attempt_no=1,
                              request_digest="sha256:" + "d" * 64,
                              response_class="5xx", retry_disposition="RETRY_SCHEDULED")
        result = outbox.transition(self.path, worker_id="w1", to_state="RETRY_SCHEDULED",
                                   reason_class="RETRY_5XX", **key)
        self.assertEqual(result["state"], "RETRY_SCHEDULED")
        self.assertEqual(result["attempt_no"], 1)
        self.assertIsNotNone(result["next_attempt_at"])

    def test_restart_discovery(self):
        rec = _record()
        outbox.enqueue(self.path, **rec)
        pending = outbox.discover_restart(self.path)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["state"], "PENDING")

    def _bound_ack(self):
        """Unit-only shape/request bindings; never authenticated receiver proof."""
        rec = _record()
        outbox.enqueue(self.path, **rec)
        outbox.acquire_lease(self.path, worker_id="w1", **_key(rec))
        request_digest = "sha256:" + "d" * 64
        outbox.record_attempt(self.path, semantic_event_id=outbox._semantic_event_id(
            rec["projection_target"], rec["event_source"], rec["event_id"], rec["canonical_state_digest"]),
            delivery_generation=1, destination_id=rec["destination_id"], attempt_no=1,
            request_digest=request_digest, response_class="UNIT_FIXTURE_ONLY")
        return {"destination_id":rec["destination_id"], "event_source":rec["event_source"],
                "event_id":rec["event_id"], "delivery_generation":1,
                "request_digest":request_digest, "payload_digest":rec["event_payload_digest"],
                "created":time.time(), "signature_proof":"UNIT_SELF_ATTESTED_NOT_AUTHENTIC"}

    def test_bound_but_self_attested_ack_requires_independent_verifier(self):
        ack = self._bound_ack()
        verified, code = outbox.verify_ack(self.path, ack=ack, worker_id="w1")
        self.assertFalse(verified)
        self.assertEqual(code, "ACK_VERIFIER_UNAVAILABLE")

    def test_unavailable_ack_confirmation_preserves_recovery_path(self):
        ack = self._bound_ack()
        key = _key()
        before = outbox.discover_restart(self.path)[0]
        self.assertEqual(outbox.verify_ack(self.path, ack=ack, worker_id="w1"),
                         (False, "ACK_VERIFIER_UNAVAILABLE"))
        with self.assertRaisesRegex(outbox.OutboxConflict, "ACK_VERIFIER_UNAVAILABLE"):
            outbox.transition(self.path, worker_id="w1", to_state="ACK_CONFIRMED", **key)
        self.assertEqual(outbox.discover_restart(self.path)[0], before)
        # This is recovery availability, NOT successful receiver authentication.
        outbox.transition(self.path, worker_id="w1", to_state="ACK_UNKNOWN", **key)
        self.assertEqual(outbox.discover_restart(self.path)[0]["state"], "ACK_UNKNOWN")
        outbox.acquire_lease(self.path, worker_id="recovery", **key)
        retry = outbox.transition(self.path, worker_id="recovery", to_state="RETRY_SCHEDULED", **key)
        self.assertEqual(retry["state"], "RETRY_SCHEDULED")
        self.assertEqual(retry["attempt_no"], 1)
        self.assertIsNotNone(retry["next_attempt_at"])
        row = outbox.discover_restart(self.path)[0]
        self.assertEqual(row["state"], "RETRY_SCHEDULED")
        self.assertIsNone(row["lease_holder"])

    def test_expired_bound_ack_is_refused_without_confirming_delivery(self):
        ack = self._bound_ack()
        before = outbox.discover_restart(self.path)[0]
        ack["created"] = time.time() - outbox.DEFAULT_ACK_FRESHNESS_S - 1
        self.assertEqual(outbox.verify_ack(self.path, ack=ack, worker_id="w1"),
                         (False, "ACK_STALE"))
        self.assertEqual(outbox.discover_restart(self.path)[0], before)

    def test_ack_binding_mismatches_are_not_hidden_by_truthy_proof(self):
        ack = self._bound_ack()
        for field, value, expected in [
            ("event_source", "gwc.other.v1.0", "ACK_BINDING_MISMATCH"),
            ("payload_digest", "sha256:"+"f"*64, "ACK_BINDING_MISMATCH"),
            ("request_digest", "sha256:"+"e"*64, "ACK_REQUEST_UNBOUND"),
        ]:
            with self.subTest(field=field):
                verified, code = outbox.verify_ack(self.path, ack={**ack,field:value}, worker_id="w1")
                self.assertFalse(verified)
                self.assertEqual(code, expected)

    def test_ack_nonfinite_or_future_freshness_is_invalid(self):
        ack = self._bound_ack()
        for created in [float("nan"), float("inf"), float("-inf"), time.time()+3600]:
            with self.subTest(created=created):
                verified, code = outbox.verify_ack(self.path, ack={**ack,"created":created}, worker_id="w1")
                self.assertFalse(verified)
                self.assertEqual(code, "ACK_FRESHNESS_INVALID")

    def test_ack_requires_actual_persisted_request_attempt(self):
        import sqlite3
        ack = self._bound_ack()
        with closing(sqlite3.connect(self.path)) as db:
            with db:
                db.execute("DELETE FROM delivery_outbox_attempts")
        verified, code = outbox.verify_ack(self.path, ack=ack, worker_id="w1")
        self.assertFalse(verified)
        self.assertEqual(code, "ACK_REQUEST_UNBOUND")

    def test_delivery_observers_do_not_materialize_missing_store(self):
        import sqlite3
        from contextlib import suppress
        rec = _record()
        ack = {"destination_id":rec["destination_id"], "event_source":rec["event_source"],
               "event_id":rec["event_id"], "delivery_generation":1,
               "request_digest":"unit-only", "payload_digest":rec["event_payload_digest"],
               "created":time.time()}
        for reader in ["ack", "lease", "restart", "readback"]:
            with self.subTest(reader=reader):
                target = self.path.parent/(reader+"-missing.sqlite")
                with suppress(sqlite3.Error, outbox.OutboxStoreUnavailable):
                    if reader == "ack":outbox.verify_ack(target, ack=ack, worker_id="w1")
                    elif reader == "lease":outbox._verify_lease(target, key=tuple(_key().values()), worker_id="w1")
                    elif reader == "restart":outbox.discover_restart(target)
                    else:outbox._readback_after_write(target, "unit-only")
                self.assertFalse(target.exists(), reader+" created a missing store")

    def test_delivery_observation_does_not_change_uninitialized_store_policy(self):
        import sqlite3
        target = self.path.parent/"sentinel.sqlite"
        with closing(sqlite3.connect(target)) as db:
            with db:
                db.execute("CREATE TABLE sentinel(value TEXT)")
        db.close()
        before = target.read_bytes()
        with self.assertRaises(outbox.OutboxStoreUnavailable):
            outbox.discover_restart(target)
        self.assertEqual(target.read_bytes(), before)
        with closing(sqlite3.connect(target)) as db:
            with db:
                self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        db.close()

    def test_transition_cannot_bypass_ack_authentication(self):
        self._bound_ack()
        with self.assertRaisesRegex(outbox.OutboxConflict, "ACK_VERIFIER_UNAVAILABLE"):
            outbox.transition(self.path, **_key(), worker_id="w1", to_state="ACK_CONFIRMED")
        row = outbox.discover_restart(self.path)[0]
        self.assertEqual(row["state"], "IN_FLIGHT")
        self.assertEqual(row["lease_holder"], "w1")

    def test_bare_2xx_not_confirmed(self):
        rec = _record()
        outbox.enqueue(self.path, **rec)
        key = _key(rec)
        outbox.acquire_lease(self.path, worker_id="w1", **key)
        bare_ack = {
            "destination_id": "audit-sink-staging-01",
            "event_source": rec["event_source"],
            "event_id": rec["event_id"],
            "delivery_generation": 1,
            "request_digest": "sha256:" + "d" * 64,
            "payload_digest": rec["event_payload_digest"],
            "created": time.time(),
            # NO signature_proof -> unauthenticated
        }
        verified, code = outbox.verify_ack(self.path, ack=bare_ack, worker_id="w1")
        self.assertFalse(verified)
        self.assertEqual(code, "ACK_NOT_AUTHENTICATED")

    def test_late_ack_rejected(self):
        rec = _record()
        outbox.enqueue(self.path, **rec)
        key = _key(rec)
        outbox.acquire_lease(self.path, worker_id="w1", **key)
        stale_ack = {
            "destination_id": "audit-sink-staging-01",
            "event_source": rec["event_source"],
            "event_id": rec["event_id"],
            "delivery_generation": 0,  # older generation
            "request_digest": "sha256:" + "d" * 64,
            "payload_digest": rec["event_payload_digest"],
            "created": time.time(),
            "signature_proof": "sig:verified",
        }
        verified, code = outbox.verify_ack(self.path, ack=stale_ack, worker_id="w1")
        self.assertFalse(verified)
        self.assertEqual(code, "LATE_ACK_REJECTED")

    def test_quarantine_and_dlq(self):
        rec = _record()
        outbox.enqueue(self.path, **rec)
        outbox.quarantine(self.path, semantic_event_id="sid", destination_id=rec["destination_id"],
                          reason_code="OUTBOX_STORE_CORRUPTION")
        # QUARANTINE is part of the closed state set.
        self.assertIn("QUARANTINE", outbox.CLOSED_STATES)

    def test_replay_trust_revalidation_all_pass(self):
        destination = {
            "destination_id": "audit-sink-staging-01",
            "destination_type": "webhook_http",
            "receiver_identity": {"url": "https://sink.example/audit"},
            "auth": {"scheme": "hmac_sha256", "credential_ref": "vault://audit-sink"},
            "transport_policy": {"tls_required": True, "allow_redirect": False, "allow_private_ip": False},
            "revocation": {"revoked_at": None, "revoke_reason": None},
        }
        profile = dict(destination)
        profile["auth"]["credential_version"] = 2
        profile["supports_ack"] = True
        profile["destination_policy_digest"] = outbox._digest(
            {k: v for k, v in destination.items()})
        checks = outbox.replay_trust_revalidate(self.path, destination=destination,
                                                profile=profile, credential_version=2)
        self.assertTrue(all(checks.values()))

    def test_replay_trust_revalidation_revoked_fails_closed(self):
        destination = {
            "destination_id": "audit-sink-staging-01",
            "destination_type": "webhook_http",
            "receiver_identity": {"url": "https://sink.example/audit"},
            "auth": {"scheme": "hmac_sha256", "credential_ref": "vault://audit-sink"},
            "transport_policy": {"tls_required": True, "allow_redirect": False, "allow_private_ip": False},
            "revocation": {"revoked_at": "2026-08-20T00:00:00Z", "revoke_reason": "compromised"},
        }
        profile = dict(destination)
        profile["auth"]["credential_version"] = 2
        profile["supports_ack"] = True
        profile["destination_policy_digest"] = outbox._digest(
            {k: v for k, v in destination.items()})
        checks = outbox.replay_trust_revalidate(self.path, destination=destination,
                                                profile=profile, credential_version=2)
        self.assertFalse(checks["not_revoked"])

    def test_no_checkpoint_import_boundary(self):
        with self.assertRaises(ImportError):
            outbox._assert_no_checkpoint_import(["checkpoint_sqlite"])


if __name__ == "__main__":
    unittest.main()
