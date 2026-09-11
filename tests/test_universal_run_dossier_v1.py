#!/usr/bin/env python3
"""R6 certification tests: Run Dossier evidence, distinct G3/G4/G5 records,
target validation, ClosureReceipt, HandoffReceipt, and durable RunLedger append.

C7 (distinct G3 verification, G4 binding, G5 validation and G6
Closure/HandoffReceipt) per the C1-C15 matrix. Composes E1 kernel digest
primitives and the authority EffectDecisionReceipt; reuses record-envelope +
child-run-materialization-receipt schema shapes.

Pure / read-only: never persists to external stores, never grants authority,
never mutates targets. RunLedger append is an in-memory durable log facade.
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.node_architect.universal_run_kernel import UNIVERSAL_PROFILE
from tools.node_architect.universal_run_dossier import (
    ClosureReceipt,
    DossierError,
    HandoffReceipt,
    RunDossier,
    RunLedger,
    append_receipt_to_ledger,
    create_closure_receipt,
    create_handoff_receipt,
    create_run_dossier,
    validate_dossier,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE = UNIVERSAL_PROFILE


class TestRunDossier(unittest.TestCase):
    """C7: Run Dossier digest-bound with distinct G3/G4/G5 records."""

    def test_create_dossier(self):
        d = create_run_dossier(
            run_id="run-1",
            g3_records=[{"review": "G3 pass"}],
            g4_records=[{"binding": "G4 receipt"}],
            g5_records=[{"validation": "G5 pass"}],
        )
        self.assertIsInstance(d, RunDossier)
        self.assertEqual(len(d.g3_records), 1)
        self.assertEqual(len(d.g4_records), 1)
        self.assertEqual(len(d.g5_records), 1)
        self.assertNotEqual(d.dossier_digest, "")

    def test_g3_g4_g5_distinct(self):
        # Records must remain in distinct gate buckets, never merged.
        d = create_run_dossier(
            run_id="run-1",
            g3_records=[{"review": "r1"}],
            g4_records=[{"binding": "b1"}],
            g5_records=[{"validation": "v1"}],
        )
        self.assertEqual(d.g3_records[0]["review"], "r1")
        self.assertNotIn("binding", d.g3_records[0])
        self.assertEqual(d.g4_records[0]["binding"], "b1")

    def test_dossier_digest_deterministic(self):
        kwargs = dict(run_id="run-1", g3_records=[{"a": 1}], g4_records=[], g5_records=[])
        a = create_run_dossier(**kwargs)
        b = create_run_dossier(**kwargs)
        self.assertEqual(a.dossier_digest, b.dossier_digest)

    def test_validate_dossier_ok(self):
        d = create_run_dossier(run_id="run-1", g3_records=[{"a": 1}], g4_records=[], g5_records=[])
        self.assertTrue(validate_dossier(d))

    def test_validate_dossier_tamper_fails(self):
        d = create_run_dossier(run_id="run-1", g3_records=[{"a": 1}], g4_records=[], g5_records=[])
        tampered = RunDossier.from_dict(d.to_dict())
        tampered._replace_g3([{"a": 999}])
        self.assertFalse(validate_dossier(tampered))


class TestClosureReceipt(unittest.TestCase):
    """C7: ClosureReceipt (G6) is typed and digest-bound."""

    def test_create_closure_receipt(self):
        r = create_closure_receipt(
            run_id="run-1", gate="G6",
            closure_reason="all evidence present",
        )
        self.assertIsInstance(r, ClosureReceipt)
        self.assertEqual(r.gate, "G6")
        self.assertTrue(r.receipt_digest.startswith("sha256:"))

    def test_closure_requires_g6(self):
        with self.assertRaises(DossierError):
            create_closure_receipt(
                run_id="run-1", gate="G3",
                closure_reason="wrong gate",
            )

    def test_closure_digest_deterministic(self):
        kwargs = dict(run_id="run-1", gate="G6", closure_reason="done")
        a = create_closure_receipt(**kwargs)
        b = create_closure_receipt(**kwargs)
        self.assertEqual(a.receipt_digest, b.receipt_digest)


class TestHandoffReceipt(unittest.TestCase):
    """C7: HandoffReceipt with target validation + child acceptance."""

    def test_create_handoff_receipt(self):
        r = create_handoff_receipt(
            run_id="run-1",
            target_validation={"target": "gwc/main", "validated": True},
            child_acceptance=[{"child": "child-1", "accepted": True}],
        )
        self.assertIsInstance(r, HandoffReceipt)
        self.assertTrue(r.receipt_digest.startswith("sha256:"))

    def test_handoff_requires_target_validation(self):
        with self.assertRaises(DossierError):
            create_handoff_receipt(
                run_id="run-1",
                target_validation=None,
                child_acceptance=[],
            )

    def test_handoff_digest_deterministic(self):
        kwargs = dict(
            run_id="run-1",
            target_validation={"target": "gwc/main", "validated": True},
            child_acceptance=[{"child": "child-1", "accepted": True}],
        )
        a = create_handoff_receipt(**kwargs)
        b = create_handoff_receipt(**kwargs)
        self.assertEqual(a.receipt_digest, b.receipt_digest)


class TestRunLedgerDurableAppend(unittest.TestCase):
    """@bmad/@ua advisory: receipts must be durably appended (serializable)."""

    def test_append_receipt_to_ledger(self):
        ledger = RunLedger(run_id="run-1")
        receipt = create_closure_receipt(run_id="run-1", gate="G6", closure_reason="done")
        updated = append_receipt_to_ledger(ledger, receipt.to_dict())
        self.assertEqual(len(updated.entries), 1)
        self.assertEqual(updated.entries[0]["artifact_type"], "closure-receipt")

    def test_ledger_round_trip(self):
        ledger = RunLedger(run_id="run-1")
        closure = create_closure_receipt(run_id="run-1", gate="G6", closure_reason="done")
        handoff = create_handoff_receipt(
            run_id="run-1",
            target_validation={"target": "gwc/main", "validated": True},
            child_acceptance=[],
        )
        ledger = append_receipt_to_ledger(ledger, closure.to_dict())
        ledger = append_receipt_to_ledger(ledger, handoff.to_dict())
        # Serialization round-trip must preserve entries (durable).
        restored = RunLedger.from_dict(ledger.to_dict())
        self.assertEqual(len(restored.entries), 2)
        self.assertEqual(restored.entries[0]["artifact_type"], "closure-receipt")
        self.assertEqual(restored.entries[1]["artifact_type"], "handoff-receipt")

    def test_ledger_append_immutable(self):
        # Appending must not mutate the original ledger in place.
        ledger = RunLedger(run_id="run-1")
        receipt = create_closure_receipt(run_id="run-1", gate="G6", closure_reason="done")
        updated = append_receipt_to_ledger(ledger, receipt.to_dict())
        self.assertEqual(len(ledger.entries), 0)
        self.assertEqual(len(updated.entries), 1)


if __name__ == "__main__":
    unittest.main()


class JiraTicketReferenceTests(unittest.TestCase):
    """Hardening GAP 4: jira_ticket_reference in certification campaign state."""

    def test_campaign_state_has_jira_ticket_reference(self):
        from tools.node_architect.universal_run_dossier import build_campaign_state
        state = build_campaign_state(campaign_id="RP-CERT-001", jira_ticket_reference="SCRUM-677")
        self.assertEqual(state["jira_ticket_reference"], "SCRUM-677")

    def test_campaign_state_requires_jira_ticket_reference(self):
        from tools.node_architect.universal_run_dossier import (
            DossierError,
            build_campaign_state,
        )
        with self.assertRaises(DossierError):
            build_campaign_state(campaign_id="RP-CERT-001", jira_ticket_reference="")
