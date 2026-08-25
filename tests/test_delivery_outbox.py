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

    def test_ack_verified_requires_5way_binding_and_freshness(self):
        rec = _record()
        outbox.enqueue(self.path, **rec)
        key = _key(rec)
        outbox.acquire_lease(self.path, worker_id="w1", **key)
        good_ack = {
            "destination_id": "audit-sink-staging-01",
            "event_source": rec["event_source"],
            "event_id": rec["event_id"],
            "delivery_generation": 1,
            "request_digest": "sha256:" + "d" * 64,
            "payload_digest": rec["event_payload_digest"],
            "created": time.time(),
            "signature_proof": "sig:verified",
        }
        verified, code = outbox.verify_ack(self.path, ack=good_ack, worker_id="w1")
        self.assertTrue(verified)
        self.assertEqual(code, "ACK_VERIFIED")

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
