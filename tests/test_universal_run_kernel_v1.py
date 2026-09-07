from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest import mock

import jsonschema

from tools.node_architect.universal_run_kernel import (
    UniversalRunKernelError,
    derive_terminal_state,
    initial_run_state,
    make_successor_record,
    seal_immutable_record,
    transition_lifecycle,
    verify_record_digest,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "schemas" / "node-architect" / "universal-run"
PROFILE = {"id": "gwc.universal-run", "version": 1}


def _record() -> dict:
    return {
        "record_id": "REC-1",
        "schema_id": "gwc.test-record",
        "schema_version": 1,
        "run_id": "RUN-1",
        "created_at": "2026-09-07T22:50:00+07:00",
        "created_by": {"kind": "agent", "id": "ChatGPT"},
        "provenance": {"predecessor_refs": [], "source_refs": ["notion:contract-v1.1"]},
        "lifecycle_profile": PROFILE,
        "value": {"b": 2, "a": 1},
    }


class RecordEnvelopeTests(unittest.TestCase):
    def test_seal_record_uses_canonical_bytes_and_sha256(self):
        raw = _record()
        with mock.patch(
            "tools.node_architect.universal_run_kernel._canonical_json_bytes",
            return_value=b"canonical-record",
        ) as canonicalize:
            sealed = seal_immutable_record(raw)

        canonicalize.assert_called_once()
        self.assertEqual(sealed["content_digest"]["algorithm"], "sha256")
        self.assertEqual(sealed["content_digest"]["canonicalization"], "JCS")
        self.assertEqual(
            sealed["content_digest"]["value"],
            hashlib.sha256(b"canonical-record").hexdigest(),
        )
        self.assertNotIn("content_digest", raw)

    def test_verify_detects_tamper(self):
        sealed = seal_immutable_record(_record())
        self.assertTrue(verify_record_digest(sealed))
        tampered = copy.deepcopy(sealed)
        tampered["value"]["a"] = 99
        self.assertFalse(verify_record_digest(tampered))

    def test_successor_preserves_run_and_links_predecessor(self):
        sealed = seal_immutable_record(_record())
        successor = make_successor_record(
            sealed,
            record_id="REC-2",
            created_at="2026-09-07T23:00:00+07:00",
            created_by={"kind": "agent", "id": "ChatGPT"},
            changes={"value": {"a": 2}},
        )
        self.assertEqual(successor["run_id"], "RUN-1")
        self.assertIn("REC-1", successor["provenance"]["predecessor_refs"])
        self.assertTrue(verify_record_digest(successor))
        self.assertTrue(verify_record_digest(sealed))

    def test_successor_cannot_change_run_id(self):
        sealed = seal_immutable_record(_record())
        with self.assertRaises(UniversalRunKernelError) as ctx:
            make_successor_record(
                sealed,
                record_id="REC-2",
                created_at="2026-09-07T23:00:00+07:00",
                created_by={"kind": "agent", "id": "ChatGPT"},
                changes={"run_id": "RUN-OTHER"},
            )
        self.assertEqual(ctx.exception.code, "RUN_ID_IMMUTABLE")

    def test_unknown_lifecycle_version_fails_closed(self):
        raw = _record()
        raw["lifecycle_profile"] = {"id": "gwc.universal-run", "version": 2}
        with self.assertRaises(UniversalRunKernelError) as ctx:
            seal_immutable_record(raw)
        self.assertEqual(ctx.exception.code, "LIFECYCLE_PROFILE_UNSUPPORTED")

    def test_record_matches_schema(self):
        sealed = seal_immutable_record(_record())
        schema = json.loads((SCHEMA_ROOT / "record-envelope.schema.json").read_text())
        jsonschema.validate(sealed, schema)


class LifecycleTests(unittest.TestCase):
    def test_initial_state_starts_at_g0_only(self):
        state = initial_run_state(PROFILE)
        self.assertEqual(state["gate_states"]["G0"], "ACTIVE")
        self.assertTrue(all(state["gate_states"][g] == "NOT_STARTED" for g in ("G1", "G2", "G3", "G4", "G5", "G6")))
        self.assertEqual(state["terminal_state"], "OPEN")

    def test_advance_requires_passed_and_exact_next_gate(self):
        decision = transition_lifecycle(
            lifecycle_profile=PROFILE,
            current_gate="G1",
            current_state="PASSED",
            action="ADVANCE",
            target_gate="G2",
        )
        self.assertEqual(decision["next_gate"], "G2")
        self.assertEqual(decision["next_state"], "ACTIVE")

    def test_silent_gate_skip_is_rejected(self):
        with self.assertRaises(UniversalRunKernelError) as ctx:
            transition_lifecycle(
                lifecycle_profile=PROFILE,
                current_gate="G1",
                current_state="PASSED",
                action="ADVANCE",
                target_gate="G3",
            )
        self.assertEqual(ctx.exception.code, "LIFECYCLE_EDGE_UNDECLARED")

    def test_wait_and_continue_are_same_gate_edges(self):
        waiting = transition_lifecycle(
            lifecycle_profile=PROFILE,
            current_gate="G2",
            current_state="ACTIVE",
            action="WAIT",
        )
        self.assertEqual((waiting["next_gate"], waiting["next_state"]), ("G2", "WAITING"))
        resumed = transition_lifecycle(
            lifecycle_profile=PROFILE,
            current_gate="G2",
            current_state="WAITING",
            action="CONTINUE",
        )
        self.assertEqual((resumed["next_gate"], resumed["next_state"]), ("G2", "ACTIVE"))

    def test_replan_returns_to_g1_without_changing_run_identity(self):
        decision = transition_lifecycle(
            lifecycle_profile=PROFILE,
            current_gate="G4",
            current_state="BLOCKED",
            action="REPLAN",
        )
        self.assertEqual((decision["next_gate"], decision["next_state"]), ("G1", "ACTIVE"))
        self.assertEqual(decision["edge_kind"], "NON_FORWARD")

    def test_g4_no_transfer_requires_explicit_typed_outcome(self):
        decision = transition_lifecycle(
            lifecycle_profile=PROFILE,
            current_gate="G4",
            current_state="ACTIVE",
            action="COMPLETE",
            explicit_outcome="NO_TRANSFER_REQUIRED",
        )
        self.assertEqual(decision["next_gate"], "G4")
        self.assertEqual(decision["next_state"], "PASSED")
        self.assertEqual(decision["explicit_outcome"], "NO_TRANSFER_REQUIRED")

    def test_g4_no_transfer_without_typed_outcome_is_rejected(self):
        with self.assertRaises(UniversalRunKernelError) as ctx:
            transition_lifecycle(
                lifecycle_profile=PROFILE,
                current_gate="G4",
                current_state="ACTIVE",
                action="COMPLETE",
            )
        self.assertEqual(ctx.exception.code, "G4_OUTCOME_REQUIRED")

    def test_accepted_terminal_requires_g6_pass_and_handoff(self):
        states = {g: "PASSED" for g in ("G0", "G1", "G2", "G3", "G4", "G5", "G6")}
        with self.assertRaises(UniversalRunKernelError) as ctx:
            derive_terminal_state(states, closure_outcome="ACCEPTED", handoff_present=False)
        self.assertEqual(ctx.exception.code, "HANDOFF_REQUIRED")
        self.assertEqual(
            derive_terminal_state(states, closure_outcome="ACCEPTED", handoff_present=True),
            "ACCEPTED",
        )

    def test_transition_matches_schema(self):
        decision = transition_lifecycle(
            lifecycle_profile=PROFILE,
            current_gate="G0",
            current_state="PASSED",
            action="ADVANCE",
            target_gate="G1",
        )
        schema = json.loads((SCHEMA_ROOT / "lifecycle-transition.schema.json").read_text())
        jsonschema.validate(decision, schema)


if __name__ == "__main__":
    unittest.main()
