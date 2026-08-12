"""SCRUM-377 NA81 maturity tests for the rollout-progress-projection node.

Current-task requirement -> code -> test evidence map (exact SHA delivery).

Older M4 tests (test_sync_projection_m4_batch_*) cover the historical SCRUM-254
renderer only. These NA81 tests bind the CURRENT SCRUM-377 brief (#312): a
deterministic, non-authoritative rollout progress view derived from VERIFIED
canonical current-task completion + exact merge/G5 evidence only. UNKNOWN,
BLOCKED and PENDING stay explicit; unsafe Jira Done or historical
implementation must never count as completed (family invariants
ROLLOUT_PROGRESS_IS_NON_AUTHORITATIVE_PROJECTION,
ONLY_VERIFIED_CURRENT_TASK_DELIVERY_COUNTS_AS_COMPLETE,
SCALE_CONTROL_EVIDENCE_DOES_NOT_GRANT_SCALE_AUTHORITY).
"""
from __future__ import annotations

import hashlib
import unittest

from tools.node_architect.rollout_progress_projection import (
    decide_rollout_progress_projection,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


BASE_SHA = _sha("base")
HEAD_SHA = _sha("head")
EVIDENCE_REV = "sha256:" + _sha("evidence-rev-v1")
EXPECTED_REV = "sha256:" + _sha("evidence-rev-v1")


def _gate(gate: str, status: str, sha: str = None) -> dict:
    return {"gate": gate, "status": status, "evidence_sha": sha or _sha(gate)[:40]}


def _family(family: str, total: int, completed: int) -> dict:
    return {"family": family, "total_nodes": total, "completed_nodes": completed}


def _all_complete_families() -> list:
    # 9 families x 9 nodes = 81 canonical nodes, all complete.
    return [_family(f"F{i}", 9, 9) for i in range(1, 10)]


def _all_pass_gates() -> list:
    return [_gate(f"G{n}", "PASS") for n in range(1, 7)]


def _base(**over) -> dict:
    args = dict(
        task_id="SCRUM-377",
        repository="nhatnguyenquang1838-coder/gwc",
        branch="auto/SCRUM-377-na81-20260810",
        base_sha=BASE_SHA[:40],
        head_sha=HEAD_SHA[:40],
        evidence_revision=EVIDENCE_REV,
        expected_revision=EXPECTED_REV,
        family_progress=_all_complete_families(),
        gate_evidence=_all_pass_gates(),
        expected_total_families=9,
        expected_total_nodes=81,
        audit_ready_required=True,
    )
    args.update(over)
    return decide_rollout_progress_projection(**args)


class CleanProgressTests(unittest.TestCase):
    def test_all_complete_ready_for_audit_handoff(self):
        d = _base()
        self.assertEqual(d["projection_status"], "READY_FOR_AUDIT_HANDOFF")
        self.assertEqual(d["reason_code"], "ROLLOUT_READY_FOR_INDEPENDENT_AUDIT_HANDOFF")
        self.assertEqual(d["completed_nodes"], 81)
        self.assertEqual(d["observed_total_nodes"], 81)
        self.assertEqual(d["progress_percent"], 100.0)
        self.assertFalse(d["scale_authority_granted"])
        self.assertFalse(d["merge_authority_granted"])

    def test_pending_gates_show_in_progress(self):
        gates = _all_pass_gates() + [_gate("G7", "PENDING")]
        d = _base(gate_evidence=gates)
        self.assertEqual(d["projection_status"], "IN_PROGRESS")
        self.assertEqual(d["reason_code"], "ROLLOUT_GATES_PENDING")
        self.assertIn("G7", d["pending_gates"])

    def test_blocked_gates_show_blocked(self):
        gates = _all_pass_gates() + [_gate("G7", "BLOCKED")]
        d = _base(gate_evidence=gates)
        self.assertEqual(d["projection_status"], "BLOCKED")
        self.assertEqual(d["reason_code"], "BLOCKED_GATE_PRESENT")
        self.assertIn("G7", d["blocked_gates"])


class UnknownExplicitTests(unittest.TestCase):
    def test_unknown_gate_status_never_silently_counts(self):
        # An unverifiable/unknown gate must keep the projection BLOCKED,
        # never be inferred as progress.
        gates = _all_pass_gates() + [_gate("G7", "UNKNOWN")]
        d = _base(gate_evidence=gates)
        self.assertEqual(d["projection_status"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_GATE_EVIDENCE_INPUT")

    def test_unsafe_jira_done_does_not_inflate_progress(self):
        # The projection derives only from the canonical inventory; a node that
        # is "Done" in Jira but absent from verified completion evidence cannot
        # inflate progress. We prove determinism: fewer verified completed nodes
        # yields proportionally lower progress, independent of any external flag.
        families = [_family(f"F{i}", 9, 9) for i in range(1, 10)]
        families[0] = _family("F1", 9, 4)  # only 4 of 9 verified complete
        d = _base(family_progress=families)
        self.assertEqual(d["completed_nodes"], 4 + 8 * 9)
        self.assertEqual(d["progress_percent"], round((4 + 72) / 81 * 100, 2))
        self.assertNotEqual(d["projection_status"], "READY_FOR_AUDIT_HANDOFF")


class MissingG5Tests(unittest.TestCase):
    def test_missing_g5_evidence_blocks(self):
        # G5 is exact post-merge verification evidence. A gate entry without
        # valid evidence_sha (simulating missing G5) blocks the projection
        # rather than silently counting as progress.
        gates = _all_pass_gates() + [_gate("G5", "PASS", "not-a-valid-sha")]
        d = _base(gate_evidence=gates)
        self.assertEqual(d["projection_status"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_GATE_EVIDENCE_INPUT")
        self.assertNotEqual(d["projection_status"], "READY_FOR_AUDIT_HANDOFF")


class ChangedDenominatorTests(unittest.TestCase):
    def test_changed_denominator_blocks(self):
        families = [_family(f"F{i}", 9, 9) for i in range(1, 10)]
        families[0] = _family("F1", 8, 8)  # total 80, not 81
        d = _base(family_progress=families)
        self.assertEqual(d["projection_status"], "BLOCKED")
        self.assertEqual(d["reason_code"], "TOTAL_NODE_COUNT_MISMATCH")


class StaleProjectionTests(unittest.TestCase):
    def test_stale_evidence_revision_blocks(self):
        d = _base(expected_revision="sha256:" + _sha("evidence-rev-stale"))
        self.assertEqual(d["projection_status"], "BLOCKED")
        self.assertEqual(d["reason_code"], "EVIDENCE_REVISION_MISMATCH")


class DeterministicRevisionDigestTests(unittest.TestCase):
    def test_identical_inputs_yield_stable_digest(self):
        a = _base()
        b = _base()
        self.assertEqual(a["decision_digest"], b["decision_digest"])
        self.assertEqual(a["progress_percent"], b["progress_percent"])

    def test_different_inputs_yield_different_digest(self):
        a = _base()
        b = _base(gate_evidence=_all_pass_gates() + [_gate("G7", "PENDING")])
        self.assertNotEqual(a["decision_digest"], b["decision_digest"])

    def test_no_authority_granted_ever(self):
        for gates in (_all_pass_gates(), _all_pass_gates() + [_gate("G7", "BLOCKED")]):
            d = _base(gate_evidence=gates)
            self.assertFalse(d["scale_authority_granted"])
            self.assertFalse(d["deployment_authority_granted"])
            self.assertFalse(d["production_authority_granted"])
            self.assertTrue(d["read_only_projection"])


if __name__ == "__main__":
    unittest.main()
