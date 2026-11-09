"""Source-owned G2 continuation preparation regressions, never live authority."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from tools.node_architect.approval_command_validation import validate_approval_command

from tests import test_scrum844_g2_approval_preparation as bootstrap
from tools.node_architect.evidence_artifact_map import build_gate_evidence_artifact_map
from tools.node_architect.g2_approval_preparation import G2PreparationBlocked, prepare_g2_approval

CONTINUED_HEAD = "c" * 40


def continuation_input():
    inputs = bootstrap.make_input()
    inputs["scope_identity"] = bootstrap.GS.scope(
        head_sha=CONTINUED_HEAD,
        authorized_actions=["modify_approved_files"],
    )
    early = [entry for entry in bootstrap.GS.candidates()
             if entry["gate"] in ("G0_CONTEXT", "G1_ALIGNMENT")]
    inputs["evidence_map"] = build_gate_evidence_artifact_map(
        task_id=bootstrap.TASK, repository=bootstrap.REPO,
        base_sha=bootstrap.BASE, head_sha=CONTINUED_HEAD,
        evidence_candidates=early, policy_revision="gate-transition-map@1.0.1",
    )
    inputs["requested_action"] = "modify_approved_files"
    return inputs


def observation(inputs):
    """Transport observation fixture, not authentication or an effect grant."""
    return {
        "task_id": inputs["task_id"],
        "repository": inputs["repository"],
        "branch": inputs["scope_identity"]["working_branch"],
        "authority_base_sha": inputs["current_base_sha"],
        "head_sha": inputs["scope_identity"]["head_sha"],
        "observed_at": inputs["issued_at"],
    }


class G2ContinuationPreparationTests(unittest.TestCase):
    def test_valid_explicit_continuation_prepares_exact_head_without_authority(self):
        inputs = continuation_input()
        try:
            result = prepare_g2_approval(
                **inputs, working_branch_readback=observation(inputs)
            )
        except (TypeError, G2PreparationBlocked) as exc:
            self.fail(f"Valid explicit continuation cannot prepare a request: {exc}")
        self.assertEqual("AWAITING_HUMAN_APPROVAL", result["status"])
        request = result["approval_request"]
        self.assertEqual(bootstrap.BASE, request["bindings"]["base_sha"])
        self.assertEqual(CONTINUED_HEAD, request["bindings"]["head_sha"])
        self.assertNotEqual(request["bindings"]["base_sha"], request["bindings"]["head_sha"])
        self.assertEqual("AWAITING_APPROVAL", result["pending_g2_envelope"]["activation_state"])
        self.assertFalse(result["pending_g2_envelope"]["execution_started"])
        self.assertIsNone(result["pending_g2_envelope"]["approval_validation_ref"])
        for key in ("authority_granted", "execution_authority_granted", "write_authority_granted"):
            self.assertFalse(result[key])
        self.assertFalse(request["authority_granted"])

    def test_initial_bootstrap_still_needs_no_existing_branch_readback(self):
        result = prepare_g2_approval(**bootstrap.make_input())
        self.assertEqual(bootstrap.BASE, result["approval_request"]["bindings"]["head_sha"])
        self.assertEqual("AWAITING_APPROVAL", result["pending_g2_envelope"]["activation_state"])

    def test_missing_continuation_observation_does_not_relax_head_binding(self):
        with self.assertRaisesRegex(G2PreparationBlocked, "G2_PREP_SCOPE_BINDING_INVALID"):
            prepare_g2_approval(**continuation_input())

    def test_every_observation_field_is_required_and_unknown_fields_denied(self):
        inputs = continuation_input()
        good = observation(inputs)
        for field in good:
            with self.subTest(missing=field):
                bad = dict(good)
                del bad[field]
                with self.assertRaisesRegex(G2PreparationBlocked, "G2_PREP_SCOPE_BINDING_INVALID"):
                    prepare_g2_approval(**inputs, working_branch_readback=bad)
        for bad in (False, [], "VERIFIED", {}, {**good, "verified": True}):
            with self.subTest(shape=bad):
                with self.assertRaisesRegex(G2PreparationBlocked, "G2_PREP_SCOPE_BINDING_INVALID"):
                    prepare_g2_approval(**inputs, working_branch_readback=bad)

    def test_foreign_task_repository_branch_base_or_head_is_denied(self):
        inputs = continuation_input()
        for key, value in (
            ("task_id", "SCRUM-999999"), ("repository", "foreign/repo"),
            ("branch", "foreign-branch"), ("authority_base_sha", "d" * 40),
            ("head_sha", "d" * 40), ("head_sha", "c" * 39 + "g"),
        ):
            with self.subTest(field=key):
                bad = {**observation(inputs), key: value}
                with self.assertRaisesRegex(G2PreparationBlocked, "G2_PREP_SCOPE_BINDING_INVALID"):
                    prepare_g2_approval(**inputs, working_branch_readback=bad)

    def test_stale_future_naive_non_utc_or_malformed_observation_is_denied(self):
        inputs = continuation_input()
        for observed_at in (
            "2026-10-17T06:54:59Z", "2026-10-17T06:54:59.999999Z",
            "2026-10-17T07:00:00.000001Z", "2026-10-17T07:00:01Z",
            "2026-10-17T07:00:00", "2026-10-17T14:00:00+07:00",
            "2026-10-17", "2026-10-17X07:00:00Z", "20261017T070000Z",
            "2026-10-17T07:00:00,0Z", "2026-10-17T07:00:00.0000001Z",
            "invalid", "", None, False, 42, {}, [],
        ):
            with self.subTest(observed_at=observed_at):
                with self.assertRaisesRegex(G2PreparationBlocked, "G2_PREP_SCOPE_BINDING_INVALID"):
                    prepare_g2_approval(**inputs, working_branch_readback={
                        **observation(inputs), "observed_at": observed_at,
                    })

    def test_freshness_boundary_and_explicit_utc_offset_are_accepted(self):
        inputs = continuation_input()
        for observed_at in ("2026-10-17T06:55:00Z", "2026-10-17T07:00:00+00:00"):
            with self.subTest(observed_at=observed_at):
                result = prepare_g2_approval(**inputs, working_branch_readback={
                    **observation(inputs), "observed_at": observed_at,
                })
                self.assertEqual("AWAITING_HUMAN_APPROVAL", result["status"])

    def test_supplied_invalid_readback_is_not_ignored_for_initial_bootstrap(self):
        inputs = bootstrap.make_input()
        with self.assertRaisesRegex(G2PreparationBlocked, "G2_PREP_SCOPE_BINDING_INVALID"):
            prepare_g2_approval(**inputs, working_branch_readback={"verified": True})

    def test_scope_hash_integrity_and_evidence_map_binding_remain_enforced(self):
        for changed in ("scope_hash", "working_branch", "head_sha", "authorized_paths"):
            with self.subTest(changed=changed):
                inputs = continuation_input()
                scope = inputs["scope_identity"]
                if changed == "scope_hash":
                    scope[changed] = "sha256:" + "0" * 64
                elif changed == "head_sha":
                    scope[changed] = "d" * 40
                elif changed == "working_branch":
                    scope[changed] = "another-branch"
                else:
                    scope[changed] = ["tools/foreign.py"]
                # A mutually matching observation must not rescue a forged scope.
                with self.assertRaises(G2PreparationBlocked):
                    prepare_g2_approval(**inputs, working_branch_readback=observation(inputs))

    def test_continuation_cannot_bypass_real_risk_producers(self):
        for changed in ("digest", "producer", "policy"):
            with self.subTest(changed=changed):
                inputs = continuation_input()
                if changed == "digest":
                    inputs["risk_profile"]["decision_digest"] = "sha256:" + "0" * 64
                elif changed == "producer":
                    del inputs["risk_producers"]["protected_base_capture"]
                else:
                    inputs["risk_policy"]["policy_version"] = "forged"
                with self.assertRaises(G2PreparationBlocked):
                    prepare_g2_approval(**inputs, working_branch_readback=observation(inputs))

    def test_outputs_validate_against_unchanged_canonical_schemas(self):
        inputs = continuation_input()
        result = prepare_g2_approval(**inputs, working_branch_readback=observation(inputs))
        for filename, value in (
            ("gate-approval-request.schema.json", result["approval_request"]),
            ("g2-execution-envelope.schema.json", result["pending_g2_envelope"]),
        ):
            with self.subTest(schema=filename):
                schema = json.loads((bootstrap.ROOT / "schemas" / filename).read_text())
                errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
                self.assertEqual([], [e.message for e in errors])

    def test_inputs_are_unchanged_and_repeated_preparation_is_deterministic(self):
        inputs = continuation_input()
        readback = observation(inputs)
        before = copy.deepcopy((inputs, readback))
        first = prepare_g2_approval(**inputs, working_branch_readback=readback)
        second = prepare_g2_approval(**inputs, working_branch_readback=readback)
        self.assertEqual(before, (inputs, readback))
        self.assertEqual(first, second)

    def test_preparation_does_not_satisfy_native_execution_boundary(self):
        inputs = continuation_input()
        result = prepare_g2_approval(**inputs, working_branch_readback=observation(inputs))
        decision = bootstrap.check_authority_boundary(
            task_id=inputs["task_id"], repository=inputs["repository"],
            requested_action=inputs["requested_action"], gate_state_resolution=result["gate_state_resolution"],
            scope_identity={k: v for k, v in inputs["scope_identity"].items()
                            if k in bootstrap.SCOPE_IDENTITY_KEYS},
            gate_policy={"action_map": bootstrap.ACTION_TO_MINIMUM_GATE},
            risk_class="R2", production_scope_applicable=False, manual_g5_action=False,
            event_id_or_idempotency_key="continuation-native-boundary", envelope_expires_at=inputs["expires_at"],
            evaluated_at=inputs["issued_at"],
        )
        self.assertEqual("BLOCK", decision["decision"])
        for key in ("authority_granted", "execution_authority_granted", "write_authority_granted"):
            self.assertFalse(decision[key])

    def test_approval_validation_requires_the_exact_continued_head(self):
        inputs = continuation_input()
        result = prepare_g2_approval(**inputs, working_branch_readback=observation(inputs))
        req = result["approval_request"]
        readback = {
            "status": "AVAILABLE", "base_sha": inputs["current_base_sha"],
            "head_sha": CONTINUED_HEAD, "scope_hash": inputs["scope_identity"]["scope_hash"],
            "repository": inputs["repository"], "branch": inputs["scope_identity"]["working_branch"],
            "current_actor": inputs["actor_target"], "action": inputs["requested_action"],
            "risk_class": "R2", "authorized_actions": inputs["scope_identity"]["authorized_actions"],
        }
        good = validate_approval_command(
            approval_request=req, human_response=req["approval_command"], current_readback=readback,
            event_id_or_idempotency_key="continuation-approval-test", validated_at=inputs["issued_at"],
        )
        self.assertEqual("VALID", good["outcome"])
        for head in (bootstrap.BASE, "d" * 40):
            with self.subTest(drifted_head=head):
                bad = validate_approval_command(
                    approval_request=req, human_response=req["approval_command"],
                    current_readback={**readback, "head_sha": head},
                    event_id_or_idempotency_key="continuation-approval-drift-test", validated_at=inputs["issued_at"],
                )
                self.assertNotEqual("VALID", bad["outcome"])

    def test_real_cli_prepares_valid_input_and_rejects_missing_observation(self):
        inputs = continuation_input()
        inputs["working_branch_readback"] = observation(inputs)
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            path = Path(tmp) / "canonical-inputs.json"
            for valid in (True, False):
                with self.subTest(valid=valid):
                    payload = copy.deepcopy(inputs)
                    if not valid:
                        del payload["working_branch_readback"]
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    proc = subprocess.run(
                        [sys.executable, "-m", "tools.node_architect.g2_approval_preparation", "--input", str(path)],
                        cwd=bootstrap.ROOT, capture_output=True, text=True, check=False,
                        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    )
                    result = json.loads(proc.stdout)
                    self.assertEqual(0 if valid else 2, proc.returncode, proc.stderr)
                    self.assertEqual("AWAITING_HUMAN_APPROVAL" if valid else "BLOCKED", result["status"])
                    self.assertFalse(result["authority_granted"])


if __name__ == "__main__":
    unittest.main()
