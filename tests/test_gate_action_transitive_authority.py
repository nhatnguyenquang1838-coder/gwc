from __future__ import annotations

import copy
import unittest

from tools.gate_effect_authority import canonical_digest, evaluate_transitive_authority

REPO = "nhatnguyenquang1838-coder/gwc"
SHA = "a" * 40


def _identity(action: str = "merge_approved_pr", gate: str = "G4_MERGE") -> dict:
    return {
        "repository": REPO,
        "event_id_or_idempotency_key": "evt-554",
        "action": action,
        "branch": "chatgpt/scrum-554",
        "pr_number": 468,
        "sha": SHA,
        "sha_kind": "pr_head",
        "gate": gate,
        "node": "G4/merge",
    }


def _packet(action: str = "merge_approved_pr", capability: str = "MERGE") -> dict:
    return {
        "repository": REPO,
        "working_branch": "chatgpt/scrum-554",
        "head_sha": SHA,
        "gate": "G4_MERGE",
        "action": action,
        "requested_capability": capability,
        "scope": {
            "authorized_capabilities": [
                {"repository": REPO, "environment": "repository", "capability": capability}
            ],
            "independent_authorities": [],
        },
        "evidence_readback": {
            "event_id_or_idempotency_key": "evt-554",
            "effect_policy_digest": None,
        },
    }


def _graph(effects: list[dict], action: str = "merge_approved_pr") -> dict:
    graph = {
        "schema_version": "1.0",
        "artifact_type": "gate-action-effect-graph",
        "graph_id": "scrum-554-test",
        "source_action_identity": _identity(action),
        "effects": effects,
    }
    return graph


def _effect(
    effect_id: str,
    capability: str,
    *,
    repository: str = REPO,
    edge_state: str = "deterministic",
    predicate_state: str | None = None,
    predicate_identity_digest: str | None = None,
) -> dict:
    out = {
        "effect_id": effect_id,
        "edge_state": edge_state,
        "repository": repository,
        "environment": "repository",
        "capability": capability,
    }
    if edge_state == "conditional":
        out["predicate"] = {"state": predicate_state}
        if predicate_identity_digest is not None:
            out["predicate"]["evidence_identity_digest"] = predicate_identity_digest
    return out


class TransitiveAuthorityTests(unittest.TestCase):
    def _evaluate(self, packet: dict, graph: dict):
        packet = copy.deepcopy(packet)
        packet["effect_graph_ref"] = "inline:scrum-554-test"
        packet["effect_graph_digest"] = canonical_digest(graph)
        packet["evidence_readback"]["effect_policy_digest"] = packet["effect_graph_digest"]
        return evaluate_transitive_authority(packet, effect_graph=graph)

    def test_direct_authorized_but_destructive_child_blocks(self):
        packet = _packet()
        graph = _graph([_effect("delete-retention", "DESTRUCTIVE")])
        result = self._evaluate(packet, graph)
        self.assertFalse(result["allowed"])
        self.assertIn("TRANSITIVE_AUTHORITY_REQUIRED", result["reason_codes"])

    def test_safe_read_only_child_does_not_escalate(self):
        packet = _packet()
        graph = _graph([_effect("read-ci", "READ_ONLY")])
        result = self._evaluate(packet, graph)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["reason_codes"], ["TRANSITIVE_AUTHORITY_CLOSED"])

    def test_cross_repo_mutating_child_requires_independent_authority(self):
        packet = _packet()
        graph = _graph([
            _effect("cross-repo-write", "GUARDED_REPO_WRITE", repository="nhatnguyenquang1838-coder/DW-SuperApps")
        ])
        result = self._evaluate(packet, graph)
        self.assertFalse(result["allowed"])
        self.assertIn("CROSS_REPO_AUTHORITY_REQUIRED", result["reason_codes"])

    def test_cross_repo_mutating_child_passes_with_independent_authority(self):
        packet = _packet()
        packet["scope"]["independent_authorities"].append({
            "repository": "nhatnguyenquang1838-coder/DW-SuperApps",
            "environment": "repository",
            "capability": "GUARDED_REPO_WRITE",
        })
        graph = _graph([
            _effect("cross-repo-write", "GUARDED_REPO_WRITE", repository="nhatnguyenquang1838-coder/DW-SuperApps")
        ])
        result = self._evaluate(packet, graph)
        self.assertTrue(result["allowed"])

    def test_conditional_false_requires_bound_predicate_evidence(self):
        packet = _packet()
        graph = _graph([
            _effect("maybe-delete", "DESTRUCTIVE", edge_state="conditional", predicate_state="false")
        ])
        result = self._evaluate(packet, graph)
        self.assertFalse(result["allowed"])
        self.assertIn("PREDICATE_EVIDENCE_REQUIRED", result["reason_codes"])

    def test_conditional_false_with_bound_evidence_is_excluded(self):
        packet = _packet()
        identity_digest = canonical_digest(_identity())
        graph = _graph([
            _effect(
                "maybe-delete",
                "DESTRUCTIVE",
                edge_state="conditional",
                predicate_state="false",
                predicate_identity_digest=identity_digest,
            )
        ])
        result = self._evaluate(packet, graph)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["excluded_effect_ids"], ["maybe-delete"])

    def test_conditional_true_is_reachable(self):
        packet = _packet()
        graph = _graph([
            _effect("maybe-release", "RELEASE_PUBLISH", edge_state="conditional", predicate_state="true")
        ])
        result = self._evaluate(packet, graph)
        self.assertFalse(result["allowed"])
        self.assertIn("TRANSITIVE_AUTHORITY_REQUIRED", result["reason_codes"])

    def test_conditional_unknown_mutation_is_potentially_reachable(self):
        packet = _packet()
        graph = _graph([
            _effect("maybe-delete", "DESTRUCTIVE", edge_state="conditional", predicate_state="unknown")
        ])
        result = self._evaluate(packet, graph)
        self.assertFalse(result["allowed"])
        self.assertIn("TRANSITIVE_AUTHORITY_REQUIRED", result["reason_codes"])
        self.assertIn("maybe-delete", result["potentially_reachable_effect_ids"])

    def test_conditional_unknown_read_only_is_non_escalating(self):
        packet = _packet()
        graph = _graph([
            _effect("maybe-read", "READ_ONLY", edge_state="conditional", predicate_state="unknown")
        ])
        result = self._evaluate(packet, graph)
        self.assertTrue(result["allowed"])
        self.assertIn("maybe-read", result["observable_effect_ids"])

    def test_release_authority_does_not_cover_destructive_retention(self):
        packet = _packet(capability="RELEASE_PUBLISH")
        graph = _graph([_effect("retention-delete", "DESTRUCTIVE")])
        result = self._evaluate(packet, graph)
        self.assertFalse(result["allowed"])
        self.assertIn("TRANSITIVE_AUTHORITY_REQUIRED", result["reason_codes"])

    def test_trigger_capable_action_without_graph_or_profile_fails_closed(self):
        packet = _packet(action="push_working_branch", capability="GUARDED_REPO_WRITE")
        packet["gate"] = "G2_EXECUTION"
        result = evaluate_transitive_authority(packet)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["primary_reason_code"], "EFFECT_GRAPH_REQUIRED")


    def test_graph_source_head_drift_is_rejected(self):
        packet = _packet()
        graph = _graph([_effect("read-ci", "READ_ONLY")])
        graph["source_action_identity"]["sha"] = "b" * 40
        result = self._evaluate(packet, graph)
        self.assertFalse(result["allowed"])
        self.assertIn("EFFECT_SOURCE_IDENTITY_MISMATCH", result["reason_codes"])

    def test_replay_decision_digest_is_deterministic_and_drift_sensitive(self):
        packet = _packet()
        graph = _graph([_effect("read-ci", "READ_ONLY")])
        first = self._evaluate(packet, graph)
        second = self._evaluate(packet, graph)
        self.assertEqual(first["decision_digest"], second["decision_digest"])
        drifted = copy.deepcopy(graph)
        drifted["effects"].append(_effect("read-more", "READ_ONLY"))
        packet2 = copy.deepcopy(packet)
        packet2["effect_graph_ref"] = "inline:scrum-554-test"
        packet2["effect_graph_digest"] = canonical_digest(drifted)
        packet2["evidence_readback"]["effect_policy_digest"] = packet2["effect_graph_digest"]
        third = evaluate_transitive_authority(packet2, effect_graph=drifted)
        self.assertNotEqual(first["decision_digest"], third["decision_digest"])

    def test_graph_digest_drift_is_rejected(self):
        packet = _packet()
        graph = _graph([_effect("read-ci", "READ_ONLY")])
        packet["effect_graph_ref"] = "inline:scrum-554-test"
        packet["effect_graph_digest"] = "sha256:" + "0" * 64
        packet["evidence_readback"]["effect_policy_digest"] = packet["effect_graph_digest"]
        result = evaluate_transitive_authority(packet, effect_graph=graph)
        self.assertFalse(result["allowed"])
        self.assertIn("EFFECT_GRAPH_DIGEST_MISMATCH", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
