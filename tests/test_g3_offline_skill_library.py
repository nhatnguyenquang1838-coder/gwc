from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "libs" / "g3-skill-library" / "manifest.yaml"


class G3OfflineSkillLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    def test_context7_is_first_and_fallback_is_atomic(self) -> None:
        self.assertEqual("/obra/superpowers", self.manifest["context7"]["library_id"])
        self.assertTrue(self.manifest["context7"]["query_first"])
        self.assertEqual("bundle-atomic", self.manifest["fallback_policy"]["mode"])
        self.assertTrue(self.manifest["fallback_policy"]["prohibit_mixed_sources"])
        self.assertTrue(self.manifest["fallback_policy"]["verify_sha256"])

    def test_required_skill_bundle_is_complete(self) -> None:
        entries = {item["id"]: item for item in self.manifest["skills"]}
        for skill_id in self.manifest["context7"]["required_skill_ids"]:
            self.assertIn(skill_id, entries)
            self.assertTrue(entries[skill_id]["required"])

    def test_every_offline_file_matches_manifest_hash(self) -> None:
        for item in self.manifest["skills"]:
            path = ROOT / item["path"]
            self.assertTrue(path.is_file(), item["path"])
            actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(item["sha256"], actual, item["path"])

    def test_later_gate_actions_remain_prohibited(self) -> None:
        prohibited = set(self.manifest["authority"]["prohibited_actions"])
        for action in ("merge", "auto_merge", "deploy", "production_configuration", "credential_operation", "migration", "production_data"):
            self.assertIn(action, prohibited)


if __name__ == "__main__":
    unittest.main()
