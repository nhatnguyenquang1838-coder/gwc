from __future__ import annotations

import unittest

from tools.node_architect.build_run_graph import build_run_graph
from tools.node_architect.render_gate_story import build_gate_story
from tools.node_architect.render_pr_run_evidence import (
    BEGIN_MARKER,
    END_MARKER,
    ManagedBlockError,
    build_managed_block,
    extract_managed_metadata,
    upsert_managed_block,
    validate_managed_block,
)
from tests.test_run_graph_builder import manifest


class PrRunEvidenceRendererTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_run_graph(manifest())
        self.story = build_gate_story(
            self.graph,
            gate_statuses={"G4_MERGE": "not_executed", "G5_DEPLOY": "not_executed", "G6_PRODUCTION_DATA": "not_applicable"},
        )
        self.block, self.evidence_digest = build_managed_block(
            self.graph,
            self.story,
            validation={"focused_tests": "PASS", "exact_head_ci": "not_executed"},
            g4_readiness={"state": "not_ready", "reason": "G4 authority not granted"},
        )

    def test_upsert_is_idempotent_and_preserves_human_content(self):
        original = "# Human PR summary\n\nKeep this content.\n"
        first, first_digest = upsert_managed_block(original, self.block)
        second, second_digest = upsert_managed_block(first, self.block)
        self.assertEqual(first, second)
        self.assertEqual(first_digest, second_digest)
        self.assertTrue(first.startswith(original.rstrip()))
        self.assertEqual(1, first.count(BEGIN_MARKER))
        self.assertEqual(1, first.count(END_MARKER))

    def test_metadata_is_exact_head_graph_story_and_evidence_bound(self):
        body, _ = upsert_managed_block("human", self.block)
        metadata = extract_managed_metadata(body)
        self.assertEqual(self.graph["head_sha"], metadata["head_sha"])
        self.assertEqual(self.graph["graph_digest"], metadata["graph_digest"])
        self.assertEqual(self.story["story_digest"], metadata["story_digest"])
        self.assertEqual(self.evidence_digest, metadata["evidence_digest"])
        self.assertEqual([], validate_managed_block(body, expected_head_sha=self.graph["head_sha"]))

    def test_head_drift_fails_closed(self):
        body, _ = upsert_managed_block("human", self.block)
        errors = validate_managed_block(body, expected_head_sha="c" * 40)
        self.assertTrue(any("AUTONOMOUS_PR_HEAD_DRIFT" in error for error in errors))

    def test_duplicate_or_unbalanced_markers_fail_closed(self):
        malformed = f"{BEGIN_MARKER}\n{BEGIN_MARKER}\n{END_MARKER}"
        with self.assertRaises(ManagedBlockError) as raised:
            upsert_managed_block(malformed, self.block)
        self.assertEqual("AUTONOMOUS_PR_MARKER_MALFORMED", raised.exception.reason_code)

    def test_block_contains_mermaid_node_table_and_g0_to_g6_story(self):
        self.assertIn("```mermaid", self.block)
        self.assertIn("### Node participation", self.block)
        self.assertIn("### G0→G6 storyteller", self.block)
        self.assertIn("#### G6_PRODUCTION_DATA — not_applicable", self.block)
        self.assertNotIn("all 81 nodes", self.block)


if __name__ == "__main__":
    unittest.main()
