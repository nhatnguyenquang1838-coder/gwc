#!/usr/bin/env python3
"""NA81 delivery tests for SCRUM-347 — sync_projection.projection-drift-detection.

Requirement → code → test evidence map for the current NA81 brief:

1. Classify NO_DRIFT, material drift, conflict, unavailable readback
2. Stale / out-of-order readback detection
3. Conflicting target state detection
4. Unavailable readback detection
5. Deterministic digest / replay with readback meta
6. No back-write authority
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "node_architect"))  # noqa: E402

from projection_drift_detection import (
    PROJECTION_NO_DRIFT,
    PROJECTION_MATERIAL_DRIFT,
    PROJECTION_READBACK_STALE,
    PROJECTION_READBACK_CONFLICT,
    PROJECTION_READBACK_UNAVAILABLE,
    detect_projection_drift,
)


def _valid_envelope(task_id="SCRUM-347", target="audit"):
    return {
        "artifact_type": "sync-projection-envelope",
        "task_id": task_id,
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": target,
        "source_authority_digest": "sha256:" + "0" * 64,
        "evidence_linkset_digest": "sha256:" + "0" * 64,
        "privacy_boundary_digest": "sha256:" + "0" * 64,
    }


def _ready_decision(artifact_type, digest="sha256:" + "0" * 64):
    return {
        "artifact_type": artifact_type,
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "decision_digest": digest,
    }


class TestN81Classifications(unittest.TestCase):
    """New NA81 classification surface."""

    def _base_kwargs(self):
        return dict(
            envelope=_valid_envelope(),
            source_authority_decision=_ready_decision("projection-source-authority-decision"),
            evidence_linkset=_ready_decision("projection-evidence-linkset"),
            privacy_boundary_decision=_ready_decision("projection-privacy-decision"),
            projection={"canonical_state": {"status": "ACTIVE"}},
            canonical_state={"status": "ACTIVE"},
        )

    # 1. NO_DRIFT ----------------------------------------------------------
    def test_no_drift_without_readback_meta(self):
        decision = detect_projection_drift(**self._base_kwargs())
        self.assertEqual(decision["outcome"], "READY")
        # Backward-compat: M4 callers expect the original code.
        self.assertEqual(decision["reason_code"], "PROJECTION_DRIFT_NONE")
        self.assertFalse(decision["drift_detected"])
        self.assertIsNone(decision["observed_at"])

    def test_no_drift_with_readback_meta(self):
        decision = detect_projection_drift(
            **self._base_kwargs(),
            readback_meta={"observed_at": "2026-08-12T09:00:00Z"},
        )
        self.assertEqual(decision["outcome"], "READY")
        # NA81 callers see the new explicit code.
        self.assertEqual(decision["reason_code"], PROJECTION_NO_DRIFT)
        self.assertEqual(decision["observed_at"], "2026-08-12T09:00:00Z")

    # 2. Material drift ----------------------------------------------------
    def test_material_drift(self):
        decision = detect_projection_drift(
            envelope=_valid_envelope(),
            source_authority_decision=_ready_decision("projection-source-authority-decision"),
            evidence_linkset=_ready_decision("projection-evidence-linkset"),
            privacy_boundary_decision=_ready_decision("projection-privacy-decision"),
            projection={"canonical_state": {"status": "DRIFTED"}},
            canonical_state={"status": "ACTIVE"},
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertEqual(decision["reason_code"], "PROJECTION_MATERIAL_DRIFT")
        self.assertTrue(decision["drift_detected"])
        self.assertIn("PROJECTION_MATERIAL_DRIFT", decision["reason_codes"])

    # 3. Stale / out-of-order readback --------------------------------------
    def test_stale_readback(self):
        decision = detect_projection_drift(
            **self._base_kwargs(),
            readback_meta={"stale": True, "observed_at": "2026-08-12T08:00:00Z"},
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertEqual(decision["reason_code"], PROJECTION_READBACK_STALE)
        self.assertIn(PROJECTION_READBACK_STALE, decision["reason_codes"])
        self.assertEqual(decision["observed_at"], "2026-08-12T08:00:00Z")

    def test_stale_readback_precedence_over_drift(self):
        """Stale readback must BLOCK even when drift would also be detected."""
        decision = detect_projection_drift(
            envelope=_valid_envelope(),
            source_authority_decision=_ready_decision("projection-source-authority-decision"),
            evidence_linkset=_ready_decision("projection-evidence-linkset"),
            privacy_boundary_decision=_ready_decision("projection-privacy-decision"),
            projection={"canonical_state": {"status": "DRIFTED"}},
            canonical_state={"status": "ACTIVE"},
            readback_meta={"stale": True},
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertEqual(decision["reason_code"], PROJECTION_READBACK_STALE)
        self.assertNotIn(PROJECTION_MATERIAL_DRIFT, decision["reason_codes"])

    # 4. Conflicting target state -------------------------------------------
    def test_conflicting_target_state(self):
        decision = detect_projection_drift(
            **self._base_kwargs(),
            readback_meta={"conflict": True, "observed_at": "2026-08-12T09:05:00Z"},
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertEqual(decision["reason_code"], PROJECTION_READBACK_CONFLICT)
        self.assertIn(PROJECTION_READBACK_CONFLICT, decision["reason_codes"])

    # 5. Unavailable readback -----------------------------------------------
    def test_unavailable_readback(self):
        decision = detect_projection_drift(
            **self._base_kwargs(),
            readback_meta={"unavailable": True, "observed_at": "2026-08-12T09:10:00Z"},
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertEqual(decision["reason_code"], PROJECTION_READBACK_UNAVAILABLE)
        self.assertIn(PROJECTION_READBACK_UNAVAILABLE, decision["reason_codes"])

    # 6. Deterministic digest / replay --------------------------------------
    def test_deterministic_digest_with_readback_meta(self):
        kw = self._base_kwargs()
        kw["readback_meta"] = {"stale": True, "observed_at": "2026-08-12T09:00:00Z"}
        d1 = detect_projection_drift(**kw)
        d2 = detect_projection_drift(**kw)
        self.assertEqual(d1["decision_digest"], d2["decision_digest"])
        # Digest must change when observed_at changes.
        kw["readback_meta"]["observed_at"] = "2026-08-12T10:00:00Z"
        d3 = detect_projection_drift(**kw)
        self.assertNotEqual(d1["decision_digest"], d3["decision_digest"])

    def test_replay_same_result(self):
        kw = dict(
            envelope=_valid_envelope(),
            source_authority_decision=_ready_decision("projection-source-authority-decision"),
            evidence_linkset=_ready_decision("projection-evidence-linkset"),
            privacy_boundary_decision=_ready_decision("projection-privacy-decision"),
            projection={"canonical_state": {"version": "1"}},
            canonical_state={"version": "1"},
        )
        d1 = detect_projection_drift(**kw)
        d2 = detect_projection_drift(**kw)
        self.assertEqual(d1["decision_digest"], d2["decision_digest"])
        self.assertEqual(d1["reason_codes"], d2["reason_codes"])

    # 7. No back-write authority -------------------------------------------
    def test_no_back_write_authority(self):
        decision = detect_projection_drift(**self._base_kwargs())
        self.assertTrue(decision["read_only_projection"])
        self.assertFalse(decision["write_authority_granted"])
        self.assertFalse(decision["approval_authority_granted"])
        self.assertFalse(decision["merge_authority_granted"])
        self.assertFalse(decision["deployment_authority_granted"])
        self.assertFalse(decision["production_authority_granted"])


if __name__ == "__main__":
    unittest.main()
