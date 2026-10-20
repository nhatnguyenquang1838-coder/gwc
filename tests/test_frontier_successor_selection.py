"""Successor frontier projection selection (Controller COMMAND #86, Option B).

The route may bind an explicit successor frontier for the active RuntimePlan.
Selection must fail closed on missing source or plan drift.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.node_architect.q0_m1_m7_integration import (
    PLAN_REF,
    ROUTE_REF,
    resolve_frontier_ref,
)

FRONTIER_REF = "core/node-architect/q0-controlled-failure-frontier-r4.json"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1))


def test_route_declared_successor_frontier_is_selected(tmp_path: Path) -> None:
    _write(tmp_path / ROUTE_REF, {"active_frontier_ref": FRONTIER_REF})
    _write(tmp_path / FRONTIER_REF, {"runtime_plan_ref": PLAN_REF, "items": []})
    assert resolve_frontier_ref(tmp_path) == FRONTIER_REF


def test_missing_declared_frontier_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path / ROUTE_REF, {"active_frontier_ref": FRONTIER_REF})
    with pytest.raises(ValueError, match="Q0_FRONTIER_SOURCE_MISSING"):
        resolve_frontier_ref(tmp_path)


def test_declared_frontier_plan_drift_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path / ROUTE_REF, {"active_frontier_ref": FRONTIER_REF})
    _write(tmp_path / FRONTIER_REF, {"runtime_plan_ref": "other-plan.json", "items": []})
    with pytest.raises(ValueError, match="Q0_FRONTIER_PLAN_DRIFT"):
        resolve_frontier_ref(tmp_path)
