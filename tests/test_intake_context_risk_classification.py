#!/usr/bin/env python3
"""Focused and negative tests for intake_context.risk-classification (SCRUM-302)."""
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TASK = "SCRUM-302"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "7f1d26e4fb0d4d09c49e9952994220a2f47a3824"
DIGEST = "sha256:" + "a" * 64


def load_module() -> Any:
    path = ROOT / "tools/node_architect/risk_classification.py"
    spec = importlib.util.spec_from_file_location("risk_classification", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = load_module()


def load_protected_base_producer() -> Any:
    path = ROOT / "tools/node_architect/protected_base_capture.py"
    spec = importlib.util.spec_from_file_location("protected_base_capture", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRODUCER = load_protected_base_producer()
SCHEMA = json.loads((ROOT / "schemas/risk-classification.schema.json").read_text(encoding="utf-8"))
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA)
PRODUCER_SCHEMA = json.loads((ROOT / "schemas/protected-base-capture.schema.json").read_text(encoding="utf-8"))
Draft202012Validator.check_schema(PRODUCER_SCHEMA)
PRODUCER_VALIDATOR = Draft202012Validator(PRODUCER_SCHEMA)


def upstreams(*, raw_text: str = "Implement schema contract", signals: list[str] | None = None) -> dict[str, dict[str, Any]]:
    return {
        "request_intake": {
            "artifact_type": "intake-request", "repository": REPO, "base_sha": BASE,
            "outcome": "ACCEPTED", "decision_digest": DIGEST,
            "request": {"raw_text": raw_text}, "risk_signals": signals or ["schema_change"],
        },
        "source_resolution": {
            "artifact_type": "source-resolution", "repository": REPO, "base_sha": BASE,
            "outcome": "ACCEPTED", "source_set_digest": DIGEST,
        },
        "repo_identity": {
            "artifact_type": "repo-identity", "repository": REPO, "base_sha": BASE,
            "outcome": "ACCEPTED", "identity_match": True, "decision_digest": DIGEST,
        },
        # Use the actual producer contract. It never emits a synthetic base_sha.
        "protected_base_snapshot": PRODUCER.render_protected_base_capture(
            task_id=TASK, repository=REPO, protected_base_sha=BASE,
            evidence_source="github:exact-base-readback", verified_sha=BASE,
            captured_at="2026-08-10T00:00:00Z",
        ),
    }


class RiskClassificationTests(unittest.TestCase):
    def classify(
        self,
        *,
        policy: dict[str, Any] | None = None,
        prior: dict[str, Any] | None = None,
        facts: dict[str, dict[str, Any]] | None = None,
        **changes: Any,
    ) -> dict[str, Any]:
        facts = copy.deepcopy(facts or upstreams())
        for key, value in changes.items():
            facts[key] = value
        return M.render_risk_classification(
            task_id=TASK, repository=REPO, base_sha=BASE,
            policy=policy or M.build_default_policy(),
            prior_classification=prior,
            classified_at="2026-08-10T00:00:00Z",
            **facts,
        )

    def assert_schema(self, artifact: dict[str, Any]) -> None:
        errors = sorted(VALIDATOR.iter_errors(artifact), key=lambda error: list(error.path))
        self.assertEqual([], [error.message for error in errors], msg=json.dumps(artifact, indent=2))
        for field in M.AUTH_FIELDS:
            self.assertFalse(artifact[field], field)
        self.assertTrue(artifact["read_only_projection"])

    def test_schema_change_is_deterministic_r2_and_authority_negative(self) -> None:
        first = self.classify()
        second = self.classify()
        self.assertEqual("ACCEPTED", first["outcome"])
        self.assertEqual("R2", first["risk_level"])
        self.assertEqual("G2_HUMAN_DIRECTION", first["required_gate"])
        self.assertIn("RISK_CLASSIFIED_R2", first["reason_codes"])
        self.assertEqual(first["decision_digest"], second["decision_digest"])
        self.assertEqual(first["source_bindings"]["base_sha"], BASE)
        self.assert_schema(first)

    def test_replay_digest_ignores_classification_timestamp(self) -> None:
        first = self.classify()
        facts = upstreams()
        replay = M.render_risk_classification(
            task_id=TASK, repository=REPO, base_sha=BASE,
            policy=M.build_default_policy(), classified_at="2099-01-01T00:00:00Z", **facts,
        )
        self.assertEqual(first["decision_digest"], replay["decision_digest"])
        self.assert_schema(replay)

    def test_high_risk_tightens_controls_without_granting_authority(self) -> None:
        artifact = self.classify(
            request_intake={
                **upstreams()["request_intake"],
                "request": {"raw_text": "change production credentials and deploy"},
                "risk_signals": ["production_scope", "secret_change", "release_deployment"],
            }
        )
        self.assertEqual(("ACCEPTED", "R3"), (artifact["outcome"], artifact["risk_level"]))
        self.assertIn("G6_PRODUCTION_DATA", artifact["additional_authority_gates"])
        self.assertIn("G5_DEPLOY", artifact["additional_authority_gates"])
        self.assertFalse(any(artifact[field] for field in M.AUTH_FIELDS))
        self.assert_schema(artifact)

    def test_unknown_signal_never_maps_to_low_risk(self) -> None:
        request = {**upstreams()["request_intake"], "risk_signals": ["telepathy"]}
        artifact = self.classify(request_intake=request)
        self.assertEqual("BLOCKED", artifact["outcome"])
        self.assertIsNone(artifact["risk_level"])
        self.assertEqual("RISK_UNCLASSIFIED", artifact["reason_code"])
        self.assertNotEqual("R0", artifact["risk_level"])
        self.assert_schema(artifact)

    def test_missing_upstream_fails_closed(self) -> None:
        facts = upstreams()
        facts.pop("source_resolution")
        artifact = M.render_risk_classification(
            task_id=TASK,
            repository=REPO,
            base_sha=BASE,
            request_intake=facts["request_intake"],
            source_resolution=None,
            repo_identity=facts["repo_identity"],
            protected_base_snapshot=facts["protected_base_snapshot"],
            policy=M.build_default_policy(),
            classified_at="2026-08-10T00:00:00Z",
        )
        self.assertEqual(("BLOCKED", "RISK_UNCLASSIFIED"), (artifact["outcome"], artifact["reason_code"]))
        self.assert_schema(artifact)

    def test_stale_policy_requires_recomputation(self) -> None:
        prior = self.classify()
        changed = copy.deepcopy(M.build_default_policy())
        changed["version"] = "2.0"
        changed["digest"] = M.compute_policy_digest(changed)
        artifact = self.classify(policy=changed, prior=prior)
        self.assertEqual(("BLOCKED", "RISK_SOURCE_STALE"), (artifact["outcome"], artifact["reason_code"]))
        self.assertEqual("REFRESH_SOURCE", artifact["remediation"]["route"])
        self.assert_schema(artifact)

    def test_policy_digest_mismatch_is_stale(self) -> None:
        policy = M.build_default_policy()
        policy["digest"] = DIGEST
        artifact = self.classify(policy=policy)
        self.assertEqual(("BLOCKED", "RISK_SOURCE_STALE"), (artifact["outcome"], artifact["reason_code"]))
        self.assert_schema(artifact)

    def test_declared_level_conflict_requires_human(self) -> None:
        request = {**upstreams()["request_intake"], "declared_risk_level": "R0"}
        artifact = self.classify(request_intake=request)
        self.assertEqual(("HUMAN_REQUIRED", "RISK_SCOPE_AMBIGUOUS"), (artifact["outcome"], artifact["reason_code"]))
        self.assert_schema(artifact)

    def test_protected_base_drift_is_stale(self) -> None:
        protected = {**upstreams()["protected_base_snapshot"], "drift_state": "DRIFTED"}
        artifact = self.classify(protected_base_snapshot=protected)
        self.assertEqual(("BLOCKED", "RISK_SOURCE_STALE"), (artifact["outcome"], artifact["reason_code"]))
        self.assert_schema(artifact)

    def test_real_producer_consumer_integration_no_fake_base_sha(self) -> None:
        protected = upstreams()["protected_base_snapshot"]
        self.assertNotIn("base_sha", protected)
        self.assertEqual([], [e.message for e in PRODUCER_VALIDATOR.iter_errors(protected)])
        self.assertEqual("ACCEPTED", protected["outcome"])
        result = self.classify()
        self.assertEqual(("ACCEPTED", "R2"), (result["outcome"], result["risk_level"]))
        self.assertEqual("G2_HUMAN_DIRECTION", result["required_gate"])
        self.assertEqual(protected["decision_digest"], result["source_bindings"]["protected_base_capture"])
        self.assert_schema(result)

    def test_producer_protected_base_mismatch_stays_stale(self) -> None:
        other = "b" * 40
        facts = upstreams()
        facts["protected_base_snapshot"] = PRODUCER.render_protected_base_capture(
            task_id=TASK, repository=REPO, protected_base_sha=other,
            evidence_source="github:other-base-readback", verified_sha=other,
        )
        self.assertEqual("ACCEPTED", facts["protected_base_snapshot"]["outcome"])
        result = self.classify(facts=facts)
        self.assertEqual(("BLOCKED", "RISK_SOURCE_STALE"), (result["outcome"], result["reason_code"]))
        self.assert_schema(result)

    def test_missing_canonical_protected_base_sha_fails_closed(self) -> None:
        facts = upstreams()
        facts["protected_base_snapshot"].pop("protected_base_sha")
        result = self.classify(facts=facts)
        self.assertEqual(("BLOCKED", "RISK_SOURCE_STALE"), (result["outcome"], result["reason_code"]))
        self.assert_schema(result)

    def test_real_producer_readback_mismatch_fails_closed(self) -> None:
        facts = upstreams()
        facts["protected_base_snapshot"] = PRODUCER.render_protected_base_capture(
            task_id=TASK, repository=REPO, protected_base_sha=BASE,
            evidence_source="github:readback", verified_sha="b" * 40,
        )
        self.assertNotEqual("ACCEPTED", facts["protected_base_snapshot"]["outcome"])
        result = self.classify(facts=facts)
        self.assertNotEqual("ACCEPTED", result["outcome"])
        self.assertIsNone(result["risk_level"])
        self.assert_schema(result)

    def test_real_producer_drift_fails_closed(self) -> None:
        facts = upstreams()
        facts["protected_base_snapshot"] = PRODUCER.render_protected_base_capture(
            task_id=TASK, repository=REPO, protected_base_sha=BASE,
            evidence_source="github:readback", verified_sha=BASE,
            prior_capture={"protected_base_sha": "b" * 40},
        )
        self.assertEqual("DRIFTED", facts["protected_base_snapshot"]["drift_state"])
        result = self.classify(facts=facts)
        self.assertEqual(("BLOCKED", "RISK_SOURCE_STALE"), (result["outcome"], result["reason_code"]))
        self.assert_schema(result)

    def test_wrong_protected_base_repository_not_accepted(self) -> None:
        facts = upstreams()
        facts["protected_base_snapshot"]["repository"] = "another/repository"
        result = self.classify(facts=facts)
        self.assertEqual(("HUMAN_REQUIRED", "RISK_SCOPE_AMBIGUOUS"), (result["outcome"], result["reason_code"]))
        self.assert_schema(result)

    def test_spoofed_legacy_base_sha_cannot_override_protected_base(self) -> None:
        facts = upstreams()
        facts["protected_base_snapshot"]["base_sha"] = BASE
        facts["protected_base_snapshot"]["protected_base_sha"] = "b" * 40
        result = self.classify(facts=facts)
        self.assertEqual(("BLOCKED", "RISK_SOURCE_STALE"), (result["outcome"], result["reason_code"]))
        self.assert_schema(result)


if __name__ == "__main__":
    unittest.main()
