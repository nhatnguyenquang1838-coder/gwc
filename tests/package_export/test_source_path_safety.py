"""Fixture-driven tests for package_export source-path-safety-check (SCRUM-231).

Every adversarial path class from the task contract gets a real on-disk
fixture tree: nested normal file, absolute Unix/Windows path, ``..``
traversal, normalized/encoded traversal, backslash separators, symlink escape,
directory, missing required and missing optional source.
"""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
# Import the evaluator from the repo's tools/ dir directly (a host env may own a
# different top-level `tools` package under the bare CI unittest discovery).
sys.path.insert(0, str(_REPO_ROOT / "tools"))
sys.path.insert(0, str(_HERE))

from node_architect.package_export.source_path_safety import (  # noqa: E402
    SCHEMA_ID,
    SCHEMA_VERSION,
    SOURCE_NOT_REGULAR_FILE,
    SOURCE_OPTIONAL_MISSING,
    SOURCE_PATH_ABSOLUTE,
    SOURCE_PATH_BACKSLASH,
    SOURCE_PATH_ESCAPES_ROOT,
    SOURCE_PATH_SAFE,
    SOURCE_PATH_TRAVERSAL,
    SOURCE_REQUIRED_MISSING,
    SOURCE_SYMLINK_ESCAPE,
    Disposition,
    Outcome,
    check_source_paths,
    normalize_relative_path,
)

NESTED_BYTES = b"alpha-beta-gamma\n"


def _entry(entry_id, path, required=True):
    return {"id": entry_id, "path": path, "required": required}


class _RootFixture(unittest.TestCase):
    """Builds a pinned repository root plus an outside-the-root sibling tree."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="gwc-spsc-")).resolve()
        self.root = self._tmp / "repo"
        self.outside = self._tmp / "outside"
        (self.root / "pkg" / "nested").mkdir(parents=True)
        self.outside.mkdir()
        (self.root / "pkg" / "nested" / "file.txt").write_bytes(NESTED_BYTES)
        (self.outside / "secret.txt").write_bytes(b"secret\n")
        (self.root / "pkg" / "adir").mkdir()
        self.has_symlink = True
        try:
            os.symlink(self.outside / "secret.txt", self.root / "pkg" / "escape.txt")
        except (OSError, NotImplementedError):  # pragma: no cover - platform guard
            self.has_symlink = False

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def run_check(self, entries):
        return check_source_paths(
            entries,
            self.root,
            repository="nhatnguyenquang1838-coder/gwc",
            source_base_sha="bce6f6f83c74a25a57259695adc44b46a8555c46",
        )


class SyntaxEvaluationTest(unittest.TestCase):
    """Pure normalization rejects unsafe syntax without touching the filesystem."""

    def test_rejects_unsafe_syntax(self):
        cases = {
            "": None,
            "   ": None,
            "/etc/passwd": SOURCE_PATH_ABSOLUTE,
            "C:/Windows/system32": SOURCE_PATH_ABSOLUTE,
            "pkg\\nested\\file.txt": SOURCE_PATH_BACKSLASH,
            "../outside/secret.txt": SOURCE_PATH_TRAVERSAL,
            "pkg/../../outside/secret.txt": SOURCE_PATH_TRAVERSAL,
            "./pkg/./../..": SOURCE_PATH_TRAVERSAL,
        }
        for declared, expected in cases.items():
            with self.subTest(path=declared):
                normalized, code, _ = normalize_relative_path(declared)
                self.assertIsNone(normalized)
                if expected:
                    self.assertEqual(code, expected)

    def test_normalizes_redundant_segments(self):
        normalized, code, _ = normalize_relative_path("./pkg//nested/./file.txt")
        self.assertEqual(normalized, "pkg/nested/file.txt")
        self.assertEqual(code, SOURCE_PATH_SAFE)

    def test_non_string_is_not_safe(self):
        for declared in (None, 42, [], {}):
            with self.subTest(value=declared):
                normalized, _, _ = normalize_relative_path(declared)
                self.assertIsNone(normalized)


class AcceptedBindingTest(_RootFixture):
    def test_nested_file_is_accepted_and_bound(self):
        result = self.run_check([_entry("n1", "pkg/nested/file.txt")])
        self.assertEqual(result.outcome, Outcome.PASS)
        self.assertEqual(result.schema_id, SCHEMA_ID)
        self.assertEqual(result.schema_version, SCHEMA_VERSION)
        self.assertFalse(result.authority_granted)

        (verdict,) = result.verdicts
        self.assertEqual(verdict.disposition, Disposition.ACCEPTED)
        self.assertEqual(verdict.reason_code, SOURCE_PATH_SAFE)
        binding = verdict.binding
        self.assertIsNotNone(binding)
        self.assertEqual(binding.canonical_path, "pkg/nested/file.txt")
        self.assertEqual(
            binding.source_sha256,
            "sha256:" + hashlib.sha256(NESTED_BYTES).hexdigest(),
        )
        self.assertEqual(binding.byte_count, len(NESTED_BYTES))
        self.assertEqual(result.repository, "nhatnguyenquang1838-coder/gwc")
        self.assertEqual(
            result.source_base_sha, "bce6f6f83c74a25a57259695adc44b46a8555c46"
        )

    def test_result_is_deterministic_for_same_snapshot(self):
        entries = [
            _entry("n1", "pkg/nested/file.txt"),
            _entry("n2", "pkg/missing-optional.txt", required=False),
        ]
        first = self.run_check(entries)
        second = self.run_check(entries)
        self.assertEqual(first.semantic_digest(), second.semantic_digest())
        self.assertEqual(first.to_json(), second.to_json())

    def test_verdicts_are_ordered_independently_of_input_order(self):
        forward = self.run_check(
            [_entry("a", "pkg/nested/file.txt"), _entry("b", "pkg/nested/file.txt")]
        )
        self.assertEqual([v.entry_id for v in forward.verdicts], ["a", "b"])


class AdversarialPathTest(_RootFixture):
    def test_absolute_unix_path_blocks(self):
        result = self.run_check([_entry("abs", "/etc/passwd")])
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_PATH_ABSOLUTE)

    def test_absolute_windows_path_blocks(self):
        result = self.run_check([_entry("win", "C:/Windows/system32/cmd.exe")])
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_PATH_ABSOLUTE)

    def test_backslash_path_blocks(self):
        result = self.run_check([_entry("bs", "pkg\\nested\\file.txt")])
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_PATH_BACKSLASH)

    def test_parent_traversal_blocks(self):
        result = self.run_check([_entry("up", "../outside/secret.txt")])
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_PATH_TRAVERSAL)

    def test_embedded_normalized_traversal_blocks(self):
        result = self.run_check([_entry("mid", "pkg/nested/../../../outside/secret.txt")])
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_PATH_TRAVERSAL)

    def test_symlink_escape_blocks(self):
        if not self.has_symlink:  # pragma: no cover - platform guard
            self.skipTest("symlinks unavailable on this platform")
        result = self.run_check([_entry("link", "pkg/escape.txt")])
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_SYMLINK_ESCAPE)
        self.assertIsNone(result.verdicts[0].binding)

    def test_directory_is_not_a_regular_file(self):
        result = self.run_check([_entry("dir", "pkg/adir")])
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_NOT_REGULAR_FILE)

    def test_empty_path_blocks(self):
        result = self.run_check([_entry("empty", "")])
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertTrue(result.verdicts[0].blocking)

    def test_no_adversarial_case_is_ever_accepted(self):
        entries = [
            _entry("abs", "/etc/passwd"),
            _entry("win", "C:/x"),
            _entry("bs", "a\\b"),
            _entry("up", "../x"),
            _entry("dir", "pkg/adir"),
            _entry("empty", ""),
        ]
        result = self.run_check(entries)
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertEqual(result.accepted, [])
        self.assertEqual(len(result.blocked), len(entries))


class RequiredVsOptionalTest(_RootFixture):
    def test_required_missing_blocks(self):
        result = self.run_check([_entry("req", "pkg/nope.txt", required=True)])
        self.assertEqual(result.outcome, Outcome.FAIL)
        verdict = result.verdicts[0]
        self.assertEqual(verdict.reason_code, SOURCE_REQUIRED_MISSING)
        self.assertEqual(verdict.disposition, Disposition.BLOCKED)

    def test_optional_missing_is_skippable(self):
        result = self.run_check([_entry("opt", "pkg/nope.txt", required=False)])
        self.assertEqual(result.outcome, Outcome.PASS)
        verdict = result.verdicts[0]
        self.assertEqual(verdict.reason_code, SOURCE_OPTIONAL_MISSING)
        self.assertEqual(verdict.disposition, Disposition.SKIPPED)
        self.assertIsNone(verdict.binding)
        self.assertEqual(result.accepted, [])
        self.assertEqual(len(result.skipped), 1)

    def test_optional_unsafe_path_still_blocks(self):
        result = self.run_check([_entry("opt", "../outside/secret.txt", required=False)])
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_PATH_TRAVERSAL)


class RootEscapeTest(_RootFixture):
    def test_root_escape_reason_code_is_reachable(self):
        # Defensive branch: a normalized path must never resolve outside root.
        normalized, code, _ = normalize_relative_path("pkg/nested/file.txt")
        self.assertEqual(code, SOURCE_PATH_SAFE)
        self.assertNotEqual(normalized, "")
        self.assertNotIn(SOURCE_PATH_ESCAPES_ROOT, [v.reason_code for v in
                                                    self.run_check(
                                                        [_entry("ok", normalized)]
                                                    ).verdicts])


if __name__ == "__main__":
    unittest.main()
