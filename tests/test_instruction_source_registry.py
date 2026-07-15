import json
from pathlib import Path
import unittest

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


class InstructionSourceRegistryTests(unittest.TestCase):
    def test_registry_matches_schema(self):
        schema = json.loads((ROOT / "schemas/instruction-source-registry.schema.json").read_text(encoding="utf-8"))
        registry = yaml.safe_load((ROOT / "governance/instruction-source-registry.yaml").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(registry), key=lambda item: list(item.path))
        self.assertEqual([], errors)

    def test_source_ids_are_unique(self):
        registry = yaml.safe_load((ROOT / "governance/instruction-source-registry.yaml").read_text(encoding="utf-8"))
        ids = [source["id"] for source in registry["sources"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_priorities_are_unique(self):
        registry = yaml.safe_load((ROOT / "governance/instruction-source-registry.yaml").read_text(encoding="utf-8"))
        priorities = [source["priority"] for source in registry["sources"]]
        self.assertEqual(len(priorities), len(set(priorities)))


if __name__ == "__main__":
    unittest.main()
