#!/usr/bin/env python3
"""R4 certification tests: hierarchical RuntimePlan revisions, cursor, recovery,
retry/rerun/replan/restart and drift detection.

C4 (G1 RuntimePlan, TargetContract and topology are immutable/digest-bound) and
C9 (retry/rerun/replan/restart, cursor recovery, drift and unknown-effect safety)
per the C1-C15 matrix. Composes E1 kernel digest primitives and E3 topology
manifest-revision; reuses run-manifest-revision.schema.json shape.

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
from tools.node_architect.universal_run_plan import (
    CursorRecoveryError,
    DriftError,
    PlanRevision,
    RuntimePlan,
    advance_cursor,
    create_runtime_plan,
    create_plan_revision,
    detect_drift,
    recover_cursor,
    restart_run,
    validate_plan_digest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "node-architect" / "universal-run" / "run-manifest-revision.schema.json"
PROFILE = UNIVERSAL_PROFILE


def _schema_validator():
    try:
        from jsonschema import Draft7Validator
    except Exception as exc:  # pragma: no cover
        raise unittest.SkipTest(f"jsonschema unavailable: {exc}") from exc
    schema = json.loads(SCHEMA_PATH.read_text())
    return Draft7Validator(schema)


class TestC4RuntimePlanImmutability(unittest.TestCase):
    """C4: RuntimePlan + revisions are immutable/digest-bound."""

    def test_create_plan_with_revision_1(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1",
            node_allocations=["n1", "n2"],
        )
        self.assertIsInstance(plan, RuntimePlan)
        self.assertEqual(plan.revision, 1)
        self.assertIsNotNone(plan.digest)

    def test_plan_digest_deterministic(self):
        a = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        b = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        self.assertEqual(a.digest, b.digest)

    def test_revision_must_increase(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        with self.assertRaises(Exception):
            create_plan_revision(
                previous=plan, run_id="run-1", revision=1,
                target_contract_ref="target:contract:v1", node_allocations=["n1"],
            )

    def test_revision_successor_linked(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        rev2 = create_plan_revision(
            previous=plan, run_id="run-1", revision=2,
            target_contract_ref="target:contract:v2", node_allocations=["n1", "n2"],
        )
        self.assertEqual(rev2.revision, 2)
        self.assertEqual(rev2.previous_digest, plan.digest)

    def test_validate_plan_digest_ok(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        self.assertTrue(validate_plan_digest(plan))

    def test_validate_plan_digest_tamper_fails(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        plan_dict = plan.to_dict()
        plan_dict["target_contract_ref"] = "tampered"
        self.assertFalse(validate_plan_digest(PlanRevision.from_dict(plan_dict)))


class TestC4SchemaConformance(unittest.TestCase):
    """Revision record validates against run-manifest-revision schema."""

    def test_plan_revision_matches_schema(self):
        validator = _schema_validator()
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        rev2 = create_plan_revision(
            previous=plan, run_id="run-1", revision=2,
            target_contract_ref="target:contract:v2", node_allocations=["n1", "n2"],
        )
        # PlanRevision.to_manifest_record emits the manifest-revision shape.
        errors = list(validator.iter_errors(rev2.to_manifest_record()))
        self.assertEqual(errors, [])


class TestC9CursorRecovery(unittest.TestCase):
    """C9: cursor advance and recovery are monotonic, typed, fail-closed."""

    def test_advance_cursor_monotonic(self):
        result = advance_cursor(
            run_id="run-1", current_cursor=1, next_cursor=2,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["cursor"], 2)

    def test_advance_cursor_non_monotonic_rejected(self):
        with self.assertRaises(CursorRecoveryError):
            advance_cursor(
                run_id="run-1", current_cursor=2, next_cursor=1,
            )

    def test_recover_cursor_from_state(self):
        recovered = recover_cursor(
            run_id="run-1", saved_cursor=3,
            observed_cursor=None,
        )
        self.assertEqual(recovered["cursor"], 3)

    def test_recover_cursor_rejects_higher_than_saved(self):
        with self.assertRaises(CursorRecoveryError):
            recover_cursor(
                run_id="run-1", saved_cursor=2, observed_cursor=5,
            )

    def test_recover_cursor_unknown_effect_fails_closed(self):
        # No saved cursor + no observed cursor = unknown state -> fail-closed.
        with self.assertRaises(CursorRecoveryError):
            recover_cursor(
                run_id="run-1", saved_cursor=None, observed_cursor=None,
            )


class TestC9RetryRerunReplanRestart(unittest.TestCase):
    """C9: retry/rerun/replan/restart are typed control receipts, no rewrite."""

    def test_retry_uses_same_plan_digest(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        result = restart_run(
            run_id="run-1", mode="RETRY", plan_digest=plan.digest,
            restart_from_cursor=0,
        )
        self.assertEqual(result["mode"], "RETRY")
        self.assertEqual(result["plan_digest"], plan.digest)
        self.assertEqual(result["restart_from_cursor"], 0)
        self.assertEqual(result["effect"], "NO_REWRITE")

    def test_rerun_uses_same_plan_digest(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        result = restart_run(
            run_id="run-1", mode="RERUN", plan_digest=plan.digest,
            restart_from_cursor=1,
        )
        self.assertEqual(result["effect"], "NO_REWRITE")

    def test_replan_requires_new_revision(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        rev2 = create_plan_revision(
            previous=plan, run_id="run-1", revision=2,
            target_contract_ref="target:contract:v2", node_allocations=["n1"],
        )
        result = restart_run(
            run_id="run-1", mode="REPLAN", plan_digest=rev2.digest,
            restart_from_cursor=0,
        )
        self.assertEqual(result["mode"], "REPLAN")
        self.assertEqual(result["plan_digest"], rev2.digest)

    def test_restart_rejects_unknown_mode(self):
        with self.assertRaises(Exception):
            restart_run(
                run_id="run-1", mode="HACK", plan_digest="x",
                restart_from_cursor=0,
            )

    def test_restart_never_rewrites(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        for mode in ("RETRY", "RERUN", "REPLAN"):
            result = restart_run(
                run_id="run-1", mode=mode, plan_digest=plan.digest,
                restart_from_cursor=0,
            )
            self.assertEqual(result["effect"], "NO_REWRITE")


class TestC9DriftDetection(unittest.TestCase):
    """C9: drift and unknown-effect safety."""

    def test_no_drift(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        result = detect_drift(
            run_id="run-1",
            expected_plan_digest=plan.digest,
            observed_plan_digest=plan.digest,
        )
        self.assertTrue(result["no_drift"])
        self.assertEqual(result["drift_decision"], "NO_DRIFT")

    def test_drift_detected(self):
        plan_a = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        plan_b = create_runtime_plan(
            run_id="run-1", revision=2,
            target_contract_ref="target:contract:v2", node_allocations=["n2"],
        )
        result = detect_drift(
            run_id="run-1",
            expected_plan_digest=plan_a.digest,
            observed_plan_digest=plan_b.digest,
        )
        self.assertFalse(result["no_drift"])
        self.assertEqual(result["drift_decision"], "DRIFT")
        # Unknown-effect safety: drift raises a typed error when enforced.
        with self.assertRaises(DriftError):
            detect_drift(
                run_id="run-1",
                expected_plan_digest=plan_a.digest,
                observed_plan_digest=plan_b.digest,
                enforce=True,
            )

    def test_drift_digest_immutability_contract(self):
        # A plan's digest must not change across serialization round-trip.
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1", "n2"],
        )
        restored = PlanRevision.from_dict(plan.to_dict())
        self.assertEqual(restored.digest, plan.digest)


if __name__ == "__main__":
    unittest.main()


class HierarchicalPlanBindingTests(unittest.TestCase):
    """Notion design §9: hierarchical RuntimePlan — parent RuntimePlan references
    Child Run RuntimePlans; an immutable revision is frozen at G1 exit; material
    drift after G1 must produce a NEW immutable revision with provenance (no
    silent mutation)."""

    def test_plan_frozen_at_g1_exit_is_immutable(self):
        from tools.node_architect.universal_run_plan import freeze_plan_at_g1_exit as F

        p = create_runtime_plan(run_id="RUN-P", revision=1,
                                target_contract_ref="TC-1",
                                node_allocations=["A", "B"])
        r = F(plan=p, lifecycle_position="G1")
        self.assertEqual(r["frozen_at"], "G1_EXIT")
        self.assertTrue(r["immutable"])
        self.assertEqual(r["plan_digest"], p.digest)
        self.assertTrue(r["freeze_receipt"].startswith("sha256:"))

    def test_plan_mutation_after_g1_is_forbidden(self):
        from tools.node_architect.universal_run_plan import (
            PlanFrozenError,
            freeze_plan_at_g1_exit as F,
            assert_plan_mutation_allowed as A,
        )
        p = create_runtime_plan(run_id="RUN-P", revision=1,
                                target_contract_ref="TC-1", node_allocations=["A"])
        frozen = F(plan=p, lifecycle_position="G1")
        # allowed while still in G0/G1 (pre-freeze semantics)
        self.assertTrue(A(frozen=None, lifecycle_position="G0")["ok"])
        for pos in ("G2", "G3", "G4", "G5", "G6"):
            with self.assertRaises(PlanFrozenError):
                A(frozen=frozen, lifecycle_position=pos)

    def test_freeze_requires_revision_at_least_1_and_valid_digest(self):
        from tools.node_architect.universal_run_plan import (
            PlanFrozenError,
            freeze_plan_at_g1_exit as F,
        )
        p = create_runtime_plan(run_id="RUN-P", revision=1,
                                target_contract_ref="TC-1", node_allocations=["A"])
        bad = RuntimePlan(run_id=p.run_id, revision=p.revision,
                          target_contract_ref=p.target_contract_ref,
                          node_allocations=p.node_allocations,
                          previous_digest=p.previous_digest, digest="sha256:" + "0" * 64)
        with self.assertRaises(PlanFrozenError):
            F(plan=bad, lifecycle_position="G1")

    def test_parent_plan_propagates_digest_to_child_plan(self):
        from tools.node_architect.universal_run_plan import propagate_plan_digest_to_child as P

        parent = create_runtime_plan(run_id="RUN-P", revision=1,
                                     target_contract_ref="TC-1", node_allocations=["A", "B"])
        binding = P(parent_plan=parent, child_run_id="RUN-C1",
                    invoking_node_allocation_ref="RUN-P:A")
        self.assertEqual(binding["parent_plan_digest"], parent.digest)
        self.assertEqual(binding["parent_run_id"], "RUN-P")
        self.assertEqual(binding["child_run_id"], "RUN-C1")
        self.assertEqual(binding["invoking_node_allocation_ref"], "RUN-P:A")
        self.assertTrue(binding["binding_digest"].startswith("sha256:"))

    def test_child_plan_binds_parent_digest_and_validates(self):
        from tools.node_architect.universal_run_plan import (
            validate_child_plan_binding as VB,
            propagate_plan_digest_to_child as P,
        )
        parent = create_runtime_plan(run_id="RUN-P", revision=1,
                                     target_contract_ref="TC-1", node_allocations=["A"])
        binding = P(parent_plan=parent, child_run_id="RUN-C1",
                    invoking_node_allocation_ref="RUN-P:A")
        self.assertTrue(VB(parent_plan=parent, binding=binding)["ok"])
        # drift: parent digest no longer matches binding -> fail-closed
        drifted = create_plan_revision(previous=parent, run_id="RUN-P", revision=2,
                                       target_contract_ref="TC-1", node_allocations=["A", "C"])
        r = VB(parent_plan=drifted, binding=binding)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason_code"], "CHILD_PLAN_PARENT_DIGEST_DRIFT")

    def test_child_plan_revision_requires_parent_digest_provenance(self):
        from tools.node_architect.universal_run_plan import (
            create_child_plan_revision as C,
        )
        parent = create_runtime_plan(run_id="RUN-P", revision=1,
                                     target_contract_ref="TC-1", node_allocations=["A"])
        child = C(parent_plan=parent, child_run_id="RUN-C1",
                  revision=1, target_contract_ref="TC-1",
                  invoking_node_allocation_ref="RUN-P:A", node_allocations=["X"])
        self.assertEqual(child.parent_digest, parent.digest)
        self.assertEqual(child.run_id, "RUN-C1")
        self.assertTrue(child.digest.startswith("sha256:"))
        # provenance chain: child revision references the parent plan digest
        rec = child.to_dict()
        self.assertEqual(rec["parent_plan_digest"], parent.digest)
        self.assertEqual(rec["parent_run_id"], "RUN-P")

    def test_drift_after_g1_creates_new_revision_not_mutation(self):
        from tools.node_architect.universal_run_plan import (
            freeze_plan_at_g1_exit as F,
            replan_after_drift as R,
            PlanFrozenError,
        )
        p = create_runtime_plan(run_id="RUN-P", revision=1,
                                target_contract_ref="TC-1", node_allocations=["A"])
        frozen = F(plan=p, lifecycle_position="G1")
        new = R(frozen=frozen, target_contract_ref="TC-1", node_allocations=["A", "B"],
                drift_reason="MATERIAL_DRIFT")
        self.assertEqual(new.revision, 2)
        self.assertEqual(new.previous_digest, p.digest)
        self.assertNotEqual(new.digest, p.digest)
        # original frozen plan is untouched
        self.assertEqual(frozen["plan_digest"], p.digest)
        # replan without material drift is refused (no silent churn)
        with self.assertRaises(PlanFrozenError):
            R(frozen=frozen, target_contract_ref="TC-1", node_allocations=["A", "B"],
              drift_reason="COSMETIC")


class ReplanAuditLogTests(unittest.TestCase):
    """Hardening GAP 3: append-only immutable replan audit log."""

    def test_replan_audit_log_append(self):
        from tools.node_architect.universal_run_plan import (
            ReplanAuditLog,
            create_runtime_plan,
        )
        p = create_runtime_plan(run_id="RUN-P", revision=1, target_contract_ref="TC-1", node_allocations=["A"])
        log = ReplanAuditLog()
        entry = log.append(run_id="RUN-P", from_digest=p.digest, to_revision=2, drift_reason="MATERIAL_DRIFT")
        self.assertTrue(entry["digest"].startswith("sha256:"))
        self.assertEqual(len(log.entries()), 1)

    def test_replan_audit_log_immutable(self):
        from tools.node_architect.universal_run_plan import ReplanAuditLog
        log = ReplanAuditLog()
        e1 = log.append(run_id="RUN-P", from_digest="sha256:" + "a" * 64, to_revision=2, drift_reason="MATERIAL_DRIFT")
        e2 = log.append(run_id="RUN-P", from_digest="sha256:" + "b" * 64, to_revision=3, drift_reason="MATERIAL_DRIFT")
        # entries are immutable snapshots; appending does not mutate prior entries
        self.assertEqual(log.entries()[0]["digest"], e1["digest"])
        self.assertEqual(len(log.entries()), 2)

    def test_replan_audit_log_fail_closed_on_gap(self):
        from tools.node_architect.universal_run_plan import (
            ReplanAuditLog,
            ReplanAuditError,
        )
        log = ReplanAuditLog()
        log.append(run_id="RUN-P", from_digest="sha256:" + "a" * 64, to_revision=2, drift_reason="MATERIAL_DRIFT")
        # next entry must continue from revision 2; starting at 4 is a gap
        with self.assertRaises(ReplanAuditError):
            log.append(run_id="RUN-P", from_digest="sha256:" + "b" * 64, to_revision=4, drift_reason="MATERIAL_DRIFT")


class ReplanAuditWiringTests(unittest.TestCase):
    """Wiring GAP 3: replan_after_drift appends to ReplanAuditLog when provided."""

    def _frozen(self):
        from tools.node_architect.universal_run_plan import create_runtime_plan, freeze_plan_at_g1_exit
        p = create_runtime_plan(run_id="RUN-P", revision=1, target_contract_ref="TC-1", node_allocations=["A"])
        return freeze_plan_at_g1_exit(plan=p, lifecycle_position="G1")

    def test_replan_appends_audit_entry(self):
        from tools.node_architect.universal_run_plan import ReplanAuditLog, replan_after_drift
        log = ReplanAuditLog()
        new = replan_after_drift(frozen=self._frozen(), target_contract_ref="TC-1",
                                 node_allocations=["A", "B"], drift_reason="MATERIAL_DRIFT",
                                 audit_log=log)
        self.assertEqual(new.revision, 2)
        self.assertEqual(len(log.entries()), 1)
        self.assertEqual(log.entries()[0]["to_revision"], 2)
        self.assertEqual(log.entries()[0]["drift_reason"], "MATERIAL_DRIFT")

    def test_replan_without_audit_log_unchanged(self):
        from tools.node_architect.universal_run_plan import replan_after_drift
        new = replan_after_drift(frozen=self._frozen(), target_contract_ref="TC-1",
                                 node_allocations=["A", "B"], drift_reason="MATERIAL_DRIFT")
        self.assertEqual(new.revision, 2)
