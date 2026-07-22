import json
import tempfile
import unittest
from pathlib import Path
import importlib.util


VALIDATOR_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "node_architect"
    / "validate_node_catalog_intake_context.py"
)


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_intake_context", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def valid_node(slug: str) -> dict:
    return {
        "node_id": f"intake_context.{slug}",
        "node_type": "workflow",
        "title": slug.replace("-", " ").title(),
        "canonical": "canonical",
        "authority_boundary": "read_only",
        "gates": ["G0_CONTEXT"],
        "description": f"{slug} validation fixture.",
    }


class IntakeContextNodeCatalogTests(unittest.TestCase):
    def setUp(self):
        self.validator = load_validator()

    def write_family(self, root: Path, nodes: list[dict]) -> Path:
        family_dir = root / "intake_context"
        family_dir.mkdir(parents=True, exist_ok=True)
        for node in nodes:
            slug = node["node_id"].split(".", 1)[1]
            (family_dir / f"{slug}.node.json").write_text(
                json.dumps(node, indent=2) + "\n",
                encoding="utf-8",
            )
        return family_dir

    def test_valid_nine_node_family_passes(self):
        slugs = [
            "request-intake",
            "source-resolution",
            "repo-identity-check",
            "protected-base-capture",
            "risk-classification",
            "files-read-scope",
            "files-write-scope",
            "intake-card-render",
            "context-gap-escalation",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), [valid_node(slug) for slug in slugs])
            self.assertEqual([], self.validator.validate_family(family_dir))

    def test_rejects_non_g0_gate(self):
        slugs = [f"node-{index}" for index in range(9)]
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0]["gates"] = ["G1_ALIGNMENT"]
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("gates must be exactly" in error for error in errors))

    def test_rejects_extra_node(self):
        slugs = [f"node-{index}" for index in range(10)]
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), [valid_node(slug) for slug in slugs])
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("expected exactly 9" in error for error in errors))

    def test_rejects_write_authority(self):
        slugs = [f"node-{index}" for index in range(9)]
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0]["authority_boundary"] = "g2_required"
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("read-only/none authority" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
