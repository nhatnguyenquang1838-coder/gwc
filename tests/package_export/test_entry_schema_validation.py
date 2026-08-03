#!/usr/bin/env python3
"""Tests for the pure package_export entry-schema-validation evaluator (SCRUM-230)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "entry_schema_validation",
    REPO / "tools" / "node_architect" / "package_export" / "entry_schema_validation.py",
)
entry_schema_validation = importlib.util.module_from_spec(SPEC)
sys.modules["entry_schema_validation"] = entry_schema_validation
SPEC.loader.exec_module(entry_schema_validation)

from tests.package_export.fixtures import (  # noqa: E402
    ALL_FIXTURES,
    FIXTURE_SOURCE_SHA,
    FIXTURE_VALID,
)

SCHEMA = entry_schema_validation.default_schema()


def _outcome(manifest: dict) -> "entry_schema_validation.ValidationOutcome":
    return entry_schema_validation.validate_entries(manifest, SCHEMA, source_sha=FIXTURE_SOURCE_SHA)


def test_all_required_fixtures_present():
    expected = {
        "valid", "missing_field", "extra_field", "wrong_type", "invalid_id",
        "empty_path_target", "duplicate_id", "version_drift",
    }
    assert expected.issubset(set(ALL_FIXTURES))


@pytest.mark.parametrize("name,fixture", list(ALL_FIXTURES.items()))
def test_fixture_outcomes(name, fixture):
    outcome = _outcome(fixture["manifest"])
    assert outcome.overall == fixture["expected_overall"]
    statuses = {e.entry_id: e.status for e in outcome.entries}
    assert statuses == fixture["expected_entries"]


def test_valid_entry_accepted_with_no_errors():
    outcome = _outcome(FIXTURE_VALID["manifest"])
    assert outcome.accepted
    assert outcome.entries[0].accepted
    assert outcome.entries[0].errors == []


def test_missing_field_reason_code():
    outcome = _outcome(ALL_FIXTURES["missing_field"]["manifest"])
    errs = outcome.entries[0].errors
    assert any(e.reason_code == entry_schema_validation.REASON_REQUIRED_MISSING for e in errs)


def test_extra_field_reason_code():
    outcome = _outcome(ALL_FIXTURES["extra_field"]["manifest"])
    errs = outcome.entries[0].errors
    assert any(e.reason_code == entry_schema_validation.REASON_UNKNOWN_FIELD for e in errs)


def test_wrong_type_reason_code():
    outcome = _outcome(ALL_FIXTURES["wrong_type"]["manifest"])
    errs = outcome.entries[0].errors
    assert any(e.reason_code == entry_schema_validation.REASON_TYPE_INVALID for e in errs)


def test_invalid_id_reason_code():
    outcome = _outcome(ALL_FIXTURES["invalid_id"]["manifest"])
    errs = outcome.entries[0].errors
    assert any(e.reason_code == entry_schema_validation.REASON_ID_INVALID for e in errs)


def test_empty_path_target_reason_codes():
    outcome = _outcome(ALL_FIXTURES["empty_path_target"]["manifest"])
    errs = outcome.entries[0].errors
    # Empty path/target violate minLength (type/pattern area) -> typed reasons.
    assert any(e.reason_code in (entry_schema_validation.REASON_TYPE_INVALID,
                                 entry_schema_validation.REASON_ID_INVALID) for e in errs)


def test_duplicate_id_reason_code():
    outcome = _outcome(ALL_FIXTURES["duplicate_id"]["manifest"])
    errs = outcome.entries[0].errors
    assert any(e.reason_code == entry_schema_validation.REASON_DUPLICATE_ID for e in errs)


def test_version_drift_reason_code():
    outcome = _outcome(ALL_FIXTURES["version_drift"]["manifest"])
    errs = outcome.entries[0].errors
    assert any(e.reason_code == entry_schema_validation.REASON_VERSION_UNSUPPORTED for e in errs)


def test_determinism_same_bytes_same_result():
    a = _outcome(FIXTURE_VALID["manifest"])
    b = _outcome(FIXTURE_VALID["manifest"])
    assert a.manifest_digest == b.manifest_digest
    assert a.schema_digest == b.schema_digest
    assert a.overall == b.overall
    assert [e.entry_id for e in a.entries] == [e.entry_id for e in b.entries]
    assert a.as_dict() == b.as_dict()


def test_determinism_ordered_errors():
    outcome = _outcome(ALL_FIXTURES["wrong_type"]["manifest"])
    errs = outcome.entries[0].errors
    keys = [(e.json_path, e.keyword, e.reason_code, e.message) for e in errs]
    assert keys == sorted(keys)


def test_binding_present_in_result():
    outcome = _outcome(FIXTURE_VALID["manifest"])
    assert outcome.source_sha == FIXTURE_SOURCE_SHA
    assert outcome.manifest_digest and len(outcome.manifest_digest) == 64
    assert outcome.schema_digest and len(outcome.schema_digest) == 64
    assert outcome.schema_version == entry_schema_validation.SUPPORTED_SCHEMA_VERSION


def test_invalid_source_sha_rejected():
    with pytest.raises(ValueError):
        entry_schema_validation.validate_entries(
            FIXTURE_VALID["manifest"], SCHEMA, source_sha="not-a-sha"
        )


def test_manifest_digest_depends_on_entries():
    o1 = _outcome(FIXTURE_VALID["manifest"])
    o2 = _outcome(ALL_FIXTURES["extra_field"]["manifest"])
    assert o1.manifest_digest != o2.manifest_digest


def test_no_filesystem_access_in_pure_path(monkeypatch):
    calls = []

    class _Guard:
        def __getattr__(self, item):
            calls.append(item)
            raise AssertionError("filesystem access attempted in pure evaluator")

    # Patch the stdlib open used by json.load to ensure the pure function never
    # reads a file for the manifest/schema passed inline.
    real_open = open

    def _open(*args, **kwargs):
        calls.append("open")
        return real_open(*args, **kwargs)

    monkeypatch.setattr("builtins.open", _open)
    _outcome(FIXTURE_VALID["manifest"])
    # default_schema() is only invoked by the CLI; here we passed SCHEMA inline,
    # so no open() must occur during validate_entries.
    assert "open" not in calls, f"unexpected filesystem access: {calls}"
