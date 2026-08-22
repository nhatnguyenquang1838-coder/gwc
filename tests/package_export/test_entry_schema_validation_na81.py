#!/usr/bin/env python3
"""NA81 recert tests for package_export.entry-schema-validation (SCRUM-353, F7-N02).

Bound to the exact executable module
`tools/node_architect/package_export/entry_schema_validation.py`. These tests
prove the gate evaluator's fail-closed safety contract for the NA81 autonomous
lane recert: safe vs unsafe entries, schema validation pass/fail across the
closed reason-code taxonomy, normalization, dedupe, determinism, and that the
evaluator grants no authority and performs no filesystem side effects.

The module is a pure, deterministic, fail-closed schema gate: unknown fields are
rejected (never ignored), the typed EntrySchemaValidationResult (not an exit code)
is the sole PASS signal, and authority_granted is always False.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Import-path rule (Py3.12 namespace packages): prefix tools/ explicitly so the
# host env's bare top-level `tools` package can never shadow the repo module.
sys.path.insert(0, "/home/ubuntu/gwc-ctrl-r10/.wt/SCRUM-353/tools")

from node_architect.package_export.entry_schema_validation import (  # noqa: E402
    ENTRY_DUPLICATE_ID,
    ENTRY_ID_INVALID,
    ENTRY_REQUIRED_FIELD_MISSING,
    ENTRY_SCHEMA_INVALID,
    ENTRY_SCHEMA_VALID,
    ENTRY_TYPE_INVALID,
    ENTRY_UNKNOWN_FIELD,
    ENTRY_VERSION_UNSUPPORTED,
    Outcome,
    SCHEMA_VERSION,
    SUPPORTED_ENTRY_VERSIONS,
    validate_entries,
)


def _entry(**kw):
    base = {"id": "alpha", "path": ".governance/a.json", "target": "a", "required": True}
    base.update(kw)
    return base


class TestEntrySchemaValidationNA81(unittest.TestCase):
    # --- safe entries (PASS) ------------------------------------------------
    def test_minimal_valid_entry_passes(self):
        result = validate_entries({"entries": [_entry()]})
        self.assertEqual(result.outcome, Outcome.PASS)
        self.assertTrue(result.inventory[0].accepted)
        self.assertEqual(result.inventory[0].reason_code, ENTRY_SCHEMA_VALID)

    def test_valid_entry_with_all_optional_fields_passes(self):
        e = _entry(
            entry_version="0.1",
            description="a runtime check",
            category="runtime",
        )
        result = validate_entries({"entries": [e]})
        self.assertEqual(result.outcome, Outcome.PASS)
        self.assertEqual(len(result.errors), 0)

    def test_multiple_valid_entries_pass(self):
        manifest = {
            "entries": [
                _entry(id="a", path=".governance/a.json", target="a"),
                _entry(id="b", path=".governance/b.json", target="b"),
                _entry(id="c", path=".governance/c.json", target="c"),
            ]
        }
        result = validate_entries(manifest)
        self.assertEqual(result.outcome, Outcome.PASS)
        self.assertEqual(len(result.accepted_entry_ids), 3)

    # --- unknown / closed-schema fields -------------------------------------
    def test_unknown_field_rejected(self):
        e = _entry(unexpected_field="boom")
        result = validate_entries({"entries": [e]})
        self.assertEqual(result.outcome, Outcome.FAIL)
        codes = [err.reason_code for err in result.errors]
        self.assertIn(ENTRY_UNKNOWN_FIELD, codes)

    def test_multiple_unknown_fields_all_reported(self):
        e = _entry(secret="x", injected="y")
        result = validate_entries({"entries": [e]})
        unknown = [err for err in result.errors if err.reason_code == ENTRY_UNKNOWN_FIELD]
        self.assertEqual(len(unknown), 2)

    # --- missing required fields -------------------------------------------
    def test_missing_required_id_rejected(self):
        e = _entry()
        del e["id"]
        result = validate_entries({"entries": [e]})
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertIn(
            ENTRY_REQUIRED_FIELD_MISSING,
            [err.reason_code for err in result.errors],
        )

    def test_missing_required_path_rejected(self):
        e = _entry()
        del e["path"]
        result = validate_entries({"entries": [e]})
        self.assertIn(
            ENTRY_REQUIRED_FIELD_MISSING,
            [err.reason_code for err in result.errors],
        )

    def test_missing_required_target_rejected(self):
        e = _entry()
        del e["target"]
        result = validate_entries({"entries": [e]})
        self.assertIn(
            ENTRY_REQUIRED_FIELD_MISSING,
            [err.reason_code for err in result.errors],
        )

    def test_missing_required_flag_rejected(self):
        e = _entry()
        del e["required"]
        result = validate_entries({"entries": [e]})
        self.assertIn(
            ENTRY_REQUIRED_FIELD_MISSING,
            [err.reason_code for err in result.errors],
        )

    # --- type mismatches ---------------------------------------------------
    def test_required_flag_as_string_rejected(self):
        e = _entry(required="yes")
        result = validate_entries({"entries": [e]})
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertIn(ENTRY_TYPE_INVALID, [err.reason_code for err in result.errors])

    def test_id_as_non_string_rejected(self):
        e = _entry(id=123)
        result = validate_entries({"entries": [e]})
        self.assertIn(ENTRY_TYPE_INVALID, [err.reason_code for err in result.errors])

    def test_description_as_non_string_rejected(self):
        e = _entry(description=42)
        result = validate_entries({"entries": [e]})
        self.assertIn(ENTRY_TYPE_INVALID, [err.reason_code for err in result.errors])

    # --- invalid entry identifier ------------------------------------------
    def test_id_with_uppercase_and_space_invalid(self):
        e = _entry(id="Bad ID")
        result = validate_entries({"entries": [e]})
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertIn(ENTRY_ID_INVALID, [err.reason_code for err in result.errors])

    def test_id_leading_underscore_invalid(self):
        e = _entry(id="_bad")
        result = validate_entries({"entries": [e]})
        self.assertIn(ENTRY_ID_INVALID, [err.reason_code for err in result.errors])

    # --- unsupported entry version -----------------------------------------
    def test_unsupported_entry_version_rejected(self):
        e = _entry(entry_version="9.9")
        result = validate_entries({"entries": [e]})
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertIn(ENTRY_VERSION_UNSUPPORTED, [err.reason_code for err in result.errors])

    # --- empty path/target (schema invalid) -------------------------------
    def test_empty_path_rejected(self):
        e = _entry(path="")
        result = validate_entries({"entries": [e]})
        self.assertIn(ENTRY_SCHEMA_INVALID, [err.reason_code for err in result.errors])

    def test_empty_target_rejected(self):
        e = _entry(target="   ")
        result = validate_entries({"entries": [e]})
        self.assertIn(ENTRY_SCHEMA_INVALID, [err.reason_code for err in result.errors])

    # --- dedupe (duplicate id) --------------------------------------------
    def test_duplicate_id_detected(self):
        manifest = {
            "entries": [
                _entry(id="dup", path=".governance/a.json", target="a"),
                _entry(id="dup", path=".governance/b.json", target="b"),
            ]
        }
        result = validate_entries(manifest)
        self.assertEqual(result.outcome, Outcome.FAIL)
        dup = [err for err in result.errors if err.reason_code == ENTRY_DUPLICATE_ID]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0].entry_index, 1)

    def test_three_way_duplicate_produces_two_errors(self):
        e = _entry(id="dup", path=".governance/a.json", target="a")
        manifest = {"entries": [dict(e), dict(e), dict(e)]}
        result = validate_entries(manifest)
        dup = [err for err in result.errors if err.reason_code == ENTRY_DUPLICATE_ID]
        self.assertEqual(len(dup), 2)

    # --- manifest-level structural failure --------------------------------
    def test_manifest_without_entries_array_fails(self):
        result = validate_entries({"id": "x"})
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertTrue(
            any(err.reason_code == ENTRY_SCHEMA_INVALID for err in result.errors)
        )

    def test_non_object_manifest_fails(self):
        result = validate_entries(["not", "a", "manifest"])
        self.assertEqual(result.outcome, Outcome.FAIL)

    # --- normalization / determinism ---------------------------------------
    def test_repeated_evaluation_deterministic_digest(self):
        manifest = {"entries": [_entry(), _entry(id="b", path=".governance/b.json", target="b")]}
        a = validate_entries(manifest)
        b = validate_entries(manifest)
        self.assertEqual(a.to_json(), b.to_json())
        self.assertEqual(a.semantic_digest(), b.semantic_digest())

    def test_field_insertion_order_does_not_change_digest(self):
        e_shuffled = {"target": "a", "required": True, "id": "alpha", "path": ".governance/a.json"}
        a = validate_entries({"entries": [_entry()]})
        b = validate_entries({"entries": [e_shuffled]})
        self.assertEqual(a.manifest_digest, b.manifest_digest)
        self.assertEqual(a.semantic_digest(), b.semantic_digest())

    def test_schema_digest_stable_across_calls(self):
        a = validate_entries({"entries": [_entry()]})
        b = validate_entries({"entries": [_entry(id="z", path=".governance/z.json", target="z")]})
        self.assertEqual(a.schema_digest, b.schema_digest)
        self.assertEqual(SCHEMA_VERSION, SUPPORTED_ENTRY_VERSIONS[0])

    def test_inventory_count_equals_entry_count(self):
        manifest = {
            "entries": [
                _entry(id="a", path=".governance/a.json", target="a"),
                _entry(id="b", path=".governance/b.json", target="b", entry_version="9.9"),
            ]
        }
        result = validate_entries(manifest)
        self.assertEqual(len(result.inventory), len(manifest["entries"]))
        self.assertEqual([v.entry_index for v in result.inventory], [0, 1])

    def test_accepted_entry_ids_excludes_failed_entries(self):
        manifest = {
            "entries": [
                _entry(id="ok", path=".governance/a.json", target="a"),
                _entry(id="bad", entry_version="9.9"),
            ]
        }
        result = validate_entries(manifest)
        self.assertEqual(result.accepted_entry_ids, ["ok"])

    # --- no filesystem side effect -----------------------------------------
    def test_no_filesystem_side_effect(self):
        # Run the evaluator from a throwaway working directory and confirm it
        # neither creates nor removes any file there.
        manifest = {
            "entries": [
                _entry(id="a", path=".governance/a.json", target="a"),
                _entry(id="b", path=".governance/b.json", target="b"),
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                before = set(os.listdir("."))
                validate_entries(manifest)
                after = set(os.listdir("."))
            finally:
                os.chdir(cwd)
        self.assertEqual(before, after)

    # --- authority never granted ------------------------------------------
    def test_authority_never_granted(self):
        manifest = {
            "entries": [
                _entry(id="a", path=".governance/a.json", target="a"),
                _entry(id="bad", entry_version="9.9"),
            ]
        }
        result = validate_entries(manifest)
        self.assertFalse(result.authority_granted)

    def test_source_sha_passthrough(self):
        result = validate_entries({"entries": [_entry()]}, source_sha="sha256:abc")
        self.assertEqual(result.source_sha, "sha256:abc")


if __name__ == "__main__":
    unittest.main()
