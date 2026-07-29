#!/usr/bin/env python3
"""Read-only, source-owned help for the GWC Power."""
from __future__ import annotations

import argparse
import json
import sys


HELP = {
    "id": "gwc",
    "name": "GWC",
    "what": "Governance and delivery-control workflows for verified context, discovery, preflight, decisions, and evidence boundaries.",
    "when": [
        "The project is new, stale, or its repository and policy context is unclear.",
        "A change needs governed intake before implementation or delivery.",
        "You need to distinguish preparation from execution, merge, deployment, or release authority.",
    ],
    "how": [
        "Activate the native gwc-g0 or gwc-g1 skill in the configured host.",
        "Use gwc-g0 to establish current context, then gwc-g1 for intake and preflight.",
        "Use the repository-native schemas, generators, and validators for formal artifacts.",
    ],
    "why": "GWC prevents stale context, unverified assumptions, and accidental crossing of approval or delivery boundaries.",
    "gives": ["Verified or classified project context", "G0/G1 discovery and preflight guidance", "Explicit evidence and authority boundaries"],
    "doesNot": ["Grant GitHub, Jira, merge, deployment, release, secret, or production authority", "Replace repository-native governance contracts"],
    "skills": ["gwc-g0", "gwc-g1"],
    "offline": "This command reads bundled metadata only; it does not contact Context7, GitHub, Jira, or any remote service.",
    "exitCodes": {"0": "Help rendered", "2": "Invalid command-line arguments"},
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show read-only GWC Power guidance")
    parser.add_argument("--json", action="store_true", help="emit the stable help contract as JSON")
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps(HELP, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    print("GWC (gwc)")
    for key in ("what", "when", "how", "why", "gives", "doesNot", "skills"):
        value = HELP[key]
        label = {"doesNot": "Does not", "gives": "User gets"}.get(key, key.capitalize())
        print(f"{label}:")
        if isinstance(value, list):
            for item in value:
                print(f"  - {item}")
        else:
            print(f"  {value}")
    print(f"Offline: {HELP['offline']}")
    print("Exit codes:")
    for code, meaning in HELP["exitCodes"].items():
        print(f"  {code}: {meaning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
