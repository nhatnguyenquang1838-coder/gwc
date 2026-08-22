import copy
import unittest

from tools.validate_research_implementation_bridge import (
    compute_plan_scope_hash,
    compute_scope_hash,
    validate_human_approval,
    validate_implementation_plan,
    validate_implementation_validation,
)


BASE_SHA = "21f36a45495c6d14a67b9ee779db7d2e372a3623"
SNAPSHOT_SHA = "1111111111111111111111111111111111111111"


def valid_validation_record():
    record = {
        "schema_version": "1.0",
        "artifact_type": "implementation-validation",
        "validated_at": "2026-08-23T00:30:00+07:00",
        "research_parent": "SCRUM-500",
        "paired_github_issue": "https://github.com/nhatnguyenquang1838-coder/gwc/issues/500",
        "s1_snapshot_sha": SNAPSHOT_SHA,
        "current_main_sha": BASE_SHA,
        "four_lens_verdicts": {
            "L1_ARCHITECTURE_CORRECTNESS": "APPROVE",
            "L2_SECURITY_TRUST": "APPROVE",
            "L3_RELIABILITY_OPERABILITY": "APPROVE",
            "L4_GOVERNANCE_IMPLEMENTABILITY": "APPROVE",
        },
        "classification": "RESEARCH_VALIDATED",
        "material_drift": [],
        "assumptions_confirmed": ["Current main preserves the researched control boundary."],
        "assumptions_invalidated": [],
        "final_validated_recommendation": "Adopt the validated bounded design.",
        "amendments": [],
        "implementation_surfaces": ["core/node-architect/example.md"],
        "compatibility_migration": ["Preserve backward compatibility with existing nodes."],
        "test_strategy": ["Unit and contract tests on exact planning scope."],
        "rollback_requirements": ["Revert bounded implementation PR."],
        "observability_requirements": ["Persist exact validation receipt and bound SHA."],
        "unresolved_questions": [],
        "risks": ["Backward compatibility must be preserved."],
        "acceptance_criteria": ["All exact-scope validators pass."],
        "dependencies": [
            {
                "id": "SCRUM-499",
                "status": "DONE",
                "deliverable_evidence": True,
            }
        ],
    }
    record["human_review_scope_hash"] = compute_scope_hash(record)
    return record


def valid_plan():
    plan = {
        "schema_version": "1.0",
        "artifact_type": "implementation-plan",
        "research_parent": "SCRUM-500",
        "target_repository": "nhatnguyenquang1838-coder/gwc",
        "planning_base_sha": BASE_SHA,
        "objective": "Implement validated research.",
        "non_goals": ["No production deployment."],
        "requirement_to_change": [{"requirement": "R1", "changes": ["a.py"]}],
        "work_packages": [
            {"id": "WP1", "objective": "Contract", "depends_on": []},
            {"id": "WP2", "objective": "Implementation", "depends_on": ["WP1"]},
            {"id": "WP3", "objective": "Validation", "depends_on": ["WP2"]},
        ],
        "safe_parallelism": [],
        "migration_backward_compatibility": ["Preserve existing contract behavior."],
        "test_matrix": ["unit", "integration"],
        "observability": ["structured validation receipt"],
        "rollback": ["revert bounded PR"],
        "acceptance_criteria": ["All required tests pass."],
        "risks": ["Compatibility drift"],
        "pr_slicing": ["PR1 contract", "PR2 implementation"],
        "gate_path": ["G0", "G1", "G2", "G3", "G4", "G5"],
        "required_evidence_by_gate": {
            "G0": ["context"],
            "G1": ["decision"],
            "G2": ["execution scope"],
            "G3": ["exact-head review and CI"],
            "G4": ["exact Human merge approval"],
            "G5": ["merge-SHA readback"],
        },
        "ownership_executor_assumptions": ["TaskController controls; executor stays in G2 scope."],
        "grants_execution_authority": False,
        "state": "IMPLEMENTATION_PLAN_READY",
        "next_state": "AWAITING_G2_AUTHORITY",
    }
    plan["implementation_scope_hash"] = compute_plan_scope_hash(plan)
    return plan


class ImplementationValidationTests(unittest.TestCase):
    def test_validated_four_lens_record_passes(self):
        record = valid_validation_record()
        self.assertEqual(validate_implementation_validation(record, BASE_SHA), [])

    def test_non_approve_lens_cannot_enter_human_review(self):
        record = valid_validation_record()
        record["four_lens_verdicts"]["L2_SECURITY_TRUST"] = "NEEDS_CLARIFICATION"
        record["human_review_scope_hash"] = compute_scope_hash(record)
        issues = validate_implementation_validation(record, BASE_SHA)
        self.assertTrue(any("four lens" in issue.lower() for issue in issues))

    def test_current_main_drift_invalidates_validation(self):
        record = valid_validation_record()
        issues = validate_implementation_validation(record, "2" * 40)
        self.assertTrue(any("current main" in issue.lower() for issue in issues))

    def test_done_without_deliverable_evidence_is_unsafe(self):
        record = valid_validation_record()
        record["dependencies"][0]["deliverable_evidence"] = False
        record["human_review_scope_hash"] = compute_scope_hash(record)
        issues = validate_implementation_validation(record, BASE_SHA)
        self.assertTrue(any("unsafe dependency evidence" in issue.lower() for issue in issues))

    def test_scope_hash_is_deterministic_and_sensitive(self):
        first = valid_validation_record()
        reordered = copy.deepcopy(first)
        reordered["four_lens_verdicts"] = dict(reversed(list(reordered["four_lens_verdicts"].items())))
        self.assertEqual(compute_scope_hash(first), compute_scope_hash(reordered))

        changed = copy.deepcopy(first)
        changed["risks"].append("New material risk")
        self.assertNotEqual(compute_scope_hash(first), compute_scope_hash(changed))

    def test_operational_validation_fields_are_machine_required(self):
        record = valid_validation_record()
        del record["test_strategy"]
        issues = validate_implementation_validation(record, BASE_SHA)
        self.assertTrue(any("test_strategy" in issue for issue in issues))

    def test_extra_validation_fields_are_rejected_by_schema(self):
        record = valid_validation_record()
        record["uncontrolled_field"] = "not allowed"
        issues = validate_implementation_validation(record, BASE_SHA)
        self.assertTrue(any("additional properties" in issue.lower() for issue in issues))


class HumanApprovalTests(unittest.TestCase):
    def test_exact_approval_is_bound_to_run_and_hash(self):
        record = valid_validation_record()
        run_id = "SCRUM-500-20260823-R1"
        prefix = record["human_review_scope_hash"].split(":", 1)[1][:16]
        command = f"APPROVE RESEARCH_PLAN {run_id} {prefix}"
        self.assertEqual(
            validate_human_approval(
                command,
                expected_run_id=run_id,
                expected_scope_hash=record["human_review_scope_hash"],
            ),
            [],
        )

    def test_vague_and_mismatched_approvals_fail(self):
        record = valid_validation_record()
        run_id = "SCRUM-500-20260823-R1"
        for command in [
            "ok",
            "approve",
            "continue",
            f"APPROVE RESEARCH_PLAN {run_id} deadbeefdeadbeef",
            "APPROVE RESEARCH_PLAN SCRUM-999-20260823-R1 0123456789abcdef",
        ]:
            with self.subTest(command=command):
                self.assertTrue(
                    validate_human_approval(
                        command,
                        expected_run_id=run_id,
                        expected_scope_hash=record["human_review_scope_hash"],
                    )
                )


class ImplementationPlanTests(unittest.TestCase):
    def test_complete_plan_passes_and_does_not_grant_g2(self):
        plan = valid_plan()
        self.assertEqual(validate_implementation_plan(plan), [])

        plan["grants_execution_authority"] = True
        self.assertTrue(validate_implementation_plan(plan))

    def test_plan_scope_hash_is_deterministic_and_sensitive(self):
        plan = valid_plan()
        reordered = copy.deepcopy(plan)
        reordered["required_evidence_by_gate"] = dict(
            reversed(list(reordered["required_evidence_by_gate"].items()))
        )
        self.assertEqual(compute_plan_scope_hash(plan), compute_plan_scope_hash(reordered))

        changed = copy.deepcopy(plan)
        changed["risks"].append("new risk")
        self.assertNotEqual(compute_plan_scope_hash(plan), compute_plan_scope_hash(changed))

    def test_plan_requires_operational_and_ownership_contract(self):
        plan = valid_plan()
        del plan["ownership_executor_assumptions"]
        issues = validate_implementation_plan(plan)
        self.assertTrue(any("ownership_executor_assumptions" in issue for issue in issues))

    def test_unknown_parallel_work_package_fails(self):
        plan = valid_plan()
        plan["safe_parallelism"] = [
            {
                "group_id": "P1",
                "work_packages": ["WP1", "WP404"],
                "rationale": "independent files",
            }
        ]
        plan["implementation_scope_hash"] = compute_plan_scope_hash(plan)
        issues = validate_implementation_plan(plan)
        self.assertTrue(any("unknown work package" in issue.lower() for issue in issues))

    def test_dependency_related_work_packages_cannot_be_parallelized(self):
        plan = valid_plan()
        plan["safe_parallelism"] = [
            {
                "group_id": "P1",
                "work_packages": ["WP1", "WP3"],
                "rationale": "incorrectly claimed independent",
            }
        ]
        plan["implementation_scope_hash"] = compute_plan_scope_hash(plan)
        issues = validate_implementation_plan(plan)
        self.assertTrue(any("dependency-related" in issue.lower() for issue in issues))

    def test_gate_evidence_must_match_gate_path(self):
        plan = valid_plan()
        del plan["required_evidence_by_gate"]["G5"]
        plan["implementation_scope_hash"] = compute_plan_scope_hash(plan)
        issues = validate_implementation_plan(plan)
        self.assertTrue(any("required_evidence_by_gate missing" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
