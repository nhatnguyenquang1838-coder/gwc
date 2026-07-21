#!/usr/bin/env python3
"""Validate GWC changelog fragments.

This validator exists for chat-connector-safe release note hygiene. It validates
small additive fragments under releases/changelog.d/ without rewriting the long
canonical releases/changelog.md file.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

FRAGMENT_DIR = Path("releases/changelog.d")
DATE_HEADING_RE = re.compile(r"^## \d{4}-\d{2}-\d{2} — .+", re.MULTILINE)
SECTION_RE = re.compile(r"^### .+", re.MULTILINE)
TASK_RE = re.compile(r"REVAMP-GWC-\d{3}")
FORBIDDEN_AUTHORITY = (
    "grants merge",
    "grants auto-merge",
    "grants deploy",
    "grants release",
    "grants production",
    "grants credential",
    "grants migration",
    "grants production-data",
)


def validate_fragment(path: Path, root: Path) -> list[str]:
    errors: list[str] = []
    relative_path = path.relative_to(root)
    if path.suffix != ".md":
        errors.append(f"{relative_path}: fragment must be a Markdown file")
        return errors
    if relative_path.parent != FRAGMENT_DIR:
        errors.append(f"{relative_path}: fragment must live directly under {FRAGMENT_DIR}")

    text = path.read_text(encoding="utf-8")
    headings = DATE_HEADING_RE.findall(text)
    if len(headings) != 1:
        errors.append(f"{relative_path}: expected exactly one dated '## YYYY-MM-DD — title' heading")
    if not SECTION_RE.search(text):
        errors.append(f"{relative_path}: expected at least one '###' section heading")
    if not TASK_RE.search(text):
        errors.append(f"{relative_path}: expected a REVAMP-GWC task id")
    lowered = text.lower()
    for phrase in FORBIDDEN_AUTHORITY:
        if phrase in lowered and f"no {phrase.removeprefix('grants ')}" not in lowered:
            errors.append(f"{relative_path}: forbidden authority claim: {phrase}")
    if not text.endswith("\n"):
        errors.append(f"{relative_path}: must end with a newline")
    return errors


def iter_fragments(root: Path) -> list[Path]:
    directory = root / FRAGMENT_DIR
    if not directory.exists():
        return []
    return sorted(path for path in directory.iterdir() if path.is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    errors: list[str] = []
    fragments = iter_fragments(root)
    if not fragments:
        errors.append(f"{FRAGMENT_DIR}: expected at least one changelog fragment")
    for fragment in fragments:
        errors.extend(validate_fragment(fragment, root))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(fragments)} changelog fragment(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
