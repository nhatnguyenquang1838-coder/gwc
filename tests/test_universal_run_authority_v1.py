#!/usr/bin/env python3
"""R5 certification tests: orthogonal authority issuance, AuthorityDecisionReceipt,
stale/self-grant fail-closed enforcement, and cumulative module manifest.

C6 (authority orthogonal to gates, every effect has a decision receipt) and
C10 (authority cannot self-grant; stale/invalid authority fails closed) per the
C1-C15 matrix. Composes E1 kernel digest primitives; reuses authority-boundary
semantics from gate_state_resolution/authority_boundary_check.

Pure / read-only: never persists, never grants authority, never mutates targets.
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.node_architect.universal_run_kernel import UNIVERSAL_PROFILE
from tools.node_architect.universal_run_authority import (
    AuthorityDecisionReceipt,
    AuthorityError,
    SelfGrantError,
    StaleAuthorityError,
    build_modules_manifest,
    issue_authority,
    resolve_authority,
    validate_authority,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE = UNIVERSAL_PROFILE


class TestAuthorityIssuance(unittest.TestCase):
    """C6: authority issuance is orthogonal and produces a decision receipt."""

    def test_issue_authority_produces_receipt(self):
        receipt = issue_authority(
            task_id="SCRUM-668",
            authority_id="auth-1",
            grantee="dwa-hermes",
            action="G3_REVIEW",
            issued_by="analyzer-hitl",
        )
        self.assertIsInstance(receipt, AuthorityDecisionReceipt)
        self.assertEqual(receipt.action, "G3_REVIEW")
        self.assertEqual(receipt.grantee, "dwa-hermes")
        self.assertTrue(receipt.receipt_digest.startswith("sha256:"))

    def test_receipt_is_deterministic(self):
        kwargs = dict(task_id="SCRUM-668", authority_id="auth-1", grantee="dwa-hermes",
                      action="G3_REVIEW", issued_by="analyzer-hitl")
        a = issue_authority(**kwargs)
        b = issue_authority(**kwargs)
        self.assertEqual(a.receipt_digest, b.receipt_digest)

    def test_authority_orthogonal_to_gates(self):
        # Same authority must be issuable for any gate action; it is not bound
        # to a single gate in a way that prevents reuse.
        r1 = issue_authority(task_id="SCRUM-668", authority_id="a1", grantee="x",
                             action="G3_REVIEW", issued_by="y")
        r2 = issue_authority(task_id="SCRUM-668", authority_id="a2", grantee="x",
                             action="G5_DEPLOY", issued_by="y")
        self.assertNotEqual(r1.action, r2.action)
        self.assertNotEqual(r1.receipt_digest, r2.receipt_digest)

    def test_invalid_issuer_fails_closed(self):
        with self.assertRaises(AuthorityError):
            issue_authority(
                task_id="SCRUM-668", authority_id="a3", grantee="x",
                action="G4_MERGE", issued_by="",
            )


class TestSelfGrantRejection(unittest.TestCase):
    """C10: authority cannot self-grant."""

    def test_self_grant_rejected(self):
        with self.assertRaises(SelfGrantError):
            issue_authority(
                task_id="SCRUM-668", authority_id="a4", grantee="dwa-hermes",
                action="G2_EXECUTION", issued_by="dwa-hermes",
            )

    def test_distinct_issuer_ok(self):
        receipt = issue_authority(
            task_id="SCRUM-668", authority_id="a5", grantee="dwa-hermes",
            action="G2_EXECUTION", issued_by="analyzer-hitl",
        )
        self.assertEqual(receipt.issued_by, "analyzer-hitl")


class TestStaleAuthority(unittest.TestCase):
    """C10: stale/invalid authority fails closed."""

    def test_expired_authority_rejected(self):
        receipt = issue_authority(
            task_id="SCRUM-668", authority_id="a6", grantee="dwa-hermes",
            action="G3_REVIEW", issued_by="analyzer-hitl",
            expires_at="2000-01-01T00:00:00Z",
        )
        with self.assertRaises(StaleAuthorityError):
            validate_authority(receipt, now="2026-09-10T00:00:00Z")

    def test_valid_authority_ok(self):
        receipt = issue_authority(
            task_id="SCRUM-668", authority_id="a7", grantee="dwa-hermes",
            action="G3_REVIEW", issued_by="analyzer-hitl",
            expires_at="2030-01-01T00:00:00Z",
        )
        result = validate_authority(receipt, now="2026-09-10T00:00:00Z")
        self.assertTrue(result["valid"])

    def test_stale_rejection_deterministic(self):
        receipt = issue_authority(
            task_id="SCRUM-668", authority_id="a8", grantee="dwa-hermes",
            action="G3_REVIEW", issued_by="analyzer-hitl",
            expires_at="2000-01-01T00:00:00Z",
        )
        with self.assertRaises(StaleAuthorityError):
            validate_authority(receipt, now="2026-09-10T00:00:00Z")


class TestResolveAuthority(unittest.TestCase):
    """C6: every effect requires a resolved decision receipt."""

    def test_resolve_with_receipt_ok(self):
        receipt = issue_authority(
            task_id="SCRUM-668", authority_id="a9", grantee="dwa-hermes",
            action="G3_REVIEW", issued_by="analyzer-hitl",
            expires_at="2030-01-01T00:00:00Z",
        )
        result = resolve_authority(
            task_id="SCRUM-668", action="G3_REVIEW",
            receipts=[receipt], now="2026-09-10T00:00:00Z",
        )
        self.assertTrue(result["granted"])
        self.assertIn("decision_receipt", result)

    def test_resolve_without_receipt_fails_closed(self):
        result = resolve_authority(
            task_id="SCRUM-668", action="G3_REVIEW",
            receipts=[], now="2026-09-10T00:00:00Z",
        )
        self.assertFalse(result["granted"])
        self.assertEqual(result["decision"], "DENIED")

    def test_resolve_wrong_action_fails(self):
        receipt = issue_authority(
            task_id="SCRUM-668", authority_id="a10", grantee="dwa-hermes",
            action="G3_REVIEW", issued_by="analyzer-hitl",
            expires_at="2030-01-01T00:00:00Z",
        )
        result = resolve_authority(
            task_id="SCRUM-668", action="G5_DEPLOY",
            receipts=[receipt], now="2026-09-10T00:00:00Z",
        )
        self.assertFalse(result["granted"])


class TestModulesManifest(unittest.TestCase):
    """G-R4-05: cumulative universal_run_* module graph."""

    def test_manifest_binds_all_modules(self):
        manifest = build_modules_manifest(
            modules=[
                {"name": "universal_run_kernel", "layer": "kernel"},
                {"name": "universal_run_context", "layer": "context"},
                {"name": "universal_run_state", "layer": "state"},
                {"name": "universal_run_lifecycle", "layer": "lifecycle"},
                {"name": "universal_run_node", "layer": "node"},
                {"name": "universal_run_plan", "layer": "plan"},
                {"name": "universal_run_authority", "layer": "authority"},
                {"name": "universal_run_topology", "layer": "topology"},
            ]
        )
        self.assertEqual(len(manifest["modules"]), 8)
        self.assertTrue(manifest["manifest_digest"].startswith("sha256:"))

    def test_manifest_deterministic(self):
        modules = [
            {"name": "universal_run_kernel", "layer": "kernel"},
            {"name": "universal_run_authority", "layer": "authority"},
        ]
        a = build_modules_manifest(modules=modules)
        b = build_modules_manifest(modules=modules)
        self.assertEqual(a["manifest_digest"], b["manifest_digest"])

    def test_manifest_requires_unique_modules(self):
        with self.assertRaises(AuthorityError):
            build_modules_manifest(modules=[
                {"name": "universal_run_kernel", "layer": "kernel"},
                {"name": "universal_run_kernel", "layer": "kernel"},
            ])


if __name__ == "__main__":
    unittest.main()
