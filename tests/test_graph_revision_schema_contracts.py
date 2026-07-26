from pathlib import Path
import json
import unittest

from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SCHEMA_DIR = ROOT / "schemas" / "runtime"


def load(name):
    return json.loads((RUNTIME_SCHEMA_DIR / name).read_text(encoding="utf-8"))


class GraphRevisionSchemaTests(unittest.TestCase):
    def test_graph_revision_schema_positive_fixture(self):
        schema = load("graph-revision.schema.json")
        payload = {
            "revision_id": "scrum-104-20260726",
            "parent_revision_id": None,
            "source_sha": "7b7ddbab2dd8ca73d715e6e2ed7c67cda5df8ef1215a27c0e22a9b240722ee9d",
        }
        Draft202012Validator(schema).validate(payload)

    def test_graph_revision_schema_rejects_bad_source_sha(self):
        schema = load("graph-revision.schema.json")
        payload = {
            "revision_id": "scrum-104-20260726",
            "parent_revision_id": None,
            "source_sha": "not-a-sha",
        }
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(payload)))

    def test_runtime_graph_revision_uses_exported_schema_ref(self):
        runtime_graph_schema = load("runtime-graph.schema.json")
        self.assertEqual(
            runtime_graph_schema["properties"]["revision"]["$ref"],
            "https://gwc.local/schemas/runtime/graph-revision.schema.json",
        )

        store = {
            schema["$id"]: schema
            for schema in (load("runtime-graph.schema.json"), load("graph-revision.schema.json"))
            if "$id" in schema
        }
        validator = Draft202012Validator(
            runtime_graph_schema,
            resolver=RefResolver(runtime_graph_schema["$id"], runtime_graph_schema, store),
        )
        payload = {
            "schema_version": "1.0.0",
            "artifact_type": "runtime-graph",
            "graph_id": "gwc-runtime-graph-registry",
            "revision": {
                "revision_id": "scrum-104-20260726",
                "parent_revision_id": None,
                "source_sha": "7b7ddbab2dd8ca73d715e6e2ed7c67cda5df8ef1215a27c0e22a9b240722ee9d",
            },
            "nodes": ["repo_delivery.ci-run-capture"],
            "edges": [],
            "provenance": {
                "source_path": "core/RUNTIME_CATALOG_KNOWLEDGE_GRAPH_CONTRACT_v1.0.md",
                "source_sha": "7b7ddbab2dd8ca73d715e6e2ed7c67cda5df8ef1215a27c0e22a9b240722ee9d",
            },
        }
        validator.validate(payload)


if __name__ == "__main__":
    unittest.main()
