from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "verify_package_export_smoke.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("verify_package_export_smoke", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PackageExportSmokeTests(unittest.TestCase):
    def test_real_gwc_package_exports_generated_governance_tree(self) -> None:
        tool = load_tool()
        with tempfile.TemporaryDirectory() as tmp:
            result = tool.validate_export(
                repo_root=ROOT,
                package_path=ROOT / "projects" / "gwc" / "package.yaml",
                output_root=Path(tmp) / "generated",
                source_ref="main",
                source_base_sha="0" * 40,
                generated_at_utc="2026-07-22T00:00:00Z",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["project_id"], "gwc")
        self.assertEqual(result["package_version"], "1.16.0")
        self.assertGreaterEqual(result["entries"], 70)
        self.assertGreater(result["copied_entries"], 0)
        self.assertIn(
            ".governance/tools/verify_package_export_smoke.py",
            result["required_generated_targets"],
        )
        self.assertIn(
            ".governance/docs/runbooks/PACKAGE_EXPORT_SMOKE_TEST.md",
            result["required_generated_targets"],
        )


if __name__ == "__main__":
    unittest.main()
