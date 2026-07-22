import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "tools" / "node_architect" / "validate_node_catalog_expansion_plan.py"
PLAN_PATH = ROOT / "core" / "node-architect" / "node-catalog-expansion-plan.json"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_node_catalog_expansion_plan", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class NodeCatalogExpansionPlanTests(unittest.TestCase):
    def setUp(self):
        self.validator = load_validator()
        self.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    def test_plan_validates(self):
        self.validator.validate_plan(self.plan)

    def test_total_must_remain_81(self):
        plan = dict(self.plan)
        plan["target_total_nodes"] = 82
        with self.assertRaises(self.validator.ValidationError):
            self.validator.validate_plan(plan)

    def test_scale_flag_must_remain_false(self):
        plan = dict(self.plan)
        plan["scale_81_nodes_allowed"] = True
        with self.assertRaises(self.validator.ValidationError):
            self.validator.validate_plan(plan)

    def test_batches_cannot_exceed_nine_nodes(self):
        plan = json.loads(json.dumps(self.plan))
        plan["batch_sequence"][0]["planned_nodes"] = 10
        with self.assertRaises(self.validator.ValidationError):
            self.validator.validate_plan(plan)

    def test_every_family_must_be_batched_once(self):
        plan = json.loads(json.dumps(self.plan))
        plan["batch_sequence"][1]["family_id"] = plan["batch_sequence"][0]["family_id"]
        with self.assertRaises(self.validator.ValidationError):
            self.validator.validate_plan(plan)

    def test_cli_returns_failure_for_invalid_plan(self):
        plan = json.loads(json.dumps(self.plan))
        plan["implementation_allowed"] = True
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_plan = Path(tmpdir) / "bad-plan.json"
            bad_plan.write_text(json.dumps(plan), encoding="utf-8")
            self.assertEqual(self.validator.main(["--plan", str(bad_plan)]), 1)


if __name__ == "__main__":
    unittest.main()
