from pathlib import Path
import json
import unittest

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "node-architect"


def load(name):
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


class CanonicalRuntimeSchemaTests(unittest.TestCase):
    def test_runtime_node_schema_requires_authority_and_effects(self):
        schema = load("runtime-node.schema.json")
        props = schema["properties"]
        self.assertIn("authority", props)
        self.assertIn("effects", props)
        self.assertIn("execution", props)
        self.assertFalse(schema["additionalProperties"])

    def test_runtime_graph_edges_distinguish_runtime_from_visualization(self):
        schema = load("runtime-graph.schema.json")
        edge_props = schema["properties"]["edges"]["items"]["properties"]
        self.assertIn("edge_type", edge_props)
        self.assertIn("runtime_executable", edge_props)
        self.assertIn("visualization", edge_props["edge_type"]["enum"])
        self.assertIn("runtime", edge_props["edge_type"]["enum"])

    def test_decision_rule_rejects_free_form_expression_type(self):
        schema = load("decision-rule.schema.json")
        validator = Draft202012Validator(schema)
        payload = {
            "schema_version": "1.0.0",
            "artifact_type": "decision-rule",
            "id": "bad-freeform-rule",
            "expression_type": "free_form_llm_text",
            "inputs": ["status"],
            "evaluation_record": {"record_fields": ["status"], "deterministic": True},
        }
        self.assertTrue(list(validator.iter_errors(payload)))

    def test_runtime_node_positive_fixture(self):
        schema = load("runtime-node.schema.json")
        payload = {
            "schema_version": "1.0.0",
            "artifact_type": "runtime-node",
            "id": "repo-delivery-ci-run-capture",
            "identity": {"stable_id": "repo-delivery-ci-run-capture", "family": "repo_delivery", "capability": "CI Run Capture", "runtime_slot": 19, "artifact_version": "1.0.0"},
            "authority": {"required_gate": "G5_DEPLOY", "required_evidence": ["exact merge SHA"], "may_mutate": [], "projection_only": False},
            "effects": {"classification": "read_only", "side_effects": [], "reversibility": "reversible", "idempotency": "idempotent"},
            "execution": {"determinism": "external_state_dependent", "suspendable": True, "resume_metadata": ["run_id", "head_sha"]},
            "interfaces": {"inputs": ["commit_sha"], "outputs": ["ci_status"], "preconditions": ["commit exists"], "postconditions": ["status recorded"]},
            "audit": {"history_refs": ["runtime-history"], "decision_refs": ["decision-rule"]},
        }
        Draft202012Validator(schema).validate(payload)


if __name__ == "__main__":
    unittest.main()
