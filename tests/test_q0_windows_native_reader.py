"""Native Windows regression suite for handle-relative artifact reads.

Run on an actual Windows host; mocked capability tests are not sufficient.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import _windows_safe_read as safe
from scripts import scrum781_q0_replay_fixture as fixture


@unittest.skipUnless(os.name == "nt", "requires native Windows filesystem")
class TestWindowsNativeRaceSafeReader(unittest.TestCase):
    def setUp(self):
        if not safe.available():
            self.fail("Windows native backend is unavailable")
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        (self.root / "tests").mkdir()

    def test_native_artifact_and_cli_read(self):
        file = self.root / "tests" / "input.json"
        raw = b'{"n":1}'
        file.write_bytes(raw)
        ref = {"path": "tests/input.json", "sha256": hashlib.sha256(raw).hexdigest()}
        self.assertEqual(raw, fixture._read_artifact(ref, self.root))
        self.assertEqual({"n": 1}, fixture._read_cli_json(str(file)))

    def test_digest_mismatch_does_not_succeed(self):
        file = self.root / "tests" / "input.json"
        file.write_bytes(b"{}")
        ref = {"path": "tests/input.json", "sha256": "0" * 64}
        with self.assertRaisesRegex(fixture.ReplayFixtureError, "ARTIFACT_DIGEST_MISMATCH"):
            fixture._read_artifact(ref, self.root)

    def test_oversized_file_rejected(self):
        file = self.root / "tests" / "input.json"
        with file.open("wb") as handle:
            handle.truncate(fixture.MAX_BYTES + 1)
        ref = {"path": "tests/input.json", "sha256": "0" * 64}
        with self.assertRaisesRegex(fixture.ReplayFixtureError, "ARTIFACT_NOT_BOUNDED_FILE"):
            fixture._read_artifact(ref, self.root)
        with self.assertRaisesRegex(fixture.ReplayFixtureError, "CLI_INPUT_NOT_BOUNDED_FILE"):
            fixture._read_cli_json(str(file))

    def test_missing_file_rejected(self):
        ref = {"path": "tests/input.json", "sha256": hashlib.sha256(b"{}").hexdigest()}
        with self.assertRaisesRegex(fixture.ReplayFixtureError, "ARTIFACT_UNREADABLE"):
            fixture._read_artifact(ref, self.root)

    def test_reparse_parent_symlink_rejected(self):
        (self.root / "outside").mkdir()
        (self.root / "outside" / "input.json").write_bytes(b"{}")
        link = self.root / "tests" / "linked"
        try:
            link.symlink_to(self.root / "outside", target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink privilege unavailable: {exc}")
        ref = {"path": "tests/linked/input.json", "sha256": hashlib.sha256(b"{}").hexdigest()}
        with self.assertRaisesRegex(fixture.ReplayFixtureError, "ARTIFACT_UNREADABLE"):
            fixture._read_artifact(ref, self.root)

    def test_reparse_final_symlink_rejected(self):
        target = self.root / "tests" / "target.json"
        target.write_bytes(b"{}")
        link = self.root / "tests" / "input.json"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink privilege unavailable: {exc}")
        ref = {"path": "tests/input.json", "sha256": hashlib.sha256(b"{}").hexdigest()}
        with self.assertRaisesRegex(fixture.ReplayFixtureError, "ARTIFACT_UNREADABLE"):
            fixture._read_artifact(ref, self.root)

    def test_unsupported_unc_and_device_namespace_fail_closed(self):
        for name in (r"\\server\share\input.json", r"\\?\C:\input.json"):
            with self.subTest(name=name):
                with self.assertRaises(safe.WindowsSafeReadUnavailable):
                    safe.read_bounded(name, fixture.MAX_BYTES)


class TestWindowsNativeRouting(unittest.TestCase):
    def test_native_backend_not_used_when_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            file = root / "tests" / "input.json"
            file.write_bytes(b"{}")
            with mock.patch.object(fixture.os, "supports_dir_fd", set()), \
                    mock.patch.object(fixture, "_windows_native_available", return_value=False):
                with self.assertRaisesRegex(fixture.ReplayFixtureError, "RACE_SAFE_READ_UNAVAILABLE"):
                    fixture._read_artifact(
                        {"path": "tests/input.json", "sha256": hashlib.sha256(b"{}").hexdigest()}, root)
                with self.assertRaisesRegex(fixture.ReplayFixtureError, "RACE_SAFE_READ_UNAVAILABLE"):
                    fixture._read_cli_json(str(file))


if __name__ == "__main__":
    unittest.main()
