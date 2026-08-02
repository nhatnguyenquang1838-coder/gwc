#!/usr/bin/env python3
"""Validate tracked text files are UTF-8 without BOM and use LF endings."""

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


def git(root: Path, args: Sequence[str], *, stdin: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], input=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def is_git_repo(root: Path) -> bool:
    try:
        return git(root, ["rev-parse", "--is-inside-work-tree"]).strip() == b"true"
    except (OSError, RuntimeError):
        return False


def candidate_paths(root: Path, recursive: bool) -> list[str]:
    if not recursive and is_git_repo(root):
        return [
            item.decode("utf-8", errors="strict")
            for item in git(root, ["ls-files", "-z"]).split(b"\0")
            if item
        ]
    paths: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        paths.append(relative.as_posix())
    return sorted(paths)


def attributes(root: Path, paths: Sequence[str]) -> dict[str, dict[str, str]]:
    if not paths or not is_git_repo(root):
        return {}
    payload = b"".join(path.encode("utf-8") + b"\0" for path in paths)
    raw = git(root, ["check-attr", "-z", "--stdin", "text", "eol", "binary", "diff"], stdin=payload)
    fields = raw.split(b"\0")
    result: dict[str, dict[str, str]] = {}
    for index in range(0, len(fields) - 2, 3):
        path_raw, attr_raw, value_raw = fields[index:index + 3]
        if path_raw:
            path = path_raw.decode("utf-8")
            result.setdefault(path, {})[attr_raw.decode("utf-8")] = value_raw.decode("utf-8")
    return result


def is_binary(path: Path, data: bytes, attrs: dict[str, str] | None) -> bool:
    if attrs:
        if attrs.get("text") == "unset" or attrs.get("binary") == "set":
            return True
        if attrs.get("diff") == "unset" and attrs.get("text") != "set":
            return True
        if attrs.get("text") in {"set", "auto"}:
            return False
    return path.suffix.lower() in BINARY_EXTENSIONS or b"\0" in data[:8192]


def line_for(data: bytes, offset: int) -> int:
    return data.count(b"\n", 0, offset) + 1


def validate_controls(root: Path) -> list[Violation]:
    failures: list[Violation] = []
    attrs = root / ".gitattributes"
    editor = root / ".editorconfig"
    if not attrs.is_file():
        failures.append(Violation(".gitattributes", "LINE_ENDING_POLICY_MISSING"))
    elif "* text=auto eol=lf" not in attrs.read_text(encoding="utf-8", errors="replace"):
        failures.append(Violation(".gitattributes", "GIT_ATTRIBUTES_INCOMPLETE"))
    if not editor.is_file():
        failures.append(Violation(".editorconfig", "EDITORCONFIG_MISSING"))
    else:
        text = editor.read_text(encoding="utf-8", errors="replace")
        required = ("charset = utf-8", "end_of_line = lf", "insert_final_newline = true")
        missing = [item for item in required if item not in text]
        if missing:
            failures.append(Violation(".editorconfig", "EDITORCONFIG_INCOMPLETE", detail=", ".join(missing)))
    return failures


def validate_file(
    root: Path,
    relative: str,
    attrs: dict[str, str] | None,
    *,
    require_final_newline: bool = False,
) -> list[Violation]:
    path = root / relative
    if not path.is_file():
        return []
    data = path.read_bytes()
    if is_binary(path, data, attrs):
        return []

    failures: list[Violation] = []
    if attrs and attrs.get("text") in {"set", "auto"} and attrs.get("eol") not in {"lf", "unspecified"}:
        failures.append(Violation(relative, "ATTRIBUTE_CLASSIFICATION_MISMATCH", detail=f"eol={attrs.get('eol')}"))
    if data.startswith(UTF8_BOM):
        failures.append(Violation(relative, "UTF8_BOM_DETECTED", line=1))
    crlf = data.find(b"\r\n")
    if crlf >= 0:
        failures.append(Violation(relative, "CRLF_DETECTED", line=line_for(data, crlf)))
    for offset, value in enumerate(data):
        if value == 13 and (offset + 1 >= len(data) or data[offset + 1] != 10):
            failures.append(Violation(relative, "BARE_CR_DETECTED", line=line_for(data, offset)))
            break
    try:
        data.decode("utf-8-sig" if data.startswith(UTF8_BOM) else "utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        failures.append(Violation(relative, "INVALID_UTF8", detail=str(exc)))
    if require_final_newline and data and not data.endswith(b"\n"):
        failures.append(Violation(relative, "FINAL_NEWLINE_MISSING", line=data.count(b"\n") + 1))
    return failures


def validate(
    root: Path,
    *,
    force_recursive: bool = False,
    require_final_newline: bool = False,
) -> tuple[list[Violation], int, str]:
    root = root.resolve()
    paths = candidate_paths(root, force_recursive)
    attr_map = attributes(root, paths)
    failures = validate_controls(root)
    for relative in paths:
        failures.extend(
            validate_file(
                root, relative, attr_map.get(relative),
                require_final_newline=require_final_newline,
            )
        )
    mode = "recursive" if force_recursive or not is_git_repo(root) else "git-tracked"
    return failures, len(paths), mode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--require-final-newline", action="store_true")
    args = parser.parse_args(argv or sys.argv[1:])
    try:
        failures, checked, mode = validate(
            args.root,
            force_recursive=args.recursive,
            require_final_newline=args.require_final_newline,
        )
        payload = {
            "status": "PASS" if not failures else "FAIL",
            "files_checked": checked,
            "mode": mode,
            "violations": [asdict(item) for item in failures],
        }
        print(json.dumps(payload, indent=2, sort_keys=True) if args.as_json else f"{payload['status']}: checked {checked} files using {mode}")
        return 0 if not failures else 1
    except (OSError, RuntimeError, UnicodeError) as exc:
        payload = {
            "status": "ERROR", "files_checked": 0, "mode": "unavailable",
            "violations": [{"path": "", "reason": "VALIDATOR_ERROR", "line": 0, "detail": str(exc)}],
        }
        print(json.dumps(payload, indent=2, sort_keys=True) if args.as_json else f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
