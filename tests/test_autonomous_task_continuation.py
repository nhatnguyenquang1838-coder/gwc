from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.node_architect.reconcile_autonomous_task_state import reconcile_autonomous_task_state
from tools.node_architect.run_task_continuation_loop import run_task_continuation_loop


def selection_input() -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "autonomous-task-selection-input",
        "run_id": "run-1",
        "active_lane": "SCRUM-270",
        "excluded_lanes": ["SCRUM-275", "SCRUM-276"],
        "manifest": {"allowed_tasks": [{"task_id": "SCRUM-274"}, {"task_id": "SCRUM-281"}]},
        "jira_tasks": [
            {"task_id": "SCRUM-274", "lane": "SCRUM-270", "status": "Ready", "priority": "High", "dependencies": []},
            {"task_id": "SCRUM-281", "lane": "SCRUM-270", "status": "Ready", "priority": "Medium", "dependencies": []},
        ],
        "dependency_evidence": {},
    }


def checkpoint_store_config(path: Path, *, head_sha: str = "b" * 40) -> dict:
    return {
        "path": str(path),
        "controller_task_id": "SCRUM-274",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "feature/scrum-274-autonomous-jira-continuation",
        "base_sha": "a" * 40,
        "head_sha": head_sha,
        "scope_hash": "sha256:" + "c" * 64,
        "graph_revision": "scrum-104-20260726",
    }


class FakeCheckpointInput:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeCheckpointAPI:
    CheckpointInput = FakeCheckpointInput

    @staticmethod
    def load_store(path: Path) -> dict:
        if not path.exists():
            return {"revision": 0, "checkpoints": {}, "events": [], "store_digest": None}
        return json.loads(path.read_text())

    @staticmethod
    def replay_checkpoint(store: dict, task_id: str, run_id: str, node_id: str):
        return store.get("checkpoints", {}).get(f"{task_id}:{run_id}:{node_id}")

    @staticmethod
    def persist_to_file(path: Path, item: FakeCheckpointInput) -> dict:
        store = FakeCheckpointAPI.load_store(path)
        if item.expected_revision != int(store.get("revision", 0)):
            raise RuntimeError("CAS_MISMATCH")
        revision = int(store.get("revision", 0)) + 1
        record = {"state": item.state, "revision": revision}
        store["revision"] = revision
        store.setdefault("checkpoints", {})[f"{item.task_id}:{item.run_id}:{item.node_id}"] = record
        raw = json.dumps({"revision": revision, "checkpoints": store["checkpoints"]}, sort_keys=True, separators=(",", ":"))
        store["store_digest"] = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n")
        return store


class JiraReconciliationTests(unittest.TestCase):
    def base(self) -> dict:
        return {
            "task_id": "SCRUM-274",
            "dispatch_id": "dispatch-001",
            "current_status": "To Do",
            "intended_status": "In Progress",
            "canonical_execution_status": "G2_EXECUTION",
            "legal_transitions": [{"from": "To Do", "to": "In Progress"}],
        }

    def test_failed_projection_preserves_truth_and_requires_late_reconciliation(self) -> None:
        obs = {**self.base(), "write_result": "failed"}
        result = reconcile_autonomous_task_state(obs)
        self.assertEqual(result["reason_code"], "JIRA_WRITE_FAILED")
        self.assertTrue(result["late_reconciliation_required"])
        self.assertTrue(result["canonical_execution_truth_preserved"])
        self.assertFalse(result["authority_granted"])

    def test_failed_projection_is_durably_checkpointed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "jira-reconciliation.json"
            obs = {
                **self.base(),
                "run_id": "run-1",
                "write_result": "failed",
                "checkpoint_store": checkpoint_store_config(store_path),
            }
            with patch("tools.node_architect.reconcile_autonomous_task_state._checkpoint_api", return_value=FakeCheckpointAPI):
                result = reconcile_autonomous_task_state(obs)
            self.assertTrue(result["checkpoint_persisted"])
            persisted = FakeCheckpointAPI.load_store(store_path)
            record = FakeCheckpointAPI.replay_checkpoint(persisted, "SCRUM-274", "run-1", "autonomous-jira-reconciliation")
            self.assertEqual(record["state"]["reason_code"], "JIRA_WRITE_FAILED")
            self.assertEqual(record["state"]["projection_status"], "LATE_RECONCILIATION_REQUIRED")

    def test_success_requires_exact_readback(self) -> None:
        mismatch = reconcile_autonomous_task_state({**self.base(), "write_result": "success", "readback_status": "To Do"})
        self.assertEqual(mismatch["reason_code"], "JIRA_READBACK_MISMATCH")
        self.assertFalse(mismatch["synchronized"])
        ok = reconcile_autonomous_task_state({**self.base(), "write_result": "success", "readback_status": "In Progress"})
        self.assertEqual(ok["projection_status"], "SYNCHRONIZED")
        self.assertTrue(ok["synchronized"])

    def test_illegal_transition_is_blocked(self) -> None:
        obs = {**self.base(), "legal_transitions": [], "write_result": "not_attempted"}
        result = reconcile_autonomous_task_state(obs)
        self.assertEqual(result["projection_status"], "BLOCKED")
        self.assertEqual(result["reason_code"], "JIRA_TRANSITION_ILLEGAL")


class ContinuationLoopTests(unittest.TestCase):
    def test_first_dispatch_requests_exactly_one_serial_claim(self) -> None:
        result = run_task_continuation_loop({
            "run_id": "run-1",
            "dispatch_id": "dispatch-001",
            "selection_input": selection_input(),
            "stop_conditions": {},
        })
        self.assertEqual(result["outcome"], "CLAIM_ONE_TASK")
        self.assertTrue(result["claim_requested"])
        self.assertEqual(result["selected_task"], "SCRUM-274")
        self.assertEqual(result["checkpoint"]["active_task"], "SCRUM-274")
        self.assertFalse(result["parallel_execution_allowed"])

    def test_duplicate_dispatch_is_fenced(self) -> None:
        first = run_task_continuation_loop({
            "run_id": "run-1", "dispatch_id": "dispatch-001",
            "selection_input": selection_input(), "stop_conditions": {},
        })
        replay = run_task_continuation_loop({
            "run_id": "run-1", "dispatch_id": "dispatch-001",
            "checkpoint": first["checkpoint"], "selection_input": selection_input(),
            "stop_conditions": {},
        })
        self.assertEqual(replay["outcome"], "FENCED")
        self.assertEqual(replay["reason_code"], "DUPLICATE_DISPATCH_FENCED")
        self.assertFalse(replay["claim_requested"])

    def test_durable_restart_loads_checkpoint_and_fences_duplicate_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "continuation.json"
            config = checkpoint_store_config(store_path)
            with patch("tools.node_architect.run_task_continuation_loop._checkpoint_api", return_value=FakeCheckpointAPI):
                first = run_task_continuation_loop({
                    "run_id": "run-1", "dispatch_id": "dispatch-001",
                    "selection_input": selection_input(), "stop_conditions": {},
                    "checkpoint_store": config,
                })
                self.assertTrue(first["checkpoint_persisted"])
                resumed = run_task_continuation_loop({
                    "run_id": "run-1", "dispatch_id": "dispatch-001",
                    "selection_input": selection_input(), "stop_conditions": {},
                    "checkpoint_store": config,
                })
            self.assertEqual(resumed["outcome"], "FENCED")
            self.assertEqual(resumed["selected_task"], "SCRUM-274")
            self.assertTrue(resumed["checkpoint_persisted"])

    def test_resume_waits_without_exact_g5(self) -> None:
        cp = {
            "schema_version": "1.0", "run_id": "run-1", "revision": 3,
            "active_task": "SCRUM-274", "active_dispatch_id": "dispatch-old",
            "active_task_merge_sha": "a" * 40, "completed_tasks": [],
            "last_selection_digest": "sha256:" + "b" * 64,
        }
        result = run_task_continuation_loop({
            "run_id": "run-1", "dispatch_id": "dispatch-resume", "checkpoint": cp,
            "selection_input": selection_input(), "stop_conditions": {},
        })
        self.assertEqual(result["outcome"], "WAITING")
        self.assertEqual(result["reason_code"], "WAITING_FOR_EXACT_G5")
        self.assertFalse(result["claim_requested"])

    def test_merge_sha_readback_is_persisted_before_waiting_for_g5(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "continuation.json"
            config = checkpoint_store_config(store_path)
            with patch("tools.node_architect.run_task_continuation_loop._checkpoint_api", return_value=FakeCheckpointAPI):
                run_task_continuation_loop({
                    "run_id": "run-1", "dispatch_id": "dispatch-001",
                    "selection_input": selection_input(), "stop_conditions": {}, "checkpoint_store": config,
                })
                waiting = run_task_continuation_loop({
                    "run_id": "run-1", "dispatch_id": "dispatch-g5-wait",
                    "selection_input": selection_input(), "stop_conditions": {}, "checkpoint_store": config,
                    "active_task_merge_sha_readback": "d" * 40,
                })
            self.assertEqual(waiting["outcome"], "WAITING")
            self.assertEqual(waiting["checkpoint"]["active_task_merge_sha"], "d" * 40)

    def test_jira_projection_state_is_bound_into_checkpoint(self) -> None:
        result = run_task_continuation_loop({
            "run_id": "run-1", "dispatch_id": "dispatch-001",
            "selection_input": selection_input(), "stop_conditions": {},
            "jira_projection_state": {"task_id": "SCRUM-274", "status": "In Progress", "reconciliation": "SYNCHRONIZED"},
        })
        self.assertEqual(result["checkpoint"]["jira_projection_state"]["status"], "In Progress")

    def test_wrong_g5_task_or_sha_does_not_unlock_next_task(self) -> None:
        cp = {
            "schema_version": "1.0", "run_id": "run-1", "revision": 3,
            "active_task": "SCRUM-274", "active_dispatch_id": "dispatch-old",
            "active_task_merge_sha": "a" * 40, "completed_tasks": [],
            "last_selection_digest": None,
        }
        wrong = {"task_id": "SCRUM-274", "merge_sha": "c" * 40, "status": "PASS", "exact_sha_verified": True}
        result = run_task_continuation_loop({
            "run_id": "run-1", "dispatch_id": "dispatch-next", "checkpoint": cp,
            "previous_task_g5": wrong, "selection_input": selection_input(), "stop_conditions": {},
        })
        self.assertEqual(result["reason_code"], "WAITING_FOR_EXACT_G5")

    def test_exact_g5_allows_refresh_and_one_next_selection(self) -> None:
        cp = {
            "schema_version": "1.0", "run_id": "run-1", "revision": 3,
            "active_task": "SCRUM-274", "active_dispatch_id": "dispatch-old",
            "active_task_merge_sha": "a" * 40, "completed_tasks": [],
            "last_selection_digest": None,
        }
        fresh = selection_input()
        fresh["jira_tasks"][0]["status"] = "Done"
        g5 = {"task_id": "SCRUM-274", "merge_sha": "a" * 40, "status": "PASS", "exact_sha_verified": True}
        result = run_task_continuation_loop({
            "run_id": "run-1", "dispatch_id": "dispatch-next", "checkpoint": cp,
            "previous_task_g5": g5, "selection_input": fresh, "stop_conditions": {},
        })
        self.assertEqual(result["outcome"], "CLAIM_ONE_TASK")
        self.assertEqual(result["selected_task"], "SCRUM-281")
        self.assertIn("SCRUM-274", result["checkpoint"]["completed_tasks"])
        self.assertEqual(result["checkpoint"]["last_exact_g5"], g5)
        self.assertFalse(result["parallel_execution_allowed"])

    def test_stop_conditions_fail_closed(self) -> None:
        for field, expected in [
            ("policy_expired", "POLICY_EXPIRED"),
            ("graph_drift", "GRAPH_DRIFT"),
            ("task_scope_drift", "TASK_SCOPE_DRIFT"),
            ("terminal_blocker", "TERMINAL_BLOCKER"),
            ("repair_budget_exhausted", "REPAIR_BUDGET_EXHAUSTED"),
            ("human_authority_required", "HUMAN_AUTHORITY_REQUIRED"),
        ]:
            with self.subTest(field=field):
                result = run_task_continuation_loop({
                    "run_id": "run-1", "dispatch_id": f"dispatch-{field}",
                    "selection_input": selection_input(), "stop_conditions": {field: True},
                })
                self.assertEqual(result["outcome"], "STOPPED")
                self.assertEqual(result["reason_code"], expected)
                self.assertFalse(result["claim_requested"])

    def test_checkpoint_and_reconciliation_shapes_validate(self) -> None:
        schema = json.loads((ROOT / "schemas/node-architect/autonomous-task-selection.schema.json").read_text())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        result = run_task_continuation_loop({
            "run_id": "run-1", "dispatch_id": "dispatch-001",
            "selection_input": selection_input(), "stop_conditions": {},
        })
        recon = reconcile_autonomous_task_state({
            "task_id": "SCRUM-274", "dispatch_id": "dispatch-001",
            "current_status": "To Do", "intended_status": "In Progress",
            "canonical_execution_status": "G2_EXECUTION", "write_result": "failed",
            "legal_transitions": [{"from": "To Do", "to": "In Progress"}],
        })
        self.assertEqual(list(validator.iter_errors(result["checkpoint"])), [])
        self.assertEqual(list(validator.iter_errors(recon["checkpoint"])), [])


if __name__ == "__main__":
    unittest.main()
