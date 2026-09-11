#!/usr/bin/env python3
"""R8 certification tests: 3-domain fixture certification, fresh recovery,
adversarial failure-code matrix.

C13 (universal certification across software/research/non-software fixtures;
same-kernel assertions; fresh recovery; exact refs) and C14 (adversarial,
recovery and failure-code certification) per the C1-C15 matrix. Composes the
full universal_run_* module stack under one certification harness.

Pure / read-only: never persists, never grants authority, never mutates targets.
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.node_architect.universal_run_certification import (
    CertificationError,
    DomainFixture,
    FailureCodeMatrix,
    certify_fixture,
    certify_three_domains,
    classify_failure_code,
    validate_fresh_recovery,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DOMAINS = ("software", "research", "non-software")


class TestC13ThreeDomainCertification(unittest.TestCase):
    """C13: same-kernel assertions across 3 domain fixtures."""

    def test_certify_three_domains_all_pass(self):
        result = certify_three_domains(
            fixtures=[
                DomainFixture(domain="software", payload={"node": "sw-1"}),
                DomainFixture(domain="research", payload={"node": "rs-1"}),
                DomainFixture(domain="non-software", payload={"node": "ns-1"}),
            ]
        )
        self.assertEqual(result["domains_certified"], 3)
        self.assertTrue(result["all_pass"])

    def test_same_kernel_assertions(self):
        # All 3 domains must run through the same kernel path.
        result = certify_three_domains(
            fixtures=[
                DomainFixture(domain="software", payload={"node": "sw-1"}),
                DomainFixture(domain="research", payload={"node": "rs-1"}),
                DomainFixture(domain="non-software", payload={"node": "ns-1"}),
            ]
        )
        kernel_refs = {f["kernel_ref"] for f in result["fixture_results"]}
        self.assertEqual(len(kernel_refs), 1, "all domains must share one kernel ref")

    def test_duplicate_domain_rejected(self):
        with self.assertRaises(CertificationError):
            certify_three_domains(
                fixtures=[
                    DomainFixture(domain="software", payload={"node": "a"}),
                    DomainFixture(domain="software", payload={"node": "b"}),
                    DomainFixture(domain="research", payload={"node": "c"}),
                ]
            )

    def test_unknown_domain_rejected(self):
        with self.assertRaises(CertificationError):
            certify_three_domains(
                fixtures=[
                    DomainFixture(domain="hardware", payload={"node": "a"}),
                ]
            )

    def test_fixture_digest_deterministic(self):
        a = certify_fixture(DomainFixture(domain="software", payload={"node": "sw-1"}))
        b = certify_fixture(DomainFixture(domain="software", payload={"node": "sw-1"}))
        self.assertEqual(a["fixture_digest"], b["fixture_digest"])


class TestC13FreshRecovery(unittest.TestCase):
    """C13: fresh recovery validation."""

    def test_fresh_recovery_ok(self):
        result = validate_fresh_recovery(
            run_id="run-1",
            recovery_evidence={"cursor": 0, "ledger_entries": 0},
            expected_cursor=0,
        )
        self.assertTrue(result["fresh"])
        self.assertEqual(result["recovery_decision"], "FRESH")

    def test_fresh_recovery_rejects_dirty(self):
        result = validate_fresh_recovery(
            run_id="run-1",
            recovery_evidence={"cursor": 5, "ledger_entries": 3},
            expected_cursor=0,
        )
        self.assertFalse(result["fresh"])
        self.assertEqual(result["recovery_decision"], "STALE")


class TestC14AdversarialFailureCodes(unittest.TestCase):
    """C14: adversarial failure-code matrix."""

    def test_classify_failure_code_known(self):
        code = classify_failure_code("LIFECYCLE_EDGE_UNDECLARED")
        self.assertEqual(code["severity"], "ILLEGAL_TRANSITION")

    def test_classify_failure_code_unknown_fails_closed(self):
        code = classify_failure_code("UNKNOWN_MADE_UP")
        self.assertEqual(code["severity"], "UNKNOWN")

    def test_failure_code_matrix_complete(self):
        matrix = FailureCodeMatrix(codes=[
            "LIFECYCLE_EDGE_UNDECLARED",
            "LIFECYCLE_ACTION_UNKNOWN",
            "AUTHORITY_SELF_GRANT_FORBIDDEN",
            "AUTHORITY_STALE",
            "DAG_BUDGET_EXCEEDED",
            "SINGLE_ACTIVE_VIOLATION",
            "CURSOR_RECOVERY_VIOLATION",
            "PLAN_DRIFT_DETECTED",
            "LEGACY_NAMESPACE_INVALID",
            "CLOSURE_GATE_MUST_BE_G6",
        ])
        result = matrix.certify()
        self.assertTrue(result["complete"])
        self.assertEqual(result["code_count"], 10)

    def test_failure_code_matrix_missing_fails(self):
        matrix = FailureCodeMatrix(codes=["LIFECYCLE_EDGE_UNDECLARED"])
        result = matrix.certify()
        self.assertFalse(result["complete"])


if __name__ == "__main__":
    unittest.main()


class EvidenceRejectionTests(unittest.TestCase):
    """Hardening GAP 2: stale/missing evidence rejection reason codes."""

    def test_missing_evidence_rejected(self):
        from tools.node_architect.universal_run_certification import (
            EvidenceRejectionError,
            validate_evidence_refs,
        )
        with self.assertRaises(EvidenceRejectionError) as ctx:
            validate_evidence_refs(run_id="RUN-P", evidence_refs=["evidence/a.json", "evidence/missing.json"],
                                   available={"evidence/a.json": "sha256:" + "a" * 64})
        self.assertEqual(ctx.exception.code, "EVIDENCE_MISSING")

    def test_stale_evidence_rejected(self):
        from tools.node_architect.universal_run_certification import (
            EvidenceRejectionError,
            validate_evidence_refs,
        )
        with self.assertRaises(EvidenceRejectionError) as ctx:
            validate_evidence_refs(run_id="RUN-P", evidence_refs=["evidence/a.json"],
                                   available={"evidence/a.json": "sha256:" + "a" * 64},
                                   expected_digest="sha256:" + "b" * 64)
        self.assertEqual(ctx.exception.code, "EVIDENCE_STALE")

    def test_all_evidence_valid(self):
        from tools.node_architect.universal_run_certification import validate_evidence_refs
        r = validate_evidence_refs(run_id="RUN-P", evidence_refs=["evidence/a.json"],
                                   available={"evidence/a.json": "sha256:" + "a" * 64},
                                   expected_digest="sha256:" + "a" * 64)
        self.assertTrue(r["ok"])
        self.assertEqual(r["reason_code"], "EVIDENCE_VALID")
