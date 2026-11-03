#!/usr/bin/env python3
"""Deterministic generator for human G4 approval PR comments.

Outputs EXACTLY one line matching the workflow regex:

    ^APPROVE (?:G4_MERGE|G4) ([A-Za-z0-9._:-]+) ([0-9a-f]{16}) (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$

No explanation text, no markdown, no extra newlines beyond the trailing newline.
This prevents the workflow's full-body regex match from failing (which previously
skipped the gwc:g4-authority-receipt publish step because trailing prose broke
the ^...$ anchor).

Usage:
    python tools/gen_g4_approve_comment.py \
        --approval-id g4_q0_g4_merge_pr621_main_20261103 \
        --scope-hash 33fba21e92837704 \
        --expires-at 2026-11-03T12:00:00Z
"""
from __future__ import annotations

import argparse
import re
import sys

COMMAND_RE = re.compile(
    r"^APPROVE (?:G4_MERGE|G4) "
    r"([A-Za-z0-9._:-]+) "
    r"([0-9a-f]{16}) "
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$"
)

APPROVAL_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
SCOPE_HASH_SHORT_RE = re.compile(r"^[0-9a-f]{16}$")
EXPIRES_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def validate_approval_id(value: str) -> str:
    if not APPROVAL_ID_RE.fullmatch(value):
        raise ValueError(
            "approval_id must match [A-Za-z0-9._:-]+ (got %r)" % value
        )
    return value


def validate_scope_hash_short(value: str) -> str:
    if not SCOPE_HASH_SHORT_RE.fullmatch(value):
        raise ValueError(
            "scope_hash_short must be exactly 16 lowercase hex chars (got %r)"
            % value
        )
    return value


def validate_expires_at(value: str) -> str:
    if not EXPIRES_AT_RE.fullmatch(value):
        raise ValueError(
            "expires_at must be YYYY-MM-DDTHH:MM:SSZ (got %r)" % value
        )
    return value


def generate_comment(
    *, approval_id: str, scope_hash_short: str, expires_at: str
) -> str:
    validate_approval_id(approval_id)
    validate_scope_hash_short(scope_hash_short)
    validate_expires_at(expires_at)

    comment = (
        f"APPROVE G4 {approval_id} {scope_hash_short} {expires_at}"
    )
    if not COMMAND_RE.fullmatch(comment):
        raise ValueError("generated comment failed self-validation: %r" % comment)
    return comment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic G4 approval PR comment body."
    )
    parser.add_argument(
        "--approval-id",
        required=True,
        help="G4 approval request id (e.g. g4_q0_g4_merge_pr621_main_20261103)",
    )
    parser.add_argument(
        "--scope-hash",
        required=True,
        dest="scope_hash",
        help="First 16 hex chars of the scope hash (e.g. 33fba21e92837704)",
    )
    parser.add_argument(
        "--expires-at",
        required=True,
        help="Expiry in YYYY-MM-DDTHH:MM:SSZ (e.g. 2026-11-03T12:00:00Z)",
    )
    args = parser.parse_args(argv)

    try:
        comment = generate_comment(
            approval_id=args.approval_id,
            scope_hash_short=args.scope_hash,
            expires_at=args.expires_at,
        )
    except ValueError as exc:
        return fail(str(exc))

    sys.stdout.write(comment + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
