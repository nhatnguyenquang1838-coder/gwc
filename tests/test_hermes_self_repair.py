"""Self-repair evidence mechanics: synthetic receipts are NEVER live Q0 proof."""

import copy
import difflib
import importlib
import json
import subprocess
import sys
import unittest
from hashlib import sha256
from pathlib import Path

from tests import test_hermes_workflow_runtime as runtime_fixture
from tools.node_architect.hermes_workflow_compiler import digest

ROOT = runtime_fixture.ROOT


class SyntheticRepairAdapter:
    evidence_mode = "SYNTHETIC"

    def __init__(self, directory, incident, binding):
        self.directory, self.incident, self.binding = Path(directory), incident, binding
        self.receipts = {}
        self.calls = []
        self.mutate = None
        self.worker = self.directory / "synthetic_worker.py"
        self.worker.write_text("def value():\n    return 1\n")
        self.instructions = self.directory / "synthetic_instructions.txt"
        self.instructions.write_text(
            "SYNTHETIC MECHANICS ONLY; return expected fixture value"
        )
        self.command = [
            sys.executable,
            "-c",
            (
                "import json,runpy,sys; fixture=json.load(open(sys.argv[1])); "
                'assert runpy.run_path(sys.argv[2])["value"]() == fixture["expected"]'
            ),
            incident["fixture_ref"],
            str(self.worker),
        ]

    def run_repair_node(self, node, evidence, key):
        self.calls.append(node)
        candidate = "b" * 40  # labelled synthetic identity; NOT a Git commit
        data = {
            "classify_failure": ("missing_evidence", {}),
            "recover_source": (
                "verified",
                {
                    "fixture_digest": self.incident["fixture_digest"],
                    "fixture_ref": self.incident["fixture_ref"],
                    "source_sha": self.binding["source_sha"],
                },
            ),
            "analyze_cause": ("ready", {"cause_ref": "synthetic:assertion"}),
            "plan_minimal_fix": (
                "within_existing_scope",
                {
                    "target": "tests/synthetic_worker.py",
                    "action": "modify_approved_files",
                    "scope_check": True,
                    "single_writer": self.binding["writer_id"],
                },
            ),
            "apply_fix": (
                "effect_recorded",
                {
                    "diff_ref": "synthetic:diff",
                    "scope_check": True,
                    "single_writer": self.binding["writer_id"],
                    "fixed_sha": candidate,
                },
            ),
            "commit_readback": (
                "verified",
                {
                    "additive_commit_sha": candidate,
                    "parent_sha": self.binding["source_sha"],
                    "remote_sha": candidate,
                    "exact_readback": True,
                    "additive": True,
                    "synthetic_identity": True,
                },
            ),
            "runtime_reload": (
                "reloaded",
                {
                    "runtime_process_session": "synthetic-loaded-session",
                    "loaded_sha": candidate,
                },
            ),
            "load_proof": (
                "identity_matches",
                {
                    "runtime_process_session": "synthetic-loaded-session",
                    "loaded_sha": candidate,
                    "profile_digest": self.binding["profile_digest"],
                    "module_and_instruction_digests": {
                        "modules": {"synthetic-worker": digest("synthetic fixed code")},
                        "instructions": {
                            "synthetic-instructions": digest("synthetic instructions")
                        },
                    },
                },
            ),
            "invalidate_derivatives": (
                "completed",
                {
                    "invalidated": ["contract", "plan"],
                    "regenerated": [
                        {
                            "artifact": item,
                            "loaded_sha": candidate,
                            "digest": digest(item + candidate),
                        }
                        for item in ["contract", "plan"]
                    ],
                },
            ),
            "replay_original": (
                "progress_beyond_original_failure",
                {
                    "original_fixture_digest": self.incident["fixture_digest"],
                    "readback_ref": "synthetic:replay",
                    "advanced_beyond_failure": True,
                    "loaded_sha": candidate,
                    "previous_failure_state": "synthetic-failed",
                    "first_state_beyond_failure": "synthetic-advanced",
                    "legal_progress": True,
                },
            ),
        }
        if node in ("capture_red", "focused_green", "broader_tests"):
            command = self.command
            run = subprocess.run(command, capture_output=True, text=True, check=False)
            proof = {
                "exact_test_command": command,
                "returncode": run.returncode,
                "output": run.stdout + run.stderr,
                "source_sha": self.binding["source_sha"],
                "fixture_digest": self.incident["fixture_digest"],
                "tested_sha": candidate,
                "failure_signature": "AssertionError" if run.returncode else None,
                "receipt_ref": "synthetic:subprocess:" + node,
            }
            route = "authentic_red" if node == "capture_red" else "pass"
        else:
            route, proof = data[node]
        if node == "apply_fix":
            old = self.worker.read_text()
            fixed = "def value():\n    return 2\n"
            self.worker.write_text(fixed)
            diff_path = self.directory / "synthetic_fix.diff"
            diff_path.write_text(
                "".join(
                    difflib.unified_diff(
                        old.splitlines(True),
                        fixed.splitlines(True),
                        fromfile="synthetic_worker.py",
                        tofile="synthetic_worker.py",
                    )
                )
            )
            proof["diff_ref"] = str(diff_path)
        if node == "load_proof":
            proof["module_and_instruction_digests"] = {
                "modules": {
                    str(self.worker): "sha256:"
                    + sha256(self.worker.read_bytes()).hexdigest()
                },
                "instructions": {
                    str(self.instructions): "sha256:"
                    + sha256(self.instructions.read_bytes()).hexdigest()
                },
            }
        if node == "replay_original":
            run = subprocess.run(
                self.command, capture_output=True, text=True, check=False
            )
            replay_path = self.directory / "synthetic_replay.json"
            replay_path.write_text(
                json.dumps(
                    {"returncode": run.returncode, "output": run.stdout + run.stderr}
                )
            )
            proof.update(
                returncode=run.returncode,
                readback_ref=str(replay_path),
                advanced_beyond_failure=run.returncode == 0,
            )
        receipt = {
            "key": key,
            "node": node,
            "route": route,
            "evidence": proof,
            "exact_readback": True,
            "receipt_ref": "synthetic:repair:" + node,
            "evidence_mode": "SYNTHETIC",
            "binding_digest": digest(self.binding),
        }
        if self.mutate:
            receipt = self.mutate(node, receipt)
        self.receipts[key] = receipt
        return receipt

    def read_repair_node(self, key):
        return copy.deepcopy(self.receipts.get(key))


class SelfRepairTests(unittest.TestCase):
    runtime = runtime_fixture.RuntimeTests.runtime

    def setUp(self):
        runtime_fixture.RuntimeTests.setUp(self)
        self.definition = json.loads(
            (
                ROOT / "core/node-architect/hermes-loop-self-repair-workflow-r1.json"
            ).read_text()
        )
        fixture = Path(self.temp.name) / "synthetic-incident.json"
        fixture.write_text(
            json.dumps(
                {
                    "label": "SYNTHETIC NOT DWO",
                    "failure": "synthetic-failed",
                    "expected": 2,
                }
            )
        )
        self.incident = {
            "fixture_ref": str(fixture),
            "fixture_digest": digest(json.loads(fixture.read_text())),
            "evidence_mode": "SYNTHETIC",
            "previous_failure_state": "synthetic-failed",
            "source_sha": self.binding["source_sha"],
        }
        self.repair_binding = {
            **self.binding,
            "profile_digest": digest("synthetic-profile"),
        }
        self.adapter = SyntheticRepairAdapter(
            self.temp.name, self.incident, self.repair_binding
        )

    def repair(self):
        try:
            module = importlib.import_module("tools.node_architect.hermes_self_repair")
        except ModuleNotFoundError:
            self.fail("Missing evidence-validated repair mechanics")
        return module.SelfRepairMachine(
            self.runtime(),
            self.definition,
            self.incident,
            self.adapter,
            self.repair_binding,
        )

    def test_SR2_SR3_scoped_fix_and_exact_green_identity(self):
        state = self.repair().tick(max_nodes=8)
        self.assertEqual(state["next"], "commit_readback")
        self.assertEqual(state["status"], "ENGINE_FIX_IMPLEMENTED")
        self.assertEqual(state["evidence"]["focused_green"]["returncode"], 0)
        self.assertEqual(state["evidence"]["broader_tests"]["returncode"], 0)
        self.assertEqual(self.host.wakes, [])

    def test_SR2_wrong_writer_rejects_fix(self):
        self.adapter.mutate = lambda node, receipt: (
            {**receipt, "evidence": {**receipt["evidence"], "single_writer": "other"}}
            if node == "apply_fix"
            else receipt
        )
        with self.assertRaisesRegex(ValueError, "FIX_SCOPE_OR_WRITER"):
            self.repair().tick(max_nodes=8)
        self.assertEqual(self.repair()._load()["next"], "apply_fix")

    def test_SR3_green_wrong_sha_rejected(self):
        self.adapter.mutate = lambda node, receipt: (
            {**receipt, "evidence": {**receipt["evidence"], "tested_sha": "c" * 40}}
            if node == "focused_green"
            else receipt
        )
        with self.assertRaisesRegex(ValueError, "GREEN_IDENTITY"):
            self.repair().tick(max_nodes=8)
        self.assertEqual(self.repair()._load()["next"], "focused_green")

    def test_SR4_SR5_commit_and_loaded_identity_before_replay(self):
        state = self.repair().tick(max_nodes=11)
        self.assertEqual(state["next"], "invalidate_derivatives")
        self.assertEqual(state["status"], "ENGINE_FIX_LOADED")
        self.assertFalse(state["live_qualified"])
        self.assertEqual(self.host.wakes, [])

    def test_SR4_remote_readback_drift_rejected(self):
        self.adapter.mutate = lambda node, receipt: (
            {**receipt, "evidence": {**receipt["evidence"], "remote_sha": "c" * 40}}
            if node == "commit_readback"
            else receipt
        )
        with self.assertRaisesRegex(ValueError, "ADDITIVE_COMMIT"):
            self.repair().tick(max_nodes=13)
        self.assertNotIn("runtime_reload", self.adapter.calls)

    def test_SR5_changed_head_without_loaded_modules_rejected(self):
        self.adapter.mutate = lambda node, receipt: (
            {
                **receipt,
                "evidence": {
                    **receipt["evidence"],
                    "module_and_instruction_digests": {},
                },
            }
            if node == "load_proof"
            else receipt
        )
        with self.assertRaisesRegex(ValueError, "LOAD_PROOF"):
            self.repair().tick(max_nodes=13)
        self.assertNotIn("replay_original", self.adapter.calls)

    def test_SR6_SR7_full_13_node_synthetic_path_never_live_certifies(self):
        state = self.repair().tick(max_nodes=13)
        self.assertEqual(state["next"], "persist_progress")
        self.assertEqual(state["status"], "ENGINE_REPAIR_REPLAY_VERIFIED")
        self.assertEqual(len(self.adapter.calls), 13)
        self.assertEqual(
            set(self.adapter.calls), {n["id"] for n in self.definition["nodes"]}
        )
        self.assertFalse(state["live_qualified"])
        self.assertFalse(state["authority_granted"])
        self.assertEqual(self.host.wakes, [])

    def test_SR6_missing_derivative_regeneration_rejected(self):
        self.adapter.mutate = lambda node, receipt: (
            {**receipt, "evidence": {**receipt["evidence"], "regenerated": []}}
            if node == "invalidate_derivatives"
            else receipt
        )
        with self.assertRaisesRegex(ValueError, "DERIVATIVE"):
            self.repair().tick(max_nodes=13)
        self.assertNotIn("replay_original", self.adapter.calls)

    def test_SR7_wrong_original_fixture_replay_rejected(self):
        self.adapter.mutate = lambda node, receipt: (
            {
                **receipt,
                "evidence": {
                    **receipt["evidence"],
                    "original_fixture_digest": digest("other fixture"),
                },
            }
            if node == "replay_original"
            else receipt
        )
        with self.assertRaisesRegex(ValueError, "ORIGINAL_REPLAY"):
            self.repair().tick(max_nodes=13)

    def test_SR10_crash_reconciles_same_node_effect_once(self):
        original = self.adapter.run_repair_node

        def crash(node, evidence, key):
            receipt = original(node, evidence, key)
            if node == "apply_fix":
                raise RuntimeError("synthetic crash after fix")
            return receipt

        self.adapter.run_repair_node = crash
        with self.assertRaises(RuntimeError):
            self.repair().tick(max_nodes=13)
        self.adapter.run_repair_node = original
        state = self.repair().tick(max_nodes=13)
        self.assertEqual(state["next"], "persist_progress")
        self.assertEqual(self.adapter.calls.count("apply_fix"), 1)
        self.repair().tick(max_nodes=13)
        self.assertEqual(len(self.adapter.calls), 13)

    def test_SR11_SR12_real_incident_admission_not_inferred(self):
        self.incident["evidence_mode"] = "LIVE"
        with self.assertRaisesRegex(ValueError, "BASE_LIVE_QUALIFICATION_REQUIRED"):
            self.repair()
        self.assertEqual(self.adapter.calls, [])

    def test_synthetic_red_fix_green_replays_same_actual_worker(self):
        state = self.repair().tick(max_nodes=13)
        red = state["evidence"]["capture_red"]
        green = state["evidence"]["focused_green"]
        self.assertEqual(red["exact_test_command"], green["exact_test_command"])
        self.assertTrue(Path(state["evidence"]["apply_fix"]["diff_ref"]).is_file())
        rerun = subprocess.run(
            red["exact_test_command"], capture_output=True, text=True, check=False
        )
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        self.assertEqual(state["evidence"]["replay_original"]["returncode"], 0)

    def test_SR11_fixture_tamper_after_checkpoint_rejected(self):
        machine = self.repair()
        machine.tick(max_nodes=3)
        Path(self.incident["fixture_ref"]).write_text(
            '{"label":"SYNTHETIC CHANGED","expected":2}'
        )
        with self.assertRaisesRegex(ValueError, "INCIDENT_PROVENANCE"):
            machine.tick(max_nodes=13)
        self.assertNotIn("apply_fix", self.adapter.calls)

    def test_SR8_recoverable_green_loop_invalidates_stale_derivatives_no_wake(self):
        state = self.repair().tick(max_nodes=11)
        self.assertEqual(state["status"], "ENGINE_FIX_LOADED")

        def recoverable(node, receipt):
            if node == "replay_original":
                receipt["route"] = "recoverable_fail"
            return receipt

        self.adapter.mutate = recoverable
        state = self.repair().tick(max_nodes=2)
        self.assertEqual(state["next"], "analyze_cause")
        self.assertNotIn("load_proof", state["evidence"])
        self.assertEqual(state["status"], "ENGINE_MECHANICS")
        self.assertEqual(self.host.wakes, [])

    def test_local_module_proof_is_observed_code_not_git_head_claim(self):
        from tools.node_architect import hermes_self_repair

        self.assertTrue(
            hasattr(hermes_self_repair, "local_load_proof"),
            "Missing local module/process load proof",
        )
        proof = hermes_self_repair.local_load_proof(
            ROOT,
            ["tools.node_architect.hermes_self_repair"],
            ["AGENTS.md"],
            self.graph.plan,
        )
        self.assertEqual(proof["source_root"], str(ROOT))
        self.assertGreater(proof["process_id"], 0)
        self.assertTrue(proof["modules"][0]["loaded_code_digest"].startswith("sha256:"))
        self.assertTrue(proof["modules"][0]["loaded_functions_match_disk"])
        self.assertTrue(
            proof["instructions"][0]["content_digest"].startswith("sha256:")
        )
        self.assertFalse(proof["host_admitted"])
        self.assertEqual(proof["profile_digest"], self.graph.plan_digest)

    def test_local_load_proof_distinguishes_source_functions_and_generated_methods(
        self,
    ):
        from tools.node_architect.hermes_self_repair import local_load_proof

        proof = local_load_proof(
            ROOT,
            ["tools.node_architect.hermes_workflow_compiler"],
            ["AGENTS.md"],
            self.graph.plan,
        )
        self.assertTrue(proof["modules"][0]["loaded_functions_match_disk"])
        self.assertGreater(len(proof["modules"][0]["generated_functions"]), 0)
        self.assertIn("CompiledWorkflow.nodes", proof["modules"][0]["source_functions"])

    def test_SR1_source_recovery_authentic_synthetic_red(self):
        state = self.repair().tick(max_nodes=3)
        self.assertEqual(state["next"], "analyze_cause")
        self.assertEqual(
            self.adapter.calls, ["classify_failure", "recover_source", "capture_red"]
        )
        self.assertEqual(state["evidence"]["capture_red"]["returncode"], 1)
        self.assertIn("AssertionError", state["evidence"]["capture_red"]["output"])
        self.assertFalse(state["authority_granted"])
        self.assertFalse(state["live_qualified"])


if __name__ == "__main__":
    unittest.main()
