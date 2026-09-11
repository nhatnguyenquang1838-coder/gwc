from __future__ import annotations

import copy
import importlib
from typing import Any

import pytest

from tools.node_architect.universal_run_kernel import UniversalRunKernelError

MODULE_NAME = "tools.node_architect.universal_run_context"
PROFILE = {"id": "gwc.universal-run", "version": 1}


def _api():
    try:
        module = importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name == MODULE_NAME:
            pytest.fail("R1 RED contract missing: universal_run_context.py is not materialized")
        pytest.fail(f"R1 RED contract unavailable: {type(exc).__name__}: {exc}")
    required = ("create_context_snapshot", "verify_context_snapshot")
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        pytest.fail("R1 RED contract missing symbols: " + ", ".join(missing))
    return module


def _valid(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "run_id": "RUN-R1",
        "lifecycle_profile": PROFILE,
        "objective": "establish universal run state semantics",
        "consumer_or_parent_ref": "root:GWC-UNIVERSAL-RUN-REVAMP",
        "context_refs": ["notion:contract-freeze-v1.1"],
        "scope": {"kind": "bounded", "items": ["R1"]},
        "candidate_target": {"kind": "repository", "ref": "nhatnguyenquang1838-coder/gwc"},
        "constraints": ["no external effects", "no protected-main merge"],
        "authority_effect_boundary": {"grants_authority": False, "effects": []},
        "acceptance_boundary": {"required": ["immutable digest", "source binding"]},
        "execution_shape": "RECURSIVE",
        "source_bindings": {
            "repository": "nhatnguyenquang1838-coder/gwc",
            "baseline_ref": "main",
            "baseline_sha": "d5fadc412d89f32c96ca9a1fcfd985913dc97876",
            "observed_at": "2026-09-10T08:00:00+07:00",
        },
        "ambiguities": [],
        "blocked": False,
        "evidence_strength_ref": {"kind": "provenance", "ref": "g0:context"},
        "created_at": "2026-09-10T08:00:00+07:00",
        "created_by": {"kind": "agent", "id": "DWA"},
    }
    value.update(overrides)
    return value


def _create(**overrides: Any) -> dict[str, Any]:
    return _api().create_context_snapshot(**_valid(**overrides))


def test_context_snapshot_requires_exact_run_id():
    with pytest.raises(UniversalRunKernelError):
        _create(run_id="")


def test_context_snapshot_requires_source_baseline_binding():
    bindings = _valid()["source_bindings"].copy()
    bindings.pop("baseline_sha")
    with pytest.raises(UniversalRunKernelError):
        _create(source_bindings=bindings)


def test_context_snapshot_blocking_ambiguity_fails_closed():
    with pytest.raises(UniversalRunKernelError):
        _create(ambiguities=[{"id": "C8", "status": "UNRESOLVED"}], blocked=False)


def test_context_snapshot_rejects_primitive_ambiguity_entries():
    with pytest.raises(UniversalRunKernelError):
        _create(ambiguities=["not-an-object"], blocked=True)


def test_context_snapshot_authority_field_does_not_grant_authority():
    with pytest.raises(UniversalRunKernelError):
        _create(authority_effect_boundary={"grants_authority": True, "effects": []})


def test_context_snapshot_tamper_breaks_digest():
    snapshot = _create()
    tampered = copy.deepcopy(snapshot)
    tampered["objective"] = "changed after sealing"
    assert _api().verify_context_snapshot(snapshot) is True
    assert _api().verify_context_snapshot(tampered) is False
