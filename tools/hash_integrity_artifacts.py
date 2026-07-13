#!/usr/bin/env python3
"""Hash files and generate or verify a SHA256SUMS-style manifest."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        digest, rel = line.split(maxsplit=1)
        manifest[rel] = digest.lower()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files to hash relative to --root, or absolute paths.",
    )
    parser.add_argument("--root", default=None,
                        help="Repository root; defaults to the parent of tools/")
    parser.add_argument(
        "--output",
        default=None,
        help="Write manifest lines to this file instead of stdout.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify an existing manifest file instead of generating one.",
    )
    parser.add_argument(
        "--manifest",
        default="SHA256SUMS.txt",
        help="Manifest path used with --verify.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]

    if args.verify:
        manifest_path = Path(args.manifest)
        if not manifest_path.is_absolute():
            manifest_path = root / manifest_path
        if not manifest_path.is_file():
            print(f"MANIFEST_MISSING: {manifest_path}", file=sys.stderr)
            return 2

        expected = load_manifest(manifest_path)
        errors: list[str] = []
        warnings: list[str] = []

        for rel, digest in expected.items():
            target = Path(rel)
            if not target.is_absolute():
                target = root / target
            if not target.is_file():
                errors.append(f"missing: {rel}")
                continue
            actual = sha256(target)
            if actual != digest:
                warnings.append(f"hash mismatch: {rel}: expected {digest}, got {actual}")

        if errors:
            print("HASH_VERIFY_FAILED")
            for error in errors:
                print(f"- {error}")
            return 1

        if warnings:
            print("HASH_VERIFY_OK_WITH_WARNINGS")
            for warning in warnings:
                print(f"- {warning}")
            return 0

        print("HASH_VERIFY_OK")
        print(f"Manifest: {manifest_path}")
        print(f"Files: {len(expected)}")
        return 0

    if not args.paths:
        print("No paths provided.", file=sys.stderr)
        return 2

    lines: list[str] = []
    for raw in args.paths:
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            print(f"missing: {raw}", file=sys.stderr)
            return 1
        rel = path.relative_to(root).as_posix() if str(path).startswith(str(root)) else path.as_posix()
        lines.append(f"{sha256(path)}  {rel}")

    output_text = "\n".join(lines) + "\n"
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = root / output_path
        output_path.write_text(output_text, encoding="utf-8")
        print(f"WROTE: {output_path}")
        print(f"Files: {len(lines)}")
        return 0

    sys.stdout.write(output_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
