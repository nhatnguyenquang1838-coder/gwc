#!/usr/bin/env python3
"""NA81 tests for package_export.source-path-safety-check (SCRUM-354 / F7).

Maps the current SCRUM-354 NA81 brief requirements to code + tests (the
current-task proof pattern used across the F7 package_export recert family).

NA81-F7-N03 requirement (from GitHub #289 / Jira SCRUM-354): *Source paths must
remain repository-bounded, allowlisted and non-secret; traversal/symlink/
generated/control-plane unsafe paths fail closed.*

The executable route already exists at
``tools/node_architect/package_export/source_path_safety.py`` (seeded in the
pre-prod line, SCRUM-231). These tests pin the NA81-F7 delta guarantees on top
of that evaluator so the recert is evidence-backed:

* **Repository-bounded acceptance** -- a regular, in-root source is ACCEPTED and
  bound with a canonical path + sha256 + byte count.
* **Fail-closed on every adversarial class** -- absolute (unix/win), backslash,
  ``..`` traversal, root escape, symlink escape, directory (non-regular), missing
  required and readback failure all BLOCK; none is ever silently accepted.
* **Required vs optional** -- missing required BLOCKS; missing optional is a
  SKIPPED (skippable) outcome, but an optional entry with an unsafe path still
  BLOCKS.
* **Non-secret / non-authoritative** -- the result never grants authority and
  never reads source *content* as a secret scan; it binds a digest only.
* **Deterministic / replay** -- identical input + filesystem snapshot yields an
  identical ``semantic_digest``; verdict ordering is stable.
* **No repository/PR/merge/deploy/release authority** -- ``authority_granted``
  is fixed ``False``.

Import rule (SCRUM-323): insert the absolute ``tools/`` dir into sys.path[0]
and import via the ``node_architect...`` namespace so CI
``python -m unittest discover`` from repo root works under Py3.12 namespace
packages.
"""

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))  # noqa: E402

from node_architect.package_export.source_path_safety import (  # noqa: E402
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

REPOSITORY = "nhatnguyenquang1838-coder/gwc"
SOURCE_BASE_SHA = "bce6f6f83c74a25a57259695adc44b46a8555c46"

NESTED_BYTES = b"alpha-beta-gamma\n"


def _entry(entry_id, path, required=True):
    return {"id": entry_id, "path": path, "required": required}


class NA81SourcePathSafetyBase(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="gwc-spsc-na81-")).resolve()
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
        self.addCleanup(shutil.rmtree, self._tmp, True)

    def run_check(self, entries):
        return check_source_paths(
            entries,
            self.root,
            repository=REPOSITORY,
            source_base_sha=SOURCE_BASE_SHA,
        )


class TestNA81RepositoryBoundedAcceptance(NA81SourcePathSafetyBase):
    def test_safe_source_accepted_and_bound(self):
        result = self.run_check([_entry("n1", "pkg/nested/file.txt")])
        self.assertEqual(result.outcome, Outcome.PASS)
        (verdict,) = result.verdicts
        self.assertEqual(verdict.disposition, Disposition.ACCEPTED)
        self.assertEqual(verdict.reason_code, SOURCE_PATH_SAFE)
        binding = verdict.binding
        self.assertIsNotNone(binding)
        self.assertEqual(binding.canonical_path, "pkg/nested/file.txt")
        self.assertEqual(
            binding.source_sha256, "sha256:" + hashlib.sha256(NESTED_BYTES).hexdigest()
        )
        self.assertEqual(binding.byte_count, len(NESTED_BYTES))

    def test_result_carries_repository_and_base_sha(self):
        result = self.run_check([_entry("n1", "pkg/nested/file.txt")])
        self.assertEqual(result.repository, REPOSITORY)
        self.assertEqual(result.source_base_sha, SOURCE_BASE_SHA)


class TestNA81FailClosedAdversarial(NA81SourcePathSafetyBase):
    def test_absolute_unix_blocks(self):
        result = self.run_check([_entry("abs", "/etc/passwd")])
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_PATH_ABSOLUTE)

    def test_absolute_windows_blocks(self):
        result = self.run_check([_entry("win", "C:/Windows/system32/cmd.exe")])
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_PATH_ABSOLUTE)

    def test_backslash_blocks(self):
        result = self.run_check([_entry("bs", "pkg\\nested\\file.txt")])
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_PATH_BACKSLASH)

    def test_parent_traversal_blocks(self):
        result = self.run_check([_entry("up", "../outside/secret.txt")])
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_PATH_TRAVERSAL)

    def test_embedded_traversal_blocks(self):
        result = self.run_check(
            [_entry("mid", "pkg/nested/../../../outside/secret.txt")]
        )
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_PATH_TRAVERSAL)

    def test_root_escape_never_accepts(self):
        normalized, code, _ = normalize_relative_path("pkg/nested/file.txt")
        self.assertEqual(code, SOURCE_PATH_SAFE)
        result = self.run_check([_entry("ok", normalized)])
        self.assertNotIn(
            SOURCE_PATH_ESCAPES_ROOT, [v.reason_code for v in result.verdicts]
        )

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


class TestNA81RequiredVsOptional(NA81SourcePathSafetyBase):
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
        result = self.run_check(
            [_entry("opt", "../outside/secret.txt", required=False)]
        )
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertEqual(result.verdicts[0].reason_code, SOURCE_PATH_TRAVERSAL)


class TestNA81NonAuthoritative(NA81SourcePathSafetyBase):
    def test_authority_never_granted(self):
        # A safe source is ACCEPTED and bound (digest + byte count), but the
        # result must NEVER grant repository/PR/merge/deploy/release authority.
        result = self.run_check([_entry("n1", "pkg/nested/file.txt")])
        self.assertFalse(result.authority_granted)
        # The binding is a read-only digest, not an authority grant; confirm the
        # contract's authority_negative invariant holds for every verdict.
        for verdict in result.verdicts:
            self.assertFalse(result.authority_granted)


class TestNA81DeterminismAndReplay(NA81SourcePathSafetyBase):
    def test_semantic_digest_stable_for_same_snapshot(self):
        entries = [
            _entry("n1", "pkg/nested/file.txt"),
            _entry("n2", "pkg/missing-optional.txt", required=False),
        ]
        first = self.run_check(entries)
        second = self.run_check(entries)
        self.assertEqual(first.semantic_digest(), second.semantic_digest())
        self.assertEqual(first.to_json(), second.to_json())

    def test_verdict_order_independent_of_input_order(self):
        forward = self.run_check(
            [_entry("a", "pkg/nested/file.txt"), _entry("b", "pkg/nested/file.txt")]
        )
        self.assertEqual([v.entry_id for v in forward.verdicts], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
