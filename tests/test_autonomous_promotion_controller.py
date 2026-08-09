import unittest

from tools.node_architect.promotion_controller import autonomous_main_action_allowed, evaluate_promotion

A = "a" * 40
B = "b" * 40
C = "c" * 40


class PromotionControllerTests(unittest.TestCase):
    def test_incomplete_dag_blocks_promotion(self):
        result = evaluate_promotion(promotion_id="P1", required_nodes=["A", "B"], completed_nodes=["A"],
                                    base_main_sha=A, preprod_cut_sha=B, integration_conclusion="success")
        self.assertEqual(result["reason_code"], "AUTONOMOUS_PROMOTION_DAG_INCOMPLETE")

    def test_promotion_uses_immutable_cut_branch_and_draft(self):
        result = evaluate_promotion(promotion_id="P1", required_nodes=["A"], completed_nodes=["A"],
                                    base_main_sha=A, preprod_cut_sha=B, integration_conclusion="success")
        self.assertEqual(result["outcome"], "ALLOW")
        self.assertEqual(result["base_branch"], "main")
        self.assertTrue(result["draft"])
        self.assertTrue(result["source_branch"].endswith(B[:12]))
        self.assertFalse(result["main_merge_allowed"])
        self.assertFalse(result["mark_ready_allowed"])

    def test_duplicate_promotion_is_readback_not_second_effect(self):
        first = evaluate_promotion(promotion_id="P1", required_nodes=["A"], completed_nodes=["A"],
                                   base_main_sha=A, preprod_cut_sha=B, integration_conclusion="success")
        replay = evaluate_promotion(promotion_id="P1", required_nodes=["A"], completed_nodes=["A"],
                                    base_main_sha=A, preprod_cut_sha=B, integration_conclusion="success",
                                    existing_promotion=first)
        self.assertEqual(replay["reason_code"], "AUTONOMOUS_PROMOTION_REPLAY")

    def test_cut_drift_blocks_existing_promotion(self):
        first = evaluate_promotion(promotion_id="P1", required_nodes=["A"], completed_nodes=["A"],
                                   base_main_sha=A, preprod_cut_sha=B, integration_conclusion="success")
        drift = evaluate_promotion(promotion_id="P1", required_nodes=["A"], completed_nodes=["A"],
                                   base_main_sha=A, preprod_cut_sha=C, integration_conclusion="success",
                                   existing_promotion=first)
        self.assertEqual(drift["reason_code"], "AUTONOMOUS_PROMOTION_CUT_DRIFT")

    def test_autonomous_main_merge_is_never_allowed(self):
        self.assertTrue(autonomous_main_action_allowed("create_draft_pr"))
        self.assertFalse(autonomous_main_action_allowed("merge"))
        self.assertFalse(autonomous_main_action_allowed("mark_ready"))


if __name__ == "__main__":
    unittest.main()
