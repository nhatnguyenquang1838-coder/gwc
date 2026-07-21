from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "projects/gwc/package.yaml"
CHANGELOG = ROOT / "releases/changelog.md"


class GwcPackageReleaseNoteHygieneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = yaml.safe_load(PACKAGE.read_text(encoding="utf-8"))
        cls.changelog = CHANGELOG.read_text(encoding="utf-8")

    def test_package_version_remains_runtime_bootstrap_version(self) -> None:
        self.assertEqual(self.package["package_version"], "1.16.0")

    def test_package_notes_do_not_duplicate_current_package_version(self) -> None:
        notes = self.package.get("notes", [])
        current_version_notes = [
            note for note in notes
            if isinstance(note, str) and note.startswith("Package version 1.16.0")
        ]
        self.assertEqual(current_version_notes, [
            "Package version 1.16.0 adds runtime bootstrap evidence to G0/G1 and fail-closed selected runtime profile resolution for the current agent execution mode."
        ])

    def test_consumer_export_note_is_rollout_not_package_bump(self) -> None:
        notes = "\n".join(str(note) for note in self.package.get("notes", []))
        self.assertIn("REVAMP-GWC-006 adds consumer package export", notes)
        self.assertIn("without changing package_version", notes)
        self.assertNotIn("Package version 1.17.0", notes)

    def test_changelog_backfills_consumer_export_scope(self) -> None:
        self.assertIn("REVAMP-GWC-006 consumer package export", self.changelog)
        self.assertIn("Package export manifest schema", self.changelog)
        self.assertIn('keeps `package_version: "1.16.0"`', self.changelog)
        self.assertIn("PR #58 metadata was corrected", self.changelog)


if __name__ == "__main__":
    unittest.main()
