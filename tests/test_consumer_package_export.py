from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "export_project_package.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("export_project_package", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ConsumerPackageExportTests(unittest.TestCase):
    def test_export_copies_declared_entries_and_writes_manifest(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            out = Path(tmp) / "out"
            (root / "core").mkdir(parents=True)
            (root / "projects" / "gwc").mkdir(parents=True)
            (root / "core" / "rule.md").write_text("rule\n", encoding="utf-8")
            package = root / "projects" / "gwc" / "package.yaml"
            package.write_text(
                """
schema_version: "1.0"
project_id: gwc
package_version: "1.17.0"
status: active
profile: projects/gwc/project-profile.yaml
instructions:
  - id: sample-rule
    path: core/rule.md
    target: .governance/core/rule.md
    required: true
delivery:
  mode: git-pr
  target_repository: nhatnguyenquang1838-coder/gwc
  target_path: .governance
  default_branch: main
  identity_status: verified
  write_enabled: true
""".strip()
                + "\n",
                encoding="utf-8",
            )
            manifest = tool.export_package(
                repo_root=root,
                package_path=package,
                output_root=out,
                source_ref="main",
                source_base_sha="0" * 40,
                generated_at_utc="2026-07-22T00:00:00Z",
            )
            self.assertEqual(manifest["entries"][0]["status"], "copied")
            self.assertEqual((out / ".governance" / "core" / "rule.md").read_text(), "rule\n")
            manifest_file = json.loads((out / ".package-export-manifest.json").read_text())
            self.assertEqual(manifest_file["package_version"], "1.17.0")

    def test_export_rejects_unsafe_paths(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            out = Path(tmp) / "out"
            (root / "projects" / "gwc").mkdir(parents=True)
            package = root / "projects" / "gwc" / "package.yaml"
            package.write_text(
                """
schema_version: "1.0"
project_id: gwc
package_version: "1.17.0"
status: active
profile: projects/gwc/project-profile.yaml
instructions:
  - id: bad-rule
    path: ../secret.txt
    target: .governance/core/rule.md
    required: true
delivery:
  mode: git-pr
  target_repository: nhatnguyenquang1838-coder/gwc
  target_path: .governance
  default_branch: main
  identity_status: verified
  write_enabled: true
""".strip()
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                tool.export_package(
                    repo_root=root,
                    package_path=package,
                    output_root=out,
                    source_ref="main",
                    source_base_sha="0" * 40,
                    generated_at_utc="2026-07-22T00:00:00Z",
                )


if __name__ == "__main__":
    unittest.main()
