#!/usr/bin/env python3
"""Validate repository text files are UTF-8 without BOM and use LF endings."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

BINARY_EXTENSIONS = {
    ".7z", ".avi", ".bin", ".db", ".gif", ".gz", ".ico", ".jar",
    ".jpeg", ".jpg", ".mov", ".mp3", ".mp4", ".otf", ".pdf", ".png",
    ".sqlite", ".sqlite3", ".tgz", ".ttf", ".war", ".webp", ".woff",
    ".woff2", ".zip",
}

SKIP_DIRS = {".git", ".mypy_cache", ".pytest_cache", "__pycache__", "node_modules"}
UTF8_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class Violation:
    path: str
    reason: str
    line: int = 0
    detail: str | None = None


def run_git(root: Path, args: Sequence[str], *, stdin: bytes | None = None) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace").strip())
    return completed.stdout


def is_git_repository(root: Path) -> bool:
    try:
        return run_git(root, ["rev-parse", "--is-inside-work-tree"]).strip() == b"true"
    except (OSError, RuntimeError):
        return False


def tracked_paths(root: Path) -> list[str]:
    raw = run_git(root, ["ls-files", "-z"])
    return [item.decode("utf-8", errors="strict") for item in raw.split(b"\0") if item]


def recursive_paths(root: Path) -> list[str]:
    result: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        result.append(relative.as_posix())
    return sorted(result)


def git_attributes(root: Path, paths: Sequence[str]) -> dict[str, dict[str, str]]:
    if not paths:
        return {}
    payload = b"".join(path.encode("utf-8") + b"\0" for path in paths)
    raw = run_git(root, ["check-attr", "-z", "--stdin", "text", "eol", "binary", "diff"], stdin=payload)
    fields = raw.split(b"\0")
    attrs: dict[str, dict[str, str]] = {}
    for index in range(0, len(fields) - 2, 3):
        path_raw, attr_raw, value_raw = fields[index : index + 3]
        if not path_raw:
            continue
        path = path_raw.decode("utf-8", errors="strict")
        attr = attr_raw.decode("utf-8", errors="strict")
        value = value_raw.decode("utf-8", errors="strict")
        attrs.setdefault(path, {})[attr] = value
    return attrs


def looks_binary(path: Path, data: bytes, attrs: dict[str, str] | None) -> bool:
    if attrs:
        if attrs.get("text") == "unset":
            return True
        if attrs.get("binary") == "set":
            return True
        if attrs.get("diff") == "unset" and attrs.get("text") != "set":
            return True
        if attrs.get("text") in {"set", "auto"}:
            return False
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    return b"\0" in data[:8192]


def first_line_for_offset(data: bytes, offset: int) -> int:
    return data.count(b"\n", 0, offset) + 1


def validate_control_files(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    attributes = root / ".gitattributes"
    editorconfig = root / ".editorconfig"

    if not attributes.is_file():
        violations.append(Violation(".gitattributes", "LINE_ENDING_POLICY_MISSING"))
    else:
        text = attributes.read_text(encoding="utf-8", errors="replace")
        if "* text=auto eol=lf" not in text:
            violations.append(
                Violation(".gitattributes", "GIT_ATTRIBUTES_INCOMPLETE", detail="missing '* text=auto eol=lf'")
            )

    if not editorconfig.is_file():
        violations.append(Violation(".editorconfig", "EDITORCONFIG_MISSING"))
    else:
        text = editorconfig.read_text(encoding="utf-8", errors="replace")
        required = ("charset = utf-8", "end_of_line = lf", "insert_final_newline = true")
        missing = [entry for entry in required if entry not in text]
        if missing:
            violations.append(
                Violation(".editorconfig", "EDITORCONFIG_INCOMPLETE", detail=", ".join(missing))
            )
    return violations


def validate_file(root: Path, relative: str, attrs: dict[str, str] | None) -> list[Violation]:
    path = root / relative
    if not path.is_file():
        return []
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [Violation(relative, "IO_ERROR", detail=str(exc))]

    if looks_binary(path, data, attrs):
        return []

    violations: list[Violation] = []

    if attrs and attrs.get("text") in {"set", "auto"} and attrs.get("eol") not in {"lf", "unspecified"}:
        violations.append(
            Violation(relative, "ATTRIBUTE_CLASSIFICATION_MISMATCH", detail=f"eol={attrs.get('eol')}")
        )

    if data.startswith(UTF8_BOM):
        violations.append(Violation(relative, "UTF8_BOM_DETECTED", line=1))

    crlf_at = data.find(b"\r\n")
    if crlf_at >= 0:
        violations.append(Violation(relative, "CRLF_DETECTED", line=first_line_for_offset(data, crlf_at)))

    bare_cr_at = -1
    search_from = 0
    while True:
        candidate = data.find(b"\r", search_from)
        if candidate < 0:
            break
        if candidate + 1 >= len(data) or data[candidate + 1 : candidate + 2] != b"\n":
            bare_cr_at = candidate
            break
        search_from = candidate + 2
    if bare_cr_at >= 0:
        violations.append(Violation(relative, "BARE_CR_DETECTED", line=first_line_for_offset(data, bare_cr_at)))

    try:
        data.decode("utf-8-sig" if data.startswith(UTF8_BOM) else "utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        violations.append(Violation(relative, "INVALID_UTF8", line=0, detail=str(exc)))

    if data and not data.endswith(b"\n"):
        violations.append(Violation(relative, "FINAL_NEWLINE_MISSING", line=data.count(b"\n") + 1))

    return violations


def validate(root: Path, *, force_recursive: bool = False) -> tuple[list[Violation], int, str]:
    root = root.resolve()
    violations = validate_control_files(root)
    mode = "recursive"
    attrs_by_path: dict[str, dict[str, str]] = {}

    if not force_recursive and is_git_repository(root):
        mode = "git-tracked"
        paths = tracked_paths(root)
        attrs_by_path = git_attributes(root, paths)
    else:
        paths = recursive_paths(root)

    for relative in paths:
        violations.extend(validate_file(root, relative, attrs_by_path.get(relative)))

    return violations, len(paths), mode


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--recursive", action="store_true", help="scan files recursively instead of using Git tracked paths")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        violations, files_checked, mode = validate(args.root, force_recursive=args.recursive)
    except (OSError, RuntimeError, UnicodeError) as exc:
        payload = {
            "status": "ERROR",
            "files_checked": 0,
            "mode": "unavailable",
            "violations": [{"path": "", "reason": "VALIDATOR_ERROR", "line": 0, "detail": str(exc)}],
        }
        print(json.dumps(payload, indent=2, sort_keys=True) if args.as_json else f"ERROR: {exc}")
        return 2

    payload = {
        "status": "PASS" if not violations else "FAIL",
        "files_checked": files_checked,
        "mode": mode,
        "violations": [asdict(item) for item in violations],
    }
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{payload['status']}: checked {files_checked} files using {mode}")
        for violation in violations:
            location = f":{violation.line}" if violation.line else ""
            detail = f" ({violation.detail})" if violation.detail else ""
            print(f"- {violation.path}{location}: {violation.reason}{detail}")
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
