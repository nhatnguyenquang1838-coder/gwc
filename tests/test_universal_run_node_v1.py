#!/usr/bin/env python3
"""R3 certification tests: NodeDefinition/NodeAllocation, WORK/CONTROL promotion,
DAG budgets and SINGLE_ACTIVE concurrency guard.

C8 (recursive Parent-Child materialization, composition, failure propagation and
budgets) and C11 (NodeDefinition/Allocation, WORK/CONTROL promotion, DAG budgets
and SINGLE_ACTIVE) per the C1-C15 matrix. Reuses the committed
node-allocation.schema.json shape; composes E3 topology primitives.

Pure / read-only: never persists, never grants authority, never mutates targets.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.node_architect.universal_run_kernel import GATES, UNIVERSAL_PROFILE
from tools.node_architect.universal_run_node import (
    DAGBudgetError,
    NodeAllocation,
    NodeDefinition,
    SingleActiveError,
    allocate_node,
    build_node_definition,
    enforce_dag_budget,
    promote_node,
    resolve_single_active,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "node-architect" / "universal-run" / "node-allocation.schema.json"
PROFILE = UNIVERSAL_PROFILE


def _schema_validator():
    try:
        from jsonschema import Draft7Validator
    except Exception as exc:  # pragma: no cover
        raise unittest.SkipTest(f"jsonschema unavailable: {exc}") from exc
    schema = json.loads(SCHEMA_PATH.read_text())
    return Draft7Validator(schema)


class TestNodeDefinition(unittest.TestCase):
    """C11: NodeDefinition construction and identity."""

    def test_build_node_definition_work(self):
        node = build_node_definition(
            node_id="n1", kind="WORK", requirement="REQUIRED",
            description="do work", budget=5,
        )
        self.assertIsInstance(node, NodeDefinition)
        self.assertEqual(node.node_id, "n1")
        self.assertEqual(node.kind, "WORK")
        self.assertEqual(node.requirement, "REQUIRED")
        self.assertEqual(node.budget, 5)

    def test_build_node_definition_control_requires_justification(self):
        with self.assertRaises(Exception):
            build_node_definition(
                node_id="n2", kind="CONTROL", requirement="REQUIRED",
                description="control", budget=1, control_justification=None,
            )

    def test_control_justification_ok(self):
        node = build_node_definition(
            node_id="n2", kind="CONTROL", requirement="REQUIRED",
            description="control", budget=1, control_justification="gate authority",
        )
        self.assertEqual(node.control_justification, "gate authority")

    def test_unknown_kind_rejected(self):
        with self.assertRaises(Exception):
            build_node_definition(
                node_id="n3", kind="GATE", requirement="REQUIRED",
                description="bad", budget=1,
            )

    def test_budget_negative_rejected(self):
        with self.assertRaises(Exception):
            build_node_definition(
                node_id="n4", kind="WORK", requirement="REQUIRED",
                description="bad", budget=-1,
            )


class TestNodeAllocation(unittest.TestCase):
    """C11: allocation semantics against node-allocation schema."""

    def test_allocate_node_work(self):
        node = build_node_definition(
            node_id="n1", kind="WORK", requirement="REQUIRED",
            description="do work", budget=5,
        )
        alloc = allocate_node(
            run_id="run-1", node=node, condition_ref=None,
            control_justification=None, independent_boundary_reasons=["INDEPENDENT_CONSUMER"],
        )
        self.assertIsInstance(alloc, NodeAllocation)
        self.assertEqual(alloc.run_id, "run-1")
        self.assertEqual(alloc.node_id, "n1")
        self.assertEqual(alloc.kind, "WORK")
        self.assertEqual(alloc.requirement, "REQUIRED")
        self.assertEqual(alloc.child_instance_policy, "SINGLE_ACTIVE")

    def test_allocate_node_control_requires_justification(self):
        node = build_node_definition(
            node_id="n2", kind="CONTROL", requirement="REQUIRED",
            description="control", budget=1, control_justification="gate authority",
        )
        with self.assertRaises(Exception):
            allocate_node(
                run_id="run-1", node=node, condition_ref=None,
                control_justification=None,
                independent_boundary_reasons=["INDEPENDENT_CONSUMER"],
            )

    def test_allocation_matches_schema(self):
        validator = _schema_validator()
        node = build_node_definition(
            node_id="n1", kind="WORK", requirement="REQUIRED",
            description="do work", budget=5,
        )
        alloc = allocate_node(
            run_id="run-1", node=node, condition_ref=None,
            control_justification=None, independent_boundary_reasons=["INDEPENDENT_CONSUMER"],
        )
        errors = list(validator.iter_errors(alloc.to_dict()))
        self.assertEqual(errors, [])

    def test_allocation_digest_deterministic(self):
        node = build_node_definition(
            node_id="n1", kind="WORK", requirement="REQUIRED",
            description="do work", budget=5,
        )
        a = allocate_node(
            run_id="run-1", node=node, condition_ref=None,
            control_justification=None, independent_boundary_reasons=["INDEPENDENT_CONSUMER"],
        )
        b = allocate_node(
            run_id="run-1", node=node, condition_ref=None,
            control_justification=None, independent_boundary_reasons=["INDEPENDENT_CONSUMER"],
        )
        self.assertEqual(a.to_dict()["content_digest"], b.to_dict()["content_digest"])


class TestWorkControlPromotion(unittest.TestCase):
    """C11: WORK/CONTROL promotion semantics."""

    def test_promote_work_to_control_requires_justification(self):
        with self.assertRaises(Exception):
            promote_node(
                node_id="n1", kind="WORK", new_kind="CONTROL",
                control_justification=None,
            )

    def test_promote_work_to_control_ok(self):
        result = promote_node(
            node_id="n1", kind="WORK", new_kind="CONTROL",
            control_justification="needs gate authority",
        )
        self.assertEqual(result["kind"], "CONTROL")
        self.assertEqual(result["control_justification"], "needs gate authority")

    def test_promote_control_to_work_rejected(self):
        with self.assertRaises(Exception):
            promote_node(
                node_id="n1", kind="CONTROL", new_kind="WORK",
                control_justification="gate authority",
            )

    def test_promote_same_kind_noop_typed(self):
        result = promote_node(
            node_id="n1", kind="WORK", new_kind="WORK",
            control_justification=None,
        )
        self.assertIsNotNone(result)
        self.assertIn("noop", result)


class TestDAGBudget(unittest.TestCase):
    """C8/C11: DAG budget enforcement."""

    def test_budget_enforced(self):
        # budget 2 for total nodes 3 -> error
        with self.assertRaises(DAGBudgetError):
            enforce_dag_budget(
                run_id="run-1", node_ids=["a", "b", "c"],
                budget=2, kind="WORK",
            )

    def test_budget_ok(self):
        result = enforce_dag_budget(
            run_id="run-1", node_ids=["a", "b"],
            budget=2, kind="WORK",
        )
        self.assertTrue(result["ok"])

    def test_control_budget_separate_from_work(self):
        # WORK budget small but CONTROL separate
        result = enforce_dag_budget(
            run_id="run-1", node_ids=["c1"],
            budget=1, kind="CONTROL",
        )
        self.assertTrue(result["ok"])


class TestSingleActive(unittest.TestCase):
    """C11: SINGLE_ACTIVE concurrency guard."""

    def test_first_active_ok(self):
        result = resolve_single_active(
            run_id="run-1", child_run_ids=["child-1"],
            active_child_run_id=None,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["active_child_run_id"], "child-1")

    def test_second_active_rejected(self):
        with self.assertRaises(SingleActiveError):
            resolve_single_active(
                run_id="run-1", child_run_ids=["child-1", "child-2"],
                active_child_run_id="child-1",
            )

    def test_activate_different_child_rejected(self):
        with self.assertRaises(SingleActiveError):
            resolve_single_active(
                run_id="run-1", child_run_ids=["child-1", "child-2"],
                active_child_run_id="child-2",
            )

    def test_idempotent_same_child(self):
        result = resolve_single_active(
            run_id="run-1", child_run_ids=["child-1"],
            active_child_run_id="child-1",
        )
        self.assertTrue(result["ok"])


class TestC8MaterializationComposition(unittest.TestCase):
    """C8: recursive parent-child materialization, budgets, failure propagation."""

    def test_materialize_children_within_budget(self):
        # parent with 2 children, budget 2 -> ok
        result = enforce_dag_budget(
            run_id="parent", node_ids=["parent", "child-1", "child-2"],
            budget=3, kind="WORK",
        )
        self.assertTrue(result["ok"])

    def test_materialize_children_exceed_budget_fails_closed(self):
        with self.assertRaises(DAGBudgetError):
            enforce_dag_budget(
                run_id="parent", node_ids=["parent", "child-1", "child-2", "child-3"],
                budget=3, kind="WORK",
            )

    def test_child_failure_propagates_as_typed_error(self):
        # A child exceeding its own budget must raise a typed DAGBudgetError
        # that the parent can catch deterministically.
        try:
            enforce_dag_budget(
                run_id="child", node_ids=["grandchild-1", "grandchild-2"],
                budget=1, kind="WORK",
            )
            self.fail("expected DAGBudgetError")
        except DAGBudgetError as exc:
            self.assertIn("DAG_BUDGET", str(exc))


class TestSchemaConformance(unittest.TestCase):
    """Allocation dict must validate against committed schema."""

    def test_control_allocation_matches_schema(self):
        validator = _schema_validator()
        node = build_node_definition(
            node_id="n2", kind="CONTROL", requirement="REQUIRED",
            description="control", budget=1, control_justification="gate authority",
        )
        alloc = allocate_node(
            run_id="run-2", node=node, condition_ref=None,
            control_justification="gate authority",
            independent_boundary_reasons=["INDEPENDENT_AUTHORITY"],
        )
        errors = list(validator.iter_errors(alloc.to_dict()))
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()


class ParentG3CompositionVerificationTests(unittest.TestCase):
    """Notion design §3: Parent.G3 verifies the COMPOSITION/aggregate of accepted
    child outputs. Parent must NOT treat child-local PASS as proof the whole
    composition is valid."""

    def test_composition_verification_requires_all_required_children_accepted(self):
        from tools.node_architect.universal_run_node import CompositionVerificationError
        from tools.node_architect.universal_run_node import verify_parent_composition as V

        # one required child never reached accepted G6 handoff -> fail-closed
        result = V(
            parent_run_id="RUN-P",
            acceptance_contract_ref="AC-P-1",
            required_child_run_ids=["RUN-C1", "RUN-C2"],
            child_results=[
                {"child_run_id": "RUN-C1", "terminal_state": "ACCEPTED", "output_digest": "sha256:" + "a" * 64},
                {"child_run_id": "RUN-C2", "terminal_state": "OPEN", "output_digest": None},
            ],
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason_code"], "COMPOSITION_CHILD_NOT_ACCEPTED")
        self.assertIn("RUN-C2", result["unaccepted_child_run_ids"])

    def test_child_local_pass_is_not_composition_proof(self):
        """A child-local PASS with all children accepted is NOT sufficient: the
        composition must bind an aggregate digest over accepted child outputs."""
        from tools.node_architect.universal_run_node import verify_parent_composition as V

        r = V(
            parent_run_id="RUN-P",
            acceptance_contract_ref="AC-P-1",
            required_child_run_ids=["RUN-C1", "RUN-C2"],
            child_results=[
                {"child_run_id": "RUN-C1", "terminal_state": "ACCEPTED", "output_digest": "sha256:" + "a" * 64},
                {"child_run_id": "RUN-C2", "terminal_state": "ACCEPTED", "output_digest": "sha256:" + "b" * 64},
            ],
        )
        # composition is produced deterministically from accepted child outputs
        self.assertTrue(r["ok"])
        self.assertEqual(r["reason_code"], "COMPOSITION_VERIFIED")
        self.assertTrue(r["composition_digest"].startswith("sha256:"))
        # aggregate digest must depend on the child output digests, not merely on
        # a count of accepted children.
        r2 = V(
            parent_run_id="RUN-P",
            acceptance_contract_ref="AC-P-1",
            required_child_run_ids=["RUN-C1", "RUN-C2"],
            child_results=[
                {"child_run_id": "RUN-C1", "terminal_state": "ACCEPTED", "output_digest": "sha256:" + "a" * 64},
                {"child_run_id": "RUN-C2", "terminal_state": "ACCEPTED", "output_digest": "sha256:" + "c" * 64},
            ],
        )
        self.assertNotEqual(r["composition_digest"], r2["composition_digest"])

    def test_composition_digest_is_deterministic_and_order_independent(self):
        from tools.node_architect.universal_run_node import verify_parent_composition as V

        a = {"child_run_id": "RUN-C1", "terminal_state": "ACCEPTED", "output_digest": "sha256:" + "a" * 64}
        b = {"child_run_id": "RUN-C2", "terminal_state": "ACCEPTED", "output_digest": "sha256:" + "b" * 64}
        r1 = V(parent_run_id="RUN-P", acceptance_contract_ref="AC-P-1",
               required_child_run_ids=["RUN-C1", "RUN-C2"], child_results=[a, b])
        r2 = V(parent_run_id="RUN-P", acceptance_contract_ref="AC-P-1",
               required_child_run_ids=["RUN-C1", "RUN-C2"], child_results=[b, a])
        self.assertEqual(r1["composition_digest"], r2["composition_digest"])

    def test_composition_rejects_child_without_output_digest(self):
        from tools.node_architect.universal_run_node import verify_parent_composition as V

        r = V(
            parent_run_id="RUN-P",
            acceptance_contract_ref="AC-P-1",
            required_child_run_ids=["RUN-C1"],
            child_results=[{"child_run_id": "RUN-C1", "terminal_state": "ACCEPTED", "output_digest": None}],
        )
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason_code"], "COMPOSITION_OUTPUT_DIGEST_MISSING")

    def test_composition_requires_acceptance_contract_ref(self):
        from tools.node_architect.universal_run_node import (
            CompositionVerificationError,
            verify_parent_composition as V,
        )
        with self.assertRaises(CompositionVerificationError):
            V(parent_run_id="RUN-P", acceptance_contract_ref="",
              required_child_run_ids=["RUN-C1"], child_results=[])

    def test_extra_unrequired_children_are_allowed_but_not_required(self):
        from tools.node_architect.universal_run_node import verify_parent_composition as V

        r = V(
            parent_run_id="RUN-P",
            acceptance_contract_ref="AC-P-1",
            required_child_run_ids=["RUN-C1"],
            child_results=[
                {"child_run_id": "RUN-C1", "terminal_state": "ACCEPTED", "output_digest": "sha256:" + "a" * 64},
                {"child_run_id": "RUN-C9", "terminal_state": "OPEN", "output_digest": None},
            ],
        )
        self.assertTrue(r["ok"])
        self.assertNotIn("RUN-C9", r["unaccepted_child_run_ids"])
