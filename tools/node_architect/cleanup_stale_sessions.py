#!/usr/bin/env python3
"""Plan or execute cleanup of stale temporary GWC session folders.

The tool is dry-run by default and never removes repository canonical evidence.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PRESERVE_NAMES = {
    ".git",
    ".gwc",
    "AGENTS.md",
    "REVAMP_G2_PREP_PACKET.md",
    "revamp-g2-envelope.json",
}

EVIDENCE_MARKERS = {
    "validation.log",
    "handoff.md",
    "checkpoint.json",
    "resume-token.json",
}


def parse_utc(value: str) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_manifest(path: Path) -> dict[str, Any]:
    manifest_path = path / ".gwc-session.json"
    if not manifest_path.exists():
        return {}
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"preserve": True, "status": "manifest_invalid"}
    return value if isinstance(value, dict) else {"preserve": True, "status": "manifest_invalid"}


def is_protected(path: Path) -> bool:
    parts = set(path.parts)
    if ".git" in parts:
        return True
    if ".gwc" in parts and "tasks" in parts:
        return True
    if path.name in PRESERVE_NAMES:
        return True
    if any((path / marker).exists() for marker in EVIDENCE_MARKERS):
        return True
    return False


def classify_session(path: Path, *, now: datetime, stale_after_hours: int) -> tuple[bool, str]:
    if is_protected(path):
        return False, "protected_or_evidence"
    manifest = load_manifest(path)
    if manifest.get("preserve") is True:
        return False, "manifest_preserve_true"
    if manifest.get("referenced_by_checkpoint") is True:
        return False, "referenced_by_checkpoint"
    if manifest.get("status") in {"blocked", "failed", "active"}:
        return False, "status_requires_preserve"

    last_used = parse_utc(str(manifest.get("last_used_at_utc", "")))
    if last_used is None:
        return False, "missing_or_invalid_last_used_at_utc"

    age_hours = (now - last_used).total_seconds() / 3600
    if age_hours < stale_after_hours:
        return False, "not_stale"
    return True, f"stale_for_{int(age_hours)}h"


def scan(root: Path, *, stale_after_hours: int, now: datetime) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    if not root.exists():
        return candidates
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        should_delete, reason = classify_session(child, now=now, stale_after_hours=stale_after_hours)
        if should_delete:
            candidates.append({"path": str(child), "reason": reason})
    return candidates


def remove_candidates(candidates: list[dict[str, str]]) -> list[str]:
    removed: list[str] = []
    for candidate in candidates:
        path = Path(candidate["path"])
        if is_protected(path):
            continue
        shutil.rmtree(path)
        removed.append(str(path))
    return removed


def build_plan(
    root: Path,
    *,
    dry_run: bool,
    stale_after_hours: int,
    candidates: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "dry_run": dry_run,
        "stale_after_hours": stale_after_hours,
        "root": str(root),
        "preserve_patterns": sorted(PRESERVE_NAMES | EVIDENCE_MARKERS),
        "delete_candidates": candidates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--stale-after-hours", type=int, default=24)
    parser.add_argument("--execute", action="store_true", help="delete candidates; default is dry-run")
    args = parser.parse_args(argv)

    if args.stale_after_hours < 1:
        raise SystemExit("--stale-after-hours must be >= 1")

    now = datetime.now(timezone.utc)
    candidates = scan(args.root, stale_after_hours=args.stale_after_hours, now=now)
    dry_run = not args.execute
    plan = build_plan(args.root, dry_run=dry_run, stale_after_hours=args.stale_after_hours, candidates=candidates)
    if args.execute:
        plan["removed"] = remove_candidates(candidates)
    print(json.dumps(plan, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
