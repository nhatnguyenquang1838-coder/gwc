"""Fixtures for package_export entry-schema-validation (SCRUM-230).

Each fixture is a standalone manifest plus the expected overall outcome and the
expected per-entry status map. ``source_sha`` is a fixed 40-hex binding used by
the tests (it is a digest binding, never computed by the evaluator).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

FIXTURE_SOURCE_SHA = "0" * 40  # fixed binding for fixture determinism


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


VALID_SCHEMA_VERSION = "entry-schema-v1"

_VALID_ENTRY = {
    "id": "alpha",
    "path": "instructions/alpha.yaml",
    "target": "build/alpha",
    "required": True,
    "metadata": {"version": "1.0.0", "description": "alpha entry"},
}


def _manifest(entries: list[dict[str, Any]], schema_version: str = VALID_SCHEMA_VERSION) -> dict[str, Any]:
    return {"schema_version": schema_version, "entries": entries}


# 1. Valid entry
FIXTURE_VALID = {
    "manifest": _manifest([dict(_VALID_ENTRY)]),
    "expected_overall": "ENTRY_SCHEMA_VALID",
    "expected_entries": {"alpha": "accepted"},
}

# 2. Missing required field (target)
FIXTURE_MISSING_FIELD = {
    "manifest": _manifest([
        {"id": "alpha", "path": "instructions/alpha.yaml", "required": True},
    ]),
    "expected_overall": "ENTRY_SCHEMA_INVALID",
    "expected_entries": {"alpha": "rejected"},
}

# 3. Extra (unknown) field
FIXTURE_EXTRA_FIELD = {
    "manifest": _manifest([
        {"id": "alpha", "path": "p", "target": "t", "required": False, "unexpected": True},
    ]),
    "expected_overall": "ENTRY_SCHEMA_INVALID",
    "expected_entries": {"alpha": "rejected"},
}

# 4. Wrong type: required should be boolean
FIXTURE_WRONG_TYPE = {
    "manifest": _manifest([
        {"id": "alpha", "path": "p", "target": "t", "required": "yes"},
    ]),
    "expected_overall": "ENTRY_SCHEMA_INVALID",
    "expected_entries": {"alpha": "rejected"},
}

# 5. Invalid id (does not match pattern)
FIXTURE_INVALID_ID = {
    "manifest": _manifest([
        {"id": "1bad id!", "path": "p", "target": "t", "required": False},
    ]),
    "expected_overall": "ENTRY_SCHEMA_INVALID",
    "expected_entries": {"1bad id!": "rejected"},
}

# 6. Empty path and target
FIXTURE_EMPTY_PATH_TARGET = {
    "manifest": _manifest([
        {"id": "alpha", "path": "", "target": "", "required": False},
    ]),
    "expected_overall": "ENTRY_SCHEMA_INVALID",
    "expected_entries": {"alpha": "rejected"},
}

# 7. Duplicate id
FIXTURE_DUPLICATE_ID = {
    "manifest": _manifest([
        dict(_VALID_ENTRY),
        {**dict(_VALID_ENTRY), "path": "instructions/alpha2.yaml", "target": "build/alpha2"},
    ]),
    "expected_overall": "ENTRY_SCHEMA_INVALID",
    "expected_entries": {"alpha": "rejected"},
}

# 8. Schema-version drift
FIXTURE_VERSION_DRIFT = {
    "manifest": _manifest([dict(_VALID_ENTRY)], schema_version="entry-schema-v2"),
    "expected_overall": "ENTRY_SCHEMA_INVALID",
    "expected_entries": {"alpha": "rejected"},
}

ALL_FIXTURES = {
    "valid": FIXTURE_VALID,
    "missing_field": FIXTURE_MISSING_FIELD,
    "extra_field": FIXTURE_EXTRA_FIELD,
    "wrong_type": FIXTURE_WRONG_TYPE,
    "invalid_id": FIXTURE_INVALID_ID,
    "empty_path_target": FIXTURE_EMPTY_PATH_TARGET,
    "duplicate_id": FIXTURE_DUPLICATE_ID,
    "version_drift": FIXTURE_VERSION_DRIFT,
}

if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "fixtures.json"
    payload = {
        "source_sha": FIXTURE_SOURCE_SHA,
        "fixtures": ALL_FIXTURES,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
