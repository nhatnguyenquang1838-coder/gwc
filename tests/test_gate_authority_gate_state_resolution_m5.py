"""SCRUM-184 M5 tests for deterministic, replay-safe gate-state resolution."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
import yaml

from tools.node_architect.evidence_artifact_map import build_gate_evidence_artifact_map
from tools.node_architect.gate_state_resolution import GATE_ORDER, resolve_gate_state
from tools.node_architect.scope_hash_calculation import calculate_gate_scope_identity

ROOT = Path(__file__).parents[1]
BASE = "9a7fd18af8f1b9dac4f5bc2774f4e0f602216624"
HEAD = "9f031809e62ea7b20c9e2b08af6f4f922f74cfb3"
REPO = "nhatnguyenquang1838-coder/gwc"
TASK = "SCRUM-184"
BRANCH = "fastlane/scrum-184-gate-state-resolution-m5-20260804"

REQUIREMENTS = (
    ("G0_CONTEXT", "context-snapshot", f".gwc/tasks/{TASK}/g0/context-snapshot.yaml", "CANONICAL_GATE_EVIDENCE", True),
    ("G1_ALIGNMENT", "intake", f".gwc/tasks/{TASK}/g1/intake/g1-intake-brief.yaml", "CANONICAL_GATE_EVIDENCE", True),
    ("G1_ALIGNMENT", "preflight", f".gwc/tasks/{TASK}/g1/preflight/g1-preflight-report.yaml", "CANONICAL_GATE_EVIDENCE", True),
    ("G1_ALIGNMENT", "options", f".gwc/tasks/{TASK}/g1/brainstorming/g1-options.yaml", "CANONICAL_GATE_EVIDENCE", True),
    ("G1_ALIGNMENT", "decision", f".gwc/tasks/{TASK}/g1/decision/g1-decision-record.yaml", "CANONICAL_GATE_EVIDENCE", True),
    ("G2_EXECUTION", "execution-envelope", f".gwc/tasks/{TASK}/g2/execution-envelope.yaml", "CANONICAL_AUTHORITY", True),
    ("G3_PR", "delivery-record", f".gwc/tasks/{TASK}/g3/delivery-record.yaml", "DELIVERY_EVIDENCE", True),
    ("G4_MERGE", "merge-approval", f".gwc/tasks/{TASK}/g4/merge-approval.yaml", "CANONICAL_AUTHORITY", True),
)


def transition_map() -> dict[str, object]:
    return yaml.safe_load((ROOT / "core/task-lifecycle/gate-transition-map.yaml").read_text(encoding="utf-8"))


def scope_identity(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "task_id": TASK,
        "repository": REPO,
        "base_ref": "main",
        "base_sha": BASE,
        "working_branch": BRANCH,
        "head_sha": HEAD,
        "risk_class": "R2",
        "authorized_paths": [
            "schemas/gate-state-resolution.schema.json",
            "tests/test_gate_authority_gate_state_resolution_m5.py",
            "tools/node_architect/gate_state_resolution.py",
        ],
        "authorized_actions": ["modify_approved_files"],
        "excluded_actions": ["merge_approved_pr"],
        "additional_bindings": [{"key": "pr_number", "value": "211"}],
        "calculated_at": "2026-08-04T13:50:00Z",
    }
    kwargs.update(overrides)
    return calculate_gate_scope_identity(**kwargs)  # type: ignore[arg-type]


def _candidate(
    gate: str,
    role: str,
    target: str,
    classification: str,
    required: bool,
    **overrides: object,
) -> dict[str, object]:
    candidate: dict[str, object] = {
        "evidence_key": target,
        "gate": gate,
        "artifact_role": role,
        "artifact_type": role,
        "classification": classification,
        "required": required,
        "source_type": "repository_artifact",
        "target": target,
        "ref": target,
        "revision": BASE,
        "digest": "sha256:" + hashlib.sha256(target.encode("utf-8")).hexdigest(),
        "binding_status": "BOUND",
        "freshness_status": "FRESH",
        "materialization_status": "MATERIALIZED",
        "source_of_truth": True,
    }
    candidate.update(overrides)
    return candidate


def evidence_candidates(*, include_g6: bool = False) -> list[dict[str, object]]:
    candidates = [_candidate(*requirement) for requirement in REQUIREMENTS]
    candidates.append(_candidate(
        "G5_DEPLOY",
        "status-verification",
        "actions://g5-status-verify",
        "DELIVERY_EVIDENCE",
        False,
        source_type="github_actions",
        artifact_type="ci-status",
    ))
    if include_g6:
        target = f".gwc/tasks/{TASK}/g6/production-approval.yaml"
        candidates.append(_candidate(
            "G6_PRODUCTION_DATA",
            "production-approval",
            target,
            "CANONICAL_AUTHORITY",
            False,
        ))
    return candidates


def evidence_map(
    *,
    candidates: list[dict[str, object]] | None = None,
    repository: str = REPO,
    include_g6: bool = False,
) -> dict[str, object]:
    return build_gate_evidence_artifact_map(
        task_id=TASK,
        repository=repository,
        base_sha=BASE,
        evidence_candidates=candidates if candidates is not None else evidence_candidates(include_g6=include_g6),
        policy_revision="gate-transition-map@1.0.1",
        mapped_at="2026-08-04T13:50:00Z",
    )


def _recompute_map_digest(model: dict[str, object]) -> None:
    semantic = {
        "task_id": model["task_id"],
        "repository": model["repository"],
        "base_sha": model["base_sha"],
        "policy_revision": model["policy_revision"],
        "requirements": model["requirements"],
        "entries": sorted(
            model["entries"],  # type: ignore[arg-type]
            key=lambda entry: (str(entry.get("gate")), str(entry.get("evidence_key"))),
        ),
        "missing_required": model["missing_required"],
        "stale_required": model["stale_required"],
        "projection_only": model["projection_only"],
    }
    canonical = json.dumps(semantic, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    model["map_digest"] = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "task_id": TASK,
        "repository": REPO,
        "current_base_sha": BASE,
        "scope_identity": scope_identity(),
        "evidence_map": evidence_map(),
        "transition_map": transition_map(),
        "task_projection": None,
        "event_id_or_idempotency_key": "scrum-184-event-1",
        "prior_resolution": None,
        "observed_at": "2026-08-04T13:50:00Z",
    }
    kwargs.update(overrides)
    return resolve_gate_state(**kwargs)  # type: ignore[arg-type]


class GateStateResolutionTests(unittest.TestCase):
    def test_dependency_builders_produce_accepted_inputs(self):
        out = resolve()
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_RESOLVED")

    def test_complete_non_production_resolves_g6_not_applicable(self):
        out = resolve()
        self.assertEqual(out["current_gate"], "G6_PRODUCTION_DATA")
        self.assertEqual(out["gate_status"], "NOT_APPLICABLE")
        self.assertEqual(out["last_passed_gate"], "G5_DEPLOY")
        self.assertIsNone(out["next_gate"])
        self.assertIn("GATE_STATE_G6_NOT_APPLICABLE", out["reason_codes"])

    def test_schema_valid(self):
        schema = json.loads((ROOT / "schemas/gate-state-resolution.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(resolve())), [])

    def test_all_authority_flags_false(self):
        out = resolve()
        for flag in (
            "authority_granted", "write_authority_granted", "pr_authority_granted",
            "merge_authority_granted", "deployment_authority_granted", "production_authority_granted",
        ):
            self.assertIs(out[flag], False)

    def test_blocked_required_entry_field_fails_input_closed(self):
        model = evidence_map()
        target = f".gwc/tasks/{TASK}/g2/execution-envelope.yaml"
        for entry in model["entries"]:  # type: ignore[union-attr]
            if entry["target"] == target:
                entry["reason_codes"] = ["EVIDENCE_BINDING_MISMATCH"]
        _recompute_map_digest(model)
        out = resolve(evidence_map=model)
        self.assertEqual(out["current_gate"], "G2_EXECUTION")
        self.assertEqual(out["gate_status"], "FAILED")
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_GATE_FAILED")

    def test_blocked_map_outcome_is_input_invalid(self):
        model = evidence_map()
        model["outcome"] = "BLOCKED"
        model["reason_codes"] = ["EVIDENCE_REQUIRED_MISSING"]
        out = resolve(evidence_map=model)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_INPUT_INVALID")

    def test_map_missing_gate_requirement_is_input_invalid(self):
        model = evidence_map()
        model["requirements"] = [  # type: ignore[arg-type]
            requirement for requirement in model["requirements"]
            if requirement["gate"] != "G0_CONTEXT"
        ]
        out = resolve(evidence_map=model)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_INPUT_INVALID")

    def test_entry_missing_canonical_metadata_is_input_invalid(self):
        model = evidence_map()
        del model["entries"][0]["artifact_type"]  # type: ignore[index]
        _recompute_map_digest(model)
        out = resolve(evidence_map=model)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_INPUT_INVALID")

    def test_non_schema_scope_hash_on_evidence_map_is_input_invalid(self):
        model = evidence_map()
        model["scope_hash"] = scope_identity()["scope_hash"]
        out = resolve(evidence_map=model)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_INPUT_INVALID")

    def test_tampered_map_digest_is_input_invalid(self):
        model = evidence_map()
        model["map_digest"] = "sha256:" + "0" * 64
        out = resolve(evidence_map=model)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_INPUT_INVALID")

    def test_tampered_scope_hash_is_input_invalid(self):
        scope = scope_identity()
        scope["scope_hash"] = "sha256:" + "0" * 64
        out = resolve(scope_identity=scope)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_INPUT_INVALID")

    def test_unknown_scope_field_is_input_invalid(self):
        scope = scope_identity()
        scope["invented"] = True
        out = resolve(scope_identity=scope)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_INPUT_INVALID")

    def test_projection_mismatch_is_warning_only(self):
        out = resolve(task_projection={"task_id": TASK, "current_gate": "G2_EXECUTION", "status": "RUNNING"})
        self.assertEqual(out["gate_status"], "NOT_APPLICABLE")
        self.assertIn("GATE_STATE_PROJECTION_MISMATCH", out["reason_codes"])
        self.assertIn("CURRENT_GATE_MISMATCH", out["projection_warnings"])

    def test_unknown_projection_state_warns_from_transition_map(self):
        out = resolve(task_projection={"task_id": TASK, "state": "invented_state"})
        self.assertIn("PROJECTION_STATE_UNKNOWN", out["projection_warnings"])
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_RESOLVED")

    def test_cancelled_projection_not_terminal_authority(self):
        out = resolve(task_projection={"task_id": TASK, "state": "cancelled"})
        self.assertEqual(out["gate_status"], "NOT_APPLICABLE")
        self.assertIn("CANCELLED_PROJECTION_WITHOUT_CANONICAL_EVIDENCE", out["projection_warnings"])

    def test_read_only_scope_with_empty_paths_is_accepted(self):
        scope = scope_identity(
            working_branch=None,
            head_sha=None,
            authorized_paths=[],
            authorized_actions=["verify_post_merge_ci"],
            additional_bindings=[],
        )
        out = resolve(scope_identity=scope)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_RESOLVED")

    def test_g5_status_evidence_needs_no_deployment_authority(self):
        out = resolve()
        g5 = next(item for item in out["gate_evaluations"] if item["gate"] == "G5_DEPLOY")  # type: ignore[index]
        self.assertEqual(g5["status"], "PASS")
        self.assertFalse(out["deployment_authority_granted"])

    def test_production_scope_requires_and_passes_g6(self):
        scope = scope_identity(
            working_branch=None,
            head_sha=None,
            authorized_paths=["production/operation-envelope.json"],
            authorized_actions=["production_data_write"],
            additional_bindings=[],
       )
        out = resolve(scope_identity=scope, evidence_map=evidence_map(include_g6=True))
        self.assertEqual(out["gate_status"], "PASS")
        self.assertEqual(out["last_passed_gate"], "G6_PRODUCTION_DATA")
        self.assertNotIn("GATE_STATE_G6_NOT_APPLICABLE", out["reason_codes"])
        self.assertFalse(out["production_authority_granted"])

    def test_production_scope_missing_g6_blocks(self):
        scope = scope_identity(
            working_branch=None,
            head_sha=None,
            authorized_paths=["production/config.json"],
            authorized_actions=["production_config_change"],
            additional_bindings=[],
        )
        out = resolve(scope_identity=scope, evidence_map=evidence_map())
        self.assertEqual(out["current_gate"], "G6_PRODUCTION_DATA")
        self.assertEqual(out["gate_status"], "BLOCKED")

    def test_unrelated_transition_map_is_input_invalid(self):
        unrelated = {
            "contract_version": "1.0.1",
            "authority": {"state_machine": "x", "discovery_tool": "y"},
            "rules": [
                {"outcome": "X", "from_state": "a", "transition": "B", "expected_state": "c"}
            ],
            "terminal_states": ["completed", "cancelled"],
            "verification": {
                "required": True,
                "failure_behavior": "fail_gate",
                "evidence": sorted({
                    "task_id", "from_state", "transition", "expected_state",
                    "observed_state", "event_id_or_idempotency_key",
                }),
                "readback_required": True,
            },
        }
        out = resolve(transition_map=unrelated)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_INPUT_INVALID")
        self.assertEqual(out["next_action_class"], "FIX_INPUT")

    def test_transition_map_missing_canonical_rule_is_input_invalid(self):
        model = transition_map()
        model["rules"] = model["rules"][:-1]
        out = resolve(transition_map=model)
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_INPUT_INVALID")

    def test_same_semantics_ignore_observed_at(self):
        a = resolve(observed_at="2026-08-04T13:50:00Z")
        b = resolve(observed_at="2026-08-05T13:50:00Z")
        self.assertEqual(a["resolution_digest"], b["resolution_digest"])

    def test_idempotent_replay(self):
        first = resolve()
        replay = resolve(prior_resolution=first, observed_at="2026-08-05T13:50:00Z")
        self.assertEqual(replay["replay_status"], "IDEMPOTENT_REPLAY")
        self.assertEqual(replay["resolution_digest"], first["resolution_digest"])

    def test_replay_conflict_precedes_binding(self):
        first = resolve()
        candidates = evidence_candidates()
        candidates[0]["freshness_status"] = "STALE"
        out = resolve(evidence_map=evidence_map(candidates=candidates), prior_resolution=first)
        self.assertEqual(out["replay_status"], "REPLAY_CONFLICT")
        self.assertEqual(out["primary_reason_code"], "GATE_STATE_REPLAY_CONFLICT")

    def test_new_event_key_is_first_seen(self):
        first = resolve()
        out = resolve(prior_resolution=first, event_id_or_idempotency_key="scrum-184-event-2")
        self.assertEqual(out["replay_status"], "FIRST_SEEN")

    def test_deterministic_ordering(self):
        model = evidence_map()
        model["entries"] = list(reversed(model["entries"]))  # type: ignore[arg-type]
        _recompute_map_digest(model)
        a = resolve(evidence_map=evidence_map())
        b = resolve(evidence_map=model)
        self.assertEqual(a["canonical_evidence_refs"], b["canonical_evidence_refs"])
        self.assertEqual(a["current_gate"], b["current_gate"])

    def test_gate_order_constant(self):
        self.assertEqual(GATE_ORDER[0], "G0_CONTEXT")
        self.assertEqual(GATE_ORDER[-1], "G6_PRODUCTION_DATA")


if __name__ == "__main__":
    unittest.main()
