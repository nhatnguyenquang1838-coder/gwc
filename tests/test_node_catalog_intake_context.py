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

    def test_accepts_typed_intake_contract(self):
        """Test that request-intake with typed intake fields validates successfully."""
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
        nodes = [valid_node(slug) for slug in slugs]
        # Add typed intake contract fields to request-intake
        nodes[0].update({
            "intent": "User-specified task scope.",
            "outcome": "Normalized typed intake record.",
            "constraints": ["Input must follow canonical request shape."],
            "exclusions": ["Production runtime behavior."],
            "entry_guards": ["G0_CONTEXT", "read_only"],
            "reason_codes": {"ACCEPTED": "Request normalized successfully."}
        })
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"Typed intake contract should validate: {errors}")

    def test_rejects_malformed_typed_fields(self):
        """Test that malformed typed intake fields are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0]["intent"] = 123  # Should be string
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("intent must be a string" in error for error in errors))

    def test_rejects_malformed_constraints(self):
        """Test that non-list or non-string constraints are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0]["constraints"] = "not a list"  # Should be list
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("constraints must be a list" in error for error in errors))

    def test_rejects_malformed_reason_codes(self):
        """Test that invalid reason_codes structures are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        # Nested dict in reason_codes values should be rejected
        nodes[0]["reason_codes"] = {"key": "value", "nested": {"obj": "value"}}
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("reason_codes" in error for error in errors))

    def test_accepts_string_reason_code(self):
        """Test that string reason_codes are accepted."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0]["reason_codes"] = "ACCEPTED"
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"String reason_codes should validate: {errors}")

    def test_typed_fields_preserve_g0_gate_and_readonly(self):
        """Test that typed intake contract preserves G0_CONTEXT and read_only boundary."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0].update({
            "intent": "Test intent.",
            "outcome": "Test outcome.",
            "constraints": [],
            "exclusions": [],
            "entry_guards": [],
            "reason_codes": {}
        })
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"G0 gate and read-only authority should persist: {errors}")

    def test_source_resolution_accepts_typed_source_contract(self):
        """Test that source-resolution with typed source-resolution fields validates successfully."""
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
        nodes = [valid_node(slug) for slug in slugs]
        # Add typed source-resolution fields to source-resolution node
        nodes[1].update({
            "intent": "Determine the authoritative source of active instructions.",
            "outcome": "Typed source-resolution record with mode, authority, provenance, and reason codes.",
            "constraints": [
                "Source mode must be deterministically resolved as REPO, PACKAGE, or MIXED.",
                "Fail closed when source authority cannot be distinguished."
            ],
            "exclusions": [
                "Production runtime behavior",
                "Deployment logic",
                "Migration logic"
            ],
            "entry_guards": [
                "G0_CONTEXT",
                "read_only"
            ],
            "reason_codes": {
                "ACCEPTED": "Source mode resolved deterministically with verified provenance.",
                "AMBIGUOUS": "Repository and package authority cannot be distinguished.",
                "MALFORMED": "Provenance evidence is incomplete or invalid.",
                "MISSING_EVIDENCE": "Required source inputs cannot be audited.",
                "INVALID_MODE": "Resolved source mode token is not REPO, PACKAGE, or MIXED."
            }
        })
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"Typed source-resolution contract should validate: {errors}")

    def test_source_resolution_rejects_malformed_reason_codes(self):
        """Test that malformed reason_codes in source-resolution are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[1]["reason_codes"] = {"key": {"nested": "object"}}  # Nested object should be rejected
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("reason_codes" in error for error in errors))

    def test_source_resolution_rejects_malformed_constraints(self):
        """Test that malformed constraints in source-resolution are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[1]["constraints"] = "not a list"  # Should be list
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("constraints must be a list" in error for error in errors))

    def test_source_resolution_rejects_malformed_entry_guards(self):
        """Test that malformed entry_guards in source-resolution are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[1]["entry_guards"] = "not a list"  # Should be list
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("entry_guards must be a list" in error for error in errors))

    def test_source_resolution_rejects_malformed_exclusions(self):
        """Test that malformed exclusions in source-resolution are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[1]["exclusions"] = "not a list"  # Should be list
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("exclusions must be a list" in error for error in errors))

    def test_source_resolution_accepts_string_reason_code(self):
        """Test that string reason_codes in source-resolution are accepted."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[1]["reason_codes"] = "ACCEPTED"
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"String reason_codes should validate: {errors}")


if __name__ == "__main__":
    unittest.main()
