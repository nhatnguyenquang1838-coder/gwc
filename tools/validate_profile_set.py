#!/usr/bin/env python3
"""Validate and resolve a GWC profile set."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from resolve_profiles import resolve_profile_set, safe_repo_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None)
    parser.add_argument(
        "--profile-set", default="governance/profile-sets/gwc-standard.yaml"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    try:
        result = resolve_profile_set(root, safe_repo_path(root, args.profile_set))
        report = {
            "outcome": "PASS",
            "valid": True,
            "profile_set": result["profile_set"],
            "resolved_count": len(result["resolved_profiles"]),
        }
    except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        report = {"outcome": "FAIL", "valid": False, "error": str(exc)}
    print(
        json.dumps(report, indent=2, sort_keys=True)
        if args.json
        else "Profile set validation " + report["outcome"]
        + (f": {report['error']}" if report.get("error") else "")
    )
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
