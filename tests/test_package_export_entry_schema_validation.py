#!/usr/bin/env python3
"""Tests for package_export.entry-schema-validation (SCRUM-230, M4_DETERMINISTIC).

Fixtures cover: valid entry, missing required field, unknown field, wrong
boolean/type, invalid id, empty path/target, duplicate id, schema-version drift,
determinism, purity (no filesystem access) and result-schema conformance.
"""
import json
import sys
import unittest
from pathlib import Path

# Import from the repo's `tools/` directory directly: a host environment may
# already own a different top-level `tools` package on sys.path, so the dotted
# `tools.node_architect...` form is not reliable under the bare CI command
# `python -m unittest discover -s tests`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from node_architect.package_export.entry_schema_validation import (  # noqa: E402
    ENTRY_DUPLICATE_ID,
    ENTRY_ID_INVALID,
    ENTRY_REQUIRED_FIELD_MISSING,
    ENTRY_SCHEMA_INVALID,
    ENTRY_TYPE_INVALID,
    ENTRY_UNKNOWN_FIELD,
    ENTRY_VERSION_UNSUPPORTED,
    Outcome,
    validate_entries,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    REPO_ROOT
    / "schemas"
    / "node-architect"
    / "package-export"
    / "entry-schema-validation.schema.json"
)
SOURCE_SHA = "d9a89a002aae4348359cd88810a9d03926199597"


def _entry(**overrides):
    base = {
        "id": "core.governance",
        "path": "core/Coding_Project_Governance_v1.0.md",
        "target": "core/Coding_Project_Governance_v1.0.md",
        "required": True,
        "entry_version": "0.1",
    }
    base.update(overrides)
    return base


def _manifest(*entries):
    return {"package": "gwc", "entries": list(entries)}


def _codes(result):
    return [e.reason_code for e in result.errors]


class ValidEntryTest(unittest.TestCase):
    def test_valid_manifest_passes(self):
        result = validate_entries(_manifest(_entry()), source_sha=SOURCE_SHA)
        self.assertEqual(result.outcome, Outcome.PASS)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.accepted_entry_ids, ["core.governance"])
        self.assertFalse(result.authority_granted)

    def test_optional_fields_allowed_and_entry_version_optional(self):
        entry = _entry(description="governance core", category="core")
        entry.pop("entry_version")
        result = validate_entries(_manifest(entry))
        self.assertEqual(result.outcome, Outcome.PASS)

    def test_empty_entries_list_passes_with_empty_inventory(self):
        result = validate_entries(_manifest())
        self.assertEqual(result.outcome, Outcome.PASS)
        self.assertEqual(result.inventory, [])


class RejectionTest(unittest.TestCase):
    def test_missing_required_field(self):
        entry = _entry()
        entry.pop("target")
        result = validate_entries(_manifest(entry))
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertIn(ENTRY_REQUIRED_FIELD_MISSING, _codes(result))
        self.assertFalse(result.inventory[0].accepted)

    def test_unknown_field_rejected(self):
        result = validate_entries(_manifest(_entry(publish=True)))
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertIn(ENTRY_UNKNOWN_FIELD, _codes(result))

    def test_wrong_boolean_type(self):
        result = validate_entries(_manifest(_entry(required="yes")))
        self.assertIn(ENTRY_TYPE_INVALID, _codes(result))

    def test_bool_not_accepted_for_string_field(self):
        result = validate_entries(_manifest(_entry(target=True)))
        self.assertIn(ENTRY_TYPE_INVALID, _codes(result))

    def test_invalid_id(self):
        result = validate_entries(_manifest(_entry(id="Core Governance!")))
        self.assertIn(ENTRY_ID_INVALID, _codes(result))

    def test_empty_path_and_target(self):
        result = validate_entries(_manifest(_entry(path="   ", target="")))
        self.assertEqual(_codes(result).count(ENTRY_SCHEMA_INVALID), 2)

    def test_duplicate_id(self):
        result = validate_entries(_manifest(_entry(), _entry(path="a.md")))
        self.assertIn(ENTRY_DUPLICATE_ID, _codes(result))
        self.assertTrue(result.inventory[0].accepted)
        self.assertFalse(result.inventory[1].accepted)

    def test_unsupported_entry_version(self):
        result = validate_entries(_manifest(_entry(entry_version="9.9")))
        self.assertIn(ENTRY_VERSION_UNSUPPORTED, _codes(result))

    def test_non_object_entry(self):
        result = validate_entries(_manifest("not-an-entry"))
        self.assertIn(ENTRY_TYPE_INVALID, _codes(result))

    def test_malformed_manifest(self):
        result = validate_entries({"package": "gwc"})
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertIn(ENTRY_SCHEMA_INVALID, _codes(result))
        self.assertEqual(result.inventory, [])


class DeterminismTest(unittest.TestCase):
    def test_same_input_same_digest_and_order(self):
        manifest = _manifest(_entry(), _entry(id="x", required="no", boom=1))
        first = validate_entries(manifest, source_sha=SOURCE_SHA)
        second = validate_entries(json.loads(json.dumps(manifest)), source_sha=SOURCE_SHA)
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.semantic_digest(), second.semantic_digest())

    def test_errors_are_ordered_canonically(self):
        manifest = _manifest(_entry(id="zeta", required=1), _entry(id="alpha", nope=1))
        result = validate_entries(manifest)
        keys = [(e.entry_id, e.entry_index, e.json_path, e.reason_code) for e in result.errors]
        self.assertEqual(keys, sorted(keys))

    def test_manifest_digest_changes_with_content(self):
        a = validate_entries(_manifest(_entry()))
        b = validate_entries(_manifest(_entry(id="other")))
        self.assertNotEqual(a.manifest_digest, b.manifest_digest)

    def test_schema_digest_is_stable_across_calls(self):
        a = validate_entries(_manifest(_entry()))
        b = validate_entries(_manifest(_entry(id="other")))
        self.assertEqual(a.schema_digest, b.schema_digest)


class PurityTest(unittest.TestCase):
    def test_no_filesystem_access(self):
        import builtins

        calls = []
        real_open = builtins.open

        def spy(*args, **kwargs):
            calls.append(args[0] if args else None)
            return real_open(*args, **kwargs)

        builtins.open = spy
        try:
            validate_entries(_manifest(_entry(path="/etc/passwd", target="../escape")))
        finally:
            builtins.open = real_open
        self.assertEqual(calls, [])

    def test_path_safety_is_not_this_nodes_job(self):
        # Traversal / absolute paths are SCRUM-231/232 concerns; schema stays PASS.
        result = validate_entries(_manifest(_entry(path="../../etc/passwd", target="..\\x")))
        self.assertEqual(result.outcome, Outcome.PASS)


class ResultSchemaConformanceTest(unittest.TestCase):
    def test_result_matches_closed_schema_fields(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        payload = validate_entries(_manifest(_entry()), source_sha=SOURCE_SHA).to_dict()
        self.assertEqual(
            sorted(payload.keys()), sorted(schema["required"])
        )
        self.assertFalse(schema["additionalProperties"])
        for key in payload:
            self.assertIn(key, schema["properties"])
        self.assertEqual(payload["schema_id"], schema["properties"]["schema_id"]["const"])
        self.assertFalse(payload["authority_granted"])

    def test_error_reason_codes_are_in_closed_enum(self):
        enum = set(schema_reason_codes())
        result = validate_entries(_manifest(_entry(id="BAD ID", required=1, extra=2)))
        for err in result.errors:
            self.assertIn(err.reason_code, enum)


def schema_reason_codes():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return schema["definitions"]["reasonCode"]["enum"]


if __name__ == "__main__":
    unittest.main()
