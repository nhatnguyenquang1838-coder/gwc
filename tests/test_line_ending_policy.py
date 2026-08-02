from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "validate_line_endings.py"
SPEC = importlib.util.spec_from_file_location("validate_line_endings", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class LineEndingPolicyTests(unittest.TestCase):
    def make_root(self) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / ".gitattributes").write_text("* text=auto eol=lf\n*.png binary\n", encoding="utf-8", newline="\n")
        (root / ".editorconfig").write_text(
            "root = true\n\n[*]\ncharset = utf-8\nend_of_line = lf\ninsert_final_newline = true\n",
            encoding="utf-8",
            newline="\n",
        )
        return root

    def reasons(self, root: Path) -> set[str]:
        violations, _, _ = module.validate(root, force_recursive=True)
        return {item.reason for item in violations}

    def test_lf_utf8_file_passes(self) -> None:
        root = self.make_root()
        (root / "ok.md").write_bytes(b"alpha\nbeta\n")
        self.assertEqual(self.reasons(root), set())

    def test_crlf_is_rejected(self) -> None:
        root = self.make_root()
        (root / "bad.yaml").write_bytes(b"a: 1\r\nb: 2\r\n")
        self.assertIn("CRLF_DETECTED", self.reasons(root))

    def test_bare_cr_is_rejected(self) -> None:
        root = self.make_root()
        (root / "bad.txt").write_bytes(b"alpha\rbeta\n")
        self.assertIn("BARE_CR_DETECTED", self.reasons(root))

    def test_utf8_bom_is_rejected(self) -> None:
        root = self.make_root()
        (root / "bad.json").write_bytes(b"\xef\xbb\xbf{}\n")
        self.assertIn("UTF8_BOM_DETECTED", self.reasons(root))

    def test_invalid_utf8_is_rejected(self) -> None:
        root = self.make_root()
        (root / "bad.md").write_bytes(b"\xff\n")
        self.assertIn("INVALID_UTF8", self.reasons(root))

    def test_missing_final_newline_is_rejected(self) -> None:
        root = self.make_root()
        (root / "bad.py").write_bytes(b"print('x')")
        self.assertIn("FINAL_NEWLINE_MISSING", self.reasons(root))

    def test_binary_file_is_not_decoded(self) -> None:
        root = self.make_root()
        (root / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff")
        self.assertEqual(self.reasons(root), set())

    def test_missing_controls_are_rejected(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "a.md").write_text("ok\n", encoding="utf-8", newline="\n")
        reasons = self.reasons(root)
        self.assertIn("LINE_ENDING_POLICY_MISSING", reasons)
        self.assertIn("EDITORCONFIG_MISSING", reasons)


if __name__ == "__main__":
    unittest.main()
