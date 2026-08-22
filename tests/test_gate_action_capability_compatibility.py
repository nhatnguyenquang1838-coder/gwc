from __future__ import annotations

import copy
import unittest

from tools.gate_effect_authority import canonical_digest, evaluate_transitive_authority

REPO = "nhatnguyenquang1838-coder/gwc"
SHA = "a" * 40


def _packet() -> dict:
    return {
        "repository": REPO,
        "gate": "G2_EXECUTION",
        "action": "push_working_branch",
        "requested_capability": "GUARDED_REPO_WRITE",
        "scope": {
            "authorized_capabilities": [
                {"repository": REPO, "environment": "repository", "capability": "GUARDED_REPO_WRITE"}
            ],
            "independent_authorities": [],
        },
        "evidence_readback": {
            "event_id_or_idempotency_key": "evt-554",
            "effect_policy_digest": None,
        },
    }


def _action_identity() -> dict:
    return {
        "repository": REPO,
        "event_id_or_idempotency_key": "evt-554",
        "action": "push_working_branch",
        "branch": "chatgpt/scrum-554",
        "pr_number": None,
        "sha": SHA,
        "sha_kind": "branch_head",
        "gate": "G2_EXECUTION",
        "node": "G2/push",
    }


def _profile(kind: str, effects: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "gate-action-effect-profile",
        "profile_id": "push-working-branch-test",
        "profile_version": "1",
        "profile_kind": kind,
        "current": True,
        "complete": True,
        "action_identity": _action_identity(),
        "effects": effects,
    }


class CompatibilityProfileTests(unittest.TestCase):
    def _evaluate(self, packet: dict, profile: dict):
        packet = copy.deepcopy(packet)
        packet["trusted_effect_profile_ref"] = "profile:push-working-branch-test@1"
        packet["trusted_effect_profile_digest"] = canonical_digest(profile)
        packet["evidence_readback"]["effect_policy_digest"] = packet["trusted_effect_profile_digest"]
        return evaluate_transitive_authority(packet, trusted_profile=profile)

    def test_no_transitive_mutation_profile_passes_without_graph(self):
        result = self._evaluate(_packet(), _profile("NO_TRANSITIVE_MUTATION", []))
        self.assertTrue(result["allowed"])
        self.assertEqual(result["policy_source"], "trusted_effect_profile")

    def test_bounded_profile_with_read_only_closure_passes(self):
        profile = _profile("BOUNDED_TRANSITIVE_EFFECTS", [{
            "effect_id": "read-ci",
            "edge_state": "deterministic",
            "repository": REPO,
            "environment": "repository",
            "capability": "READ_ONLY",
        }])
        result = self._evaluate(_packet(), profile)
        self.assertTrue(result["allowed"])

    def test_bounded_profile_with_unauthorized_cross_repo_mutation_blocks(self):
        profile = _profile("BOUNDED_TRANSITIVE_EFFECTS", [{
            "effect_id": "cross-repo",
            "edge_state": "deterministic",
            "repository": "nhatnguyenquang1838-coder/DW-SuperApps",
            "environment": "repository",
            "capability": "GUARDED_REPO_WRITE",
        }])
        result = self._evaluate(_packet(), profile)
        self.assertFalse(result["allowed"])
        self.assertIn("CROSS_REPO_AUTHORITY_REQUIRED", result["reason_codes"])

    def test_profile_digest_drift_fails_closed(self):
        packet = _packet()
        profile = _profile("NO_TRANSITIVE_MUTATION", [])
        packet["trusted_effect_profile_ref"] = "profile:push-working-branch-test@1"
        packet["trusted_effect_profile_digest"] = "sha256:" + "0" * 64
        packet["evidence_readback"]["effect_policy_digest"] = packet["trusted_effect_profile_digest"]
        result = evaluate_transitive_authority(packet, trusted_profile=profile)
        self.assertFalse(result["allowed"])
        self.assertIn("EFFECT_PROFILE_DIGEST_MISMATCH", result["reason_codes"])

    def test_incomplete_profile_fails_closed(self):
        profile = _profile("BOUNDED_TRANSITIVE_EFFECTS", [])
        profile["complete"] = False
        result = self._evaluate(_packet(), profile)
        self.assertFalse(result["allowed"])
        self.assertIn("EFFECT_PROFILE_INCOMPLETE", result["reason_codes"])

    def test_stale_profile_fails_closed(self):
        profile = _profile("NO_TRANSITIVE_MUTATION", [])
        profile["current"] = False
        result = self._evaluate(_packet(), profile)
        self.assertFalse(result["allowed"])
        self.assertIn("EFFECT_PROFILE_STALE", result["reason_codes"])


class SchemaSourceOfTruthTests(unittest.TestCase):
    def test_registry_matches_schema_and_actions_reference_known_capabilities(self):
        import json
        from pathlib import Path
        import yaml
        from jsonschema import Draft202012Validator

        root = Path(__file__).resolve().parents[1]
        registry = yaml.safe_load((root / "governance/gate-action-capability-registry.yaml").read_text())
        schema = json.loads((root / "schemas/gate-action-capability-registry.schema.json").read_text())
        errors = list(Draft202012Validator(schema).iter_errors(registry))
        self.assertEqual([], [e.message for e in errors])
        known = set(registry["capabilities"])
        self.assertTrue(known)
        self.assertTrue(all(meta["capability"] in known for meta in registry["actions"].values()))

    def test_effect_graph_schema_accepts_conditional_destructive_effect(self):
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator

        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / "schemas/gate-action-effect-graph.schema.json").read_text())
        graph = {
            "schema_version": "1.0",
            "artifact_type": "gate-action-effect-graph",
            "graph_id": "incident",
            "source_action_identity": _action_identity(),
            "effects": [{
                "effect_id": "retention-delete",
                "edge_state": "conditional",
                "repository": REPO,
                "environment": "repository",
                "capability": "DESTRUCTIVE",
                "predicate": {
                    "state": "unknown",
                    "evidence_identity_digest": "sha256:" + "a" * 64,
                },
            }],
        }
        self.assertEqual([], [e.message for e in Draft202012Validator(schema).iter_errors(graph)])

    def test_lifecycle_contract_points_to_one_capability_effect_source_of_truth(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        text = (root / "core/GATE_LIFECYCLE_CONTRACT_v1.0.md").read_text()
        for marker in (
            "governance/gate-action-capability-registry.yaml",
            "schemas/gate-action-effect-graph.schema.json",
            "schemas/gate-action-effect-profile.schema.json",
            "EFFECT_GRAPH_REQUIRED",
            "Gate labels remain compatibility projections",
        ):
            self.assertIn(marker, text)

    def test_effect_profile_schema_requires_current_complete_profile(self):
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator

        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / "schemas/gate-action-effect-profile.schema.json").read_text())
        profile = _profile("NO_TRANSITIVE_MUTATION", [])
        self.assertEqual([], [e.message for e in Draft202012Validator(schema).iter_errors(profile)])
        profile["complete"] = False
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(profile)))


class GateActionValidatorIntegrationTests(unittest.TestCase):
    def _legacy_push_packet(self):
        from datetime import datetime, timezone
        from tools.validate_gate_action import canonical_scope_hash

        value = {
            "schema_version": "1.0",
            "artifact_type": "gate-action-authority",
            "task_id": "SCRUM-554",
            "repository": REPO,
            "base_ref": "main",
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "working_branch": "chatgpt/scrum-554",
            "gate": "G2_EXECUTION",
            "action": "push_working_branch",
            "scope": {
                "authorized_paths": ["tools/gate_effect_authority.py"],
                "authorized_actions": ["push_working_branch"],
                "excluded_actions": ["merge_approved_pr"],
                "risk_class": "R2",
            },
            "issued_at": "2026-08-18T12:00:00Z",
            "expires_at": "2026-08-19T12:00:00Z",
            "actor": {"kind": "connector", "id": "chatgpt"},
            "evidence_readback": {
                "status": "confirmed",
                "observed_at": "2026-08-18T12:01:00Z",
                "task_id": "SCRUM-554",
                "repository": REPO,
                "base_sha": "a" * 40,
                "head_sha": "b" * 40,
                "gate": "G2_EXECUTION",
                "action": "push_working_branch",
                "scope_hash": "sha256:" + "0" * 64,
                "event_id_or_idempotency_key": "evt-554-push",
            },
        }
        value["scope_hash"] = canonical_scope_hash(value)
        value["evidence_readback"]["scope_hash"] = value["scope_hash"]
        return value

    def test_trigger_capable_legacy_packet_without_graph_or_profile_fails_effect_graph_required(self):
        from datetime import datetime, timezone
        from pathlib import Path
        from tools.validate_gate_action import validate

        root = Path(__file__).resolve().parents[1]
        errors = validate(
            self._legacy_push_packet(),
            schema_path=root / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc),
        )
        self.assertIn("EFFECT_GRAPH_REQUIRED", errors)

    def test_malformed_inline_effect_graph_is_rejected_by_focused_schema(self):
        from datetime import datetime, timezone
        from pathlib import Path
        from tools.validate_gate_action import canonical_scope_hash, validate

        root = Path(__file__).resolve().parents[1]
        value = self._legacy_push_packet()
        graph = {
            "schema_version": "1.0",
            "artifact_type": "gate-action-effect-graph",
            "graph_id": "malformed-inline",
            "source_action_identity": {
                "repository": REPO,
                "event_id_or_idempotency_key": "evt-554-push",
                "action": "push_working_branch",
                "branch": value["working_branch"],
                "pr_number": None,
                "sha": value["head_sha"],
                "sha_kind": "branch_head",
                "gate": "G2_EXECUTION",
                "node": "G2/push",
            },
            "effects": [],
            "bogus": "must-fail-schema",
        }
        value["requested_capability"] = "GUARDED_REPO_WRITE"
        value["scope"]["authorized_capabilities"] = [{
            "repository": REPO, "environment": "repository", "capability": "GUARDED_REPO_WRITE"
        }]
        value["scope"]["independent_authorities"] = []
        value["effect_graph_ref"] = "inline:malformed-inline"
        value["effect_graph"] = graph
        value["effect_graph_digest"] = canonical_digest(graph)
        value["evidence_readback"]["effect_policy_digest"] = value["effect_graph_digest"]
        value["scope_hash"] = canonical_scope_hash(value)
        value["evidence_readback"]["scope_hash"] = value["scope_hash"]
        errors = validate(
            value,
            schema_path=root / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(any("effect_graph" in error and "bogus" in error for error in errors), errors)

    def test_digest_bound_no_transitive_mutation_profile_passes_validator(self):
        from datetime import datetime, timezone
        from pathlib import Path
        from tools.validate_gate_action import canonical_scope_hash, validate

        root = Path(__file__).resolve().parents[1]
        value = self._legacy_push_packet()
        profile = _profile("NO_TRANSITIVE_MUTATION", [])
        profile["action_identity"]["event_id_or_idempotency_key"] = "evt-554-push"
        profile["action_identity"]["branch"] = value["working_branch"]
        profile["action_identity"]["sha"] = value["head_sha"]
        value["requested_capability"] = "GUARDED_REPO_WRITE"
        value["scope"]["authorized_capabilities"] = [{
            "repository": REPO, "environment": "repository", "capability": "GUARDED_REPO_WRITE"
        }]
        value["scope"]["independent_authorities"] = []
        value["trusted_effect_profile_ref"] = "profile:push-working-branch-test@1"
        value["trusted_effect_profile"] = profile
        value["trusted_effect_profile_digest"] = canonical_digest(profile)
        value["evidence_readback"]["effect_policy_digest"] = value["trusted_effect_profile_digest"]
        value["scope_hash"] = canonical_scope_hash(value)
        value["evidence_readback"]["scope_hash"] = value["scope_hash"]
        errors = validate(
            value,
            schema_path=root / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc),
        )
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
