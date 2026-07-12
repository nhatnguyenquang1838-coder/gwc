#!/usr/bin/env python3
"""Compare two built instruction package directories."""

from __future__ import annotations

import argparse
import difflib
import hashlib
from pathlib import Path
import sys


TEXT_SUFFIXES = {
    ".md", ".txt", ".yaml", ".yml", ".json", ".py", ".toml",
    ".ini", ".cfg", ".sh", ".ps1"
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("old_package")
    parser.add_argument("new_package")
    parser.add_argument("--show-content", action="store_true")
    args = parser.parse_args()

    old_root = Path(args.old_package).resolve()
    new_root = Path(args.new_package).resolve()

    if not old_root.is_dir() or not new_root.is_dir():
        print("Both package paths must be directories.", file=sys.stderr)
        return 2

    old_files = files(old_root)
    new_files = files(new_root)
    all_paths = sorted(set(old_files) | set(new_files))

    added, removed, changed, unchanged = [], [], [], []
    for rel in all_paths:
        if rel not in old_files:
            added.append(rel)
        elif rel not in new_files:
            removed.append(rel)
        elif sha256(old_files[rel]) != sha256(new_files[rel]):
            changed.append(rel)
        else:
            unchanged.append(rel)

    print("PACKAGE DIFF")
    print(f"Old: {old_root}")
    print(f"New: {new_root}")
    print(f"Added: {len(added)}")
    print(f"Removed: {len(removed)}")
    print(f"Changed: {len(changed)}")
    print(f"Unchanged: {len(unchanged)}")

    for label, values in [
        ("ADDED", added), ("REMOVED", removed), ("CHANGED", changed)
    ]:
        if values:
            print(f"\n{label}")
            for rel in values:
                print(f"- {rel}")

    if args.show_content:
        for rel in changed:
            old_path = old_files[rel]
            new_path = new_files[rel]
            if old_path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                old_text = old_path.read_text(encoding="utf-8").splitlines(True)
                new_text = new_path.read_text(encoding="utf-8").splitlines(True)
            except UnicodeDecodeError:
                continue
            print()
            sys.stdout.writelines(difflib.unified_diff(
                old_text,
                new_text,
                fromfile=f"old/{rel}",
                tofile=f"new/{rel}",
            ))

    return 1 if added or removed or changed else 0


if __name__ == "__main__":
    sys.exit(main())
