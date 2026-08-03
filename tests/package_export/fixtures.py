"""Fixture organization for package_export entry-schema-validation (SCRUM-230).

Ported layout from PR #199 (fixture organization only). The entry vocabulary is
the canonical one implemented by
``tools/node_architect/package_export/entry_schema_validation.py``:

* required fields: ``id``, ``path``, ``target``, ``required``
* optional fields: ``entry_version``, ``description``, ``category``
* ``id`` pattern: ``^[a-z0-9][a-z0-9._-]{0,127}$``

Each fixture is a standalone manifest plus its expected overall outcome and the
expected per-entry acceptance, addressed by entry *index* (not by id), because a
manifest may legitimately contain two entries sharing the same id.
"""
from __future__ import annotations

from typing import Any, Dict, List

FIXTURE_SOURCE_SHA = "0" * 40  # fixed binding for fixture determinism

_VALID_ENTRY: Dict[str, Any] = {
    "id": "alpha",
    "path": "instructions/alpha.yaml",
    "target": "build/alpha",
    "required": True,
    "entry_version": "0.1",
    "description": "alpha entry",
}


def _manifest(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"entries": entries}


# 1. Valid entry
FIXTURE_VALID = {
    "manifest": _manifest([dict(_VALID_ENTRY)]),
    "expected_outcome": "PASS",
    "expected_accepted": [True],
}

# 2. Missing required field (target)
FIXTURE_MISSING_FIELD = {
    "manifest": _manifest([
        {"id": "alpha", "path": "instructions/alpha.yaml", "required": True},
    ]),
    "expected_outcome": "FAIL",
    "expected_accepted": [False],
}

# 3. Extra (unknown) field
FIXTURE_EXTRA_FIELD = {
    "manifest": _manifest([
        {"id": "alpha", "path": "p", "target": "t", "required": False, "unexpected": True},
    ]),
    "expected_outcome": "FAIL",
    "expected_accepted": [False],
}

# 4. Wrong type: required must be boolean
FIXTURE_WRONG_TYPE = {
    "manifest": _manifest([
        {"id": "alpha", "path": "p", "target": "t", "required": "yes"},
    ]),
    "expected_outcome": "FAIL",
    "expected_accepted": [False],
}

# 5. Invalid id (does not match the closed pattern)
FIXTURE_INVALID_ID = {
    "manifest": _manifest([
        {"id": "1bad id!", "path": "p", "target": "t", "required": False},
    ]),
    "expected_outcome": "FAIL",
    "expected_accepted": [False],
}

# 6. Empty path and target
FIXTURE_EMPTY_PATH_TARGET = {
    "manifest": _manifest([
        {"id": "alpha", "path": "", "target": "", "required": False},
    ]),
    "expected_outcome": "FAIL",
    "expected_accepted": [False],
}

# 7. Duplicate id — BOTH entries must appear in the inventory.
FIXTURE_DUPLICATE_ID = {
    "manifest": _manifest([
        dict(_VALID_ENTRY),
        {**dict(_VALID_ENTRY), "path": "instructions/alpha2.yaml", "target": "build/alpha2"},
    ]),
    "expected_outcome": "FAIL",
    # first occurrence is accepted; the duplicate is rejected
    "expected_accepted": [True, False],
}

# 8. Unsupported entry_version (version drift)
FIXTURE_VERSION_DRIFT = {
    "manifest": _manifest([
        {**dict(_VALID_ENTRY), "entry_version": "9.9"},
    ]),
    "expected_outcome": "FAIL",
    "expected_accepted": [False],
}

ALL_FIXTURES: Dict[str, Dict[str, Any]] = {
    "valid": FIXTURE_VALID,
    "missing_field": FIXTURE_MISSING_FIELD,
    "extra_field": FIXTURE_EXTRA_FIELD,
    "wrong_type": FIXTURE_WRONG_TYPE,
    "invalid_id": FIXTURE_INVALID_ID,
    "empty_path_target": FIXTURE_EMPTY_PATH_TARGET,
    "duplicate_id": FIXTURE_DUPLICATE_ID,
    "version_drift": FIXTURE_VERSION_DRIFT,
}
