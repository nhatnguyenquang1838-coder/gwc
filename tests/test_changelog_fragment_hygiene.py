from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tools.validate_changelog_fragments import main


VALID_FRAGMENT = """## 2026-07-21 — REVAMP-GWC-009 runtime kernel schemas

### Added

- Runtime kernel schema evidence for REVAMP-GWC-009.

### Safety

- This fragment grants no merge, deploy, release, production configuration, credential, migration, or production-data authority.
"""


class ChangelogFragmentHygieneTests(unittest.TestCase):
    def _write_fragment(self, root: Path, name: str, content: str) -> Path:
        directory = root / "releases" / "changelog.d"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_valid_fragment_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_fragment(root, "2026-07-21-revamp-gwc-009-runtime-kernel.md", VALID_FRAGMENT)
            self.assertEqual(main(["--root", str(root)]), 0)

    def test_missing_task_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = self._write_fragment(
                root,
                "2026-07-21-missing-task.md",
                "## 2026-07-21 — missing task\n\n### Added\n\n- Missing task marker.\n",
            )
            try:
                self.assertEqual(main(["--root", str(root)]), 1)
            finally:
                # Explicit cleanup so a leaked temp dir can never leave a
                # stray invalid fragment in a reused CI workspace.
                path.unlink(missing_ok=True)

    def test_missing_fragment_directory_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(main(["--root", temp_dir]), 1)


if __name__ == "__main__":
    unittest.main()
