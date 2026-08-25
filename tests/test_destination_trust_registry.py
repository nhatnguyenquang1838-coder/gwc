#!/usr/bin/env python3
"""SCRUM-533 destination-trust-registry validator tests.

Verifies validate_destination_trust_registry.py enforces the SCRUM-533 L2.1
fail-closed invariants:
* schema/artifact-type identity
* HTTPS-only receiver, redirect/private-IP denied, TLS required
* credential_ref is a reference (never an inline secret)
* deterministic destination_policy_digest
* duplicate destination_id detection
* declared_entry_count consistency
* empty registry (no destinations) is valid (registration = reviewed entry)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import node_architect.validate_destination_trust_registry as vreg  # noqa: E402


def _canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _entry(overrides: dict | None = None) -> dict:
    policy = {
        "destination_id": "audit-sink-staging-01",
        "destination_type": "webhook_http",
        "receiver_identity": {"url": "https://sink.example.com/audit", "subject_alt_name": "sink.example.com"},
        "auth": {"scheme": "hmac_sha256", "credential_ref": "vault://audit-sink", "credential_version": 2},
        "transport_policy": {"tls_required": True, "allow_redirect": False,
                             "allow_private_ip": False, "dns_pin": "sink.example.com",
                             "egress_allowlist": ["sink.example.com"]},
        "revocation": {"revoked_at": None, "revoke_reason": None},
    }
    entry = {
        "schema_version": "1.0",
        "artifact_type": "destination-trust-profile",
        **policy,
        "destination_policy_digest": None,
    }
    entry["destination_policy_digest"] = "sha256:" + hashlib.sha256(
        _canonical_json(vreg._policy_block(entry)).encode("utf-8")).hexdigest()
    if overrides:
        entry.update(overrides)
    return entry


def _registry(entries: list[dict] | None = None) -> dict:
    entries = entries if entries is not None else []
    return {
        "schema_version": "1.0.0",
        "artifact_type": "destination-trust-registry",
        "registry_id": "gwc-external-audit-destination-trust-registry",
        "revision": "scrum-533-test-r1",
        "declared_entry_count": len(entries),
        "provenance": "test",
        "entries": entries,
    }


class RegistryValidatorTest(unittest.TestCase):
    def test_empty_registry_valid(self):
        findings = vreg.validate_registry(_registry([]))
        self.assertEqual(findings, [])

    def test_valid_entry_passes(self):
        findings = vreg.validate_registry(_registry([_entry()]))
        self.assertEqual(findings, [])

    def test_https_required(self):
        bad = _entry({"receiver_identity": {"url": "http://sink.example.com/audit"}})
        findings = vreg.validate_registry(_registry([bad]))
        codes = {f["code"] for f in findings}
        self.assertIn("HTTPS_REQUIRED", codes)

    def test_redirect_denied(self):
        bad = _entry({"transport_policy": {"tls_required": True, "allow_redirect": True, "allow_private_ip": False}})
        findings = vreg.validate_registry(_registry([bad]))
        self.assertIn("REDIRECT_DENIED", {f["code"] for f in findings})

    def test_private_ip_denied(self):
        bad = _entry({"transport_policy": {"tls_required": True, "allow_redirect": False, "allow_private_ip": True}})
        findings = vreg.validate_registry(_registry([bad]))
        self.assertIn("PRIVATE_IP_DENIED", {f["code"] for f in findings})

    def test_inline_secret_rejected(self):
        bad = _entry({"auth": {"scheme": "bearer_token_ref", "credential_ref": "Bearer token=eyJhbGciOiJIUzI1NiJ9.secret.payload"}})
        findings = vreg.validate_registry(_registry([bad]))
        self.assertIn("INLINE_SECRET", {f["code"] for f in findings})

    def test_policy_digest_mismatch(self):
        bad = _entry({"destination_policy_digest": "sha256:" + "0" * 64})
        findings = vreg.validate_registry(_registry([bad]))
        self.assertIn("POLICY_DIGEST_MISMATCH", {f["code"] for f in findings})

    def test_duplicate_destination_id(self):
        entries = [_entry(), _entry()]
        findings = vreg.validate_registry(_registry(entries))
        self.assertIn("DUPLICATE_DESTINATION_ID", {f["code"] for f in findings})

    def test_declared_count_mismatch(self):
        reg = _registry([_entry()])
        reg["declared_entry_count"] = 2
        findings = vreg.validate_registry(reg)
        self.assertIn("DECLARED_COUNT_MISMATCH", {f["code"] for f in findings})


if __name__ == "__main__":
    unittest.main()
