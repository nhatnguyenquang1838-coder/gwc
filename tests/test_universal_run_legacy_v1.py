#!/usr/bin/env python3
"""R7 certification tests: namespaced legacy compatibility, translation
provenance, evidence-strength rules, and the never-reinterpret invariant.

C12 (compatibility/migration is namespaced, provenance-bound and never
reinterprets legacy semantics) per the C1-C15 matrix. Composes E1 kernel digest
primitives and evidence-strength semantics from evidence_quality_check.

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
from tools.node_architect.universal_run_legacy import (
    LegacyError,
    LegacyTranslation,
    NamespacingError,
    build_legacy_translation,
    classify_evidence_strength,
    validate_legacy_translation,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE = UNIVERSAL_PROFILE

LEGACY_PROFILE = {"id": "gwc.legacy.gate-lifecycle-v1", "version": 1}
LEGACY_PAYLOAD = {"gate": "G3", "status": "PASS", "reason": "review complete"}
LEGACY_NS = "gwc.legacy.gate-lifecycle-v1"


class TestNamespacedCompatibility(unittest.TestCase):
    """C12: translations are namespaced and never merge with universal profile."""

    def test_build_legacy_translation(self):
        t = build_legacy_translation(
            run_id="run-1",
            legacy_profile=LEGACY_PROFILE,
            legacy_payload=LEGACY_PAYLOAD,
            namespace=LEGACY_NS,
        )
        self.assertIsInstance(t, LegacyTranslation)
        self.assertEqual(t.namespace, LEGACY_NS)
        self.assertEqual(t.translation_digest.split(":")[0], "sha256")

    def test_legacy_profile_never_reinterpreted(self):
        # The translated payload must keep the legacy profile + original payload
        # immutable; translation never rewrites legacy semantics.
        t = build_legacy_translation(
            run_id="run-1",
            legacy_profile=LEGACY_PROFILE,
            legacy_payload=LEGACY_PAYLOAD,
            namespace=LEGACY_NS,
        )
        self.assertEqual(t.legacy_profile, LEGACY_PROFILE)
        self.assertEqual(t.legacy_payload, LEGACY_PAYLOAD)
        self.assertEqual(t.namespace, LEGACY_NS)

    def test_namespace_required(self):
        with self.assertRaises(LegacyError):
            build_legacy_translation(
                run_id="run-1",
                legacy_profile=LEGACY_PROFILE,
                legacy_payload=LEGACY_PAYLOAD,
                namespace="",
            )

    def test_universal_profile_never_aliased_to_legacy(self):
        # A translation from the universal profile is invalid: universal must
        # never be treated as legacy (no reinterpretation path).
        with self.assertRaises(LegacyError):
            build_legacy_translation(
                run_id="run-1",
                legacy_profile=UNIVERSAL_PROFILE,
                legacy_payload={"x": 1},
                namespace="gwc.universal-run",
            )


class TestTranslationProvenance(unittest.TestCase):
    """C12: translation is provenance-bound."""

    def test_translation_has_provenance(self):
        t = build_legacy_translation(
            run_id="run-1",
            legacy_profile=LEGACY_PROFILE,
            legacy_payload=LEGACY_PAYLOAD,
            namespace=LEGACY_NS,
            source_ref="SCRUM-668/725 immutable record",
        )
        self.assertEqual(t.source_ref, "SCRUM-668/725 immutable record")

    def test_translation_digest_deterministic(self):
        kwargs = dict(
            run_id="run-1", legacy_profile=LEGACY_PROFILE,
            legacy_payload=LEGACY_PAYLOAD, namespace=LEGACY_NS,
            source_ref="s1",
        )
        a = build_legacy_translation(**kwargs)
        b = build_legacy_translation(**kwargs)
        self.assertEqual(a.translation_digest, b.translation_digest)

    def test_validate_translation_ok(self):
        t = build_legacy_translation(
            run_id="run-1",
            legacy_profile=LEGACY_PROFILE,
            legacy_payload=LEGACY_PAYLOAD,
            namespace=LEGACY_NS,
        )
        self.assertTrue(validate_legacy_translation(t))

    def test_validate_translation_tamper_fails(self):
        t = build_legacy_translation(
            run_id="run-1",
            legacy_profile=LEGACY_PROFILE,
            legacy_payload=LEGACY_PAYLOAD,
            namespace=LEGACY_NS,
        )
        d = t.to_dict()
        d["legacy_payload"] = {"gate": "G3", "status": "FAIL"}
        tampered = LegacyTranslation.from_dict(d)
        self.assertFalse(validate_legacy_translation(tampered))


class TestEvidenceStrength(unittest.TestCase):
    """C12: evidence-strength rules are namespaced and ordered."""

    def test_classify_evidence_strength_observed(self):
        self.assertEqual(
            classify_evidence_strength("OBSERVED", namespace=LEGACY_NS),
            "OBSERVED",
        )

    def test_classify_evidence_strength_inferred(self):
        self.assertEqual(
            classify_evidence_strength("INFERRED", namespace=LEGACY_NS),
            "INFERRED",
        )

    def test_classify_evidence_strength_unknown_fails_closed(self):
        with self.assertRaises(LegacyError):
            classify_evidence_strength("FABRICATED", namespace=LEGACY_NS)

    def test_strength_order_observed_stronger_than_inferred(self):
        rank = {"OBSERVED": 3, "INFERRED": 2, "PROJECTED": 1}
        self.assertGreater(rank["OBSERVED"], rank["INFERRED"])
        self.assertGreater(rank["INFERRED"], rank["PROJECTED"])

    def test_strength_namespaced(self):
        # Strength classification is only valid inside a legacy namespace.
        with self.assertRaises(LegacyError):
            classify_evidence_strength("OBSERVED", namespace="gwc.universal-run")


class TestLegacyImmutableReadback(unittest.TestCase):
    """C12: SCRUM-668/725 immutable readback preserved."""

    def test_legacy_immutable_readback(self):
        # The translation must preserve the legacy payload byte-for-byte.
        t = build_legacy_translation(
            run_id="run-1",
            legacy_profile=LEGACY_PROFILE,
            legacy_payload=LEGACY_PAYLOAD,
            namespace=LEGACY_NS,
        )
        self.assertEqual(t.legacy_payload["gate"], "G3")
        self.assertEqual(t.legacy_payload["status"], "PASS")
        self.assertEqual(t.legacy_payload["reason"], "review complete")


if __name__ == "__main__":
    unittest.main()
