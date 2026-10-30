"""Helpers for isolated Q0 tests that exercise activation readback.

These fixtures create only a temporary SQLite readback row, bound to the
committed plan and receipt. They do not invoke an activation writer, mint
authority, or qualify runtime state.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path, PurePosixPath


def materialize_readback_checkpoint(repo_root: Path, hermes_home: Path) -> Path:
    """Seed the local scratch checkpoint expected by the read-only resolver."""
    receipt_path = repo_root / '.gwc/tasks/SCRUM-781/activation/cf-plan-activation.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    plan_ref = receipt['plan_ref']
    plan_digest = receipt['plan_digest']
    checkpoint_receipt_digest = receipt['checkpoint_receipt_digest']

    original = receipt['checkpoint_ref'].replace('\\', '/')
    parts = PurePosixPath(original).parts
    marker = 'q0-m1-m7-host'
    assert marker in parts, 'activation receipt checkpoint ref lacks stable scratch marker'
    suffix = parts[parts.index(marker) + 1:]
    assert suffix, 'activation checkpoint suffix is empty'

    checkpoint = hermes_home / 'cache' / 'scratch' / marker
    for part in suffix:
        checkpoint = checkpoint / part
    checkpoint.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(str(checkpoint))) as db:
        with db:
            db.execute(
                'CREATE TABLE IF NOT EXISTS engineering_plan_activation '
                '(plan_ref TEXT PRIMARY KEY, plan_digest TEXT, context_digest TEXT, '
                'generation INTEGER, activated_at TEXT)'
            )
            db.execute(
                'INSERT OR REPLACE INTO engineering_plan_activation VALUES (?,?,?,?,?)',
                (plan_ref, plan_digest, checkpoint_receipt_digest, 1, 'TEST_READBACK_FIXTURE'),
            )
    return checkpoint
