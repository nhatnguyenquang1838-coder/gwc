"""CF-PRECHECK: the active plan must follow the human-approved successor G1."""
import json

import pytest

from tools.node_architect.q0_m1_m7_integration import PLAN_REF, resolve_active_plan


def _route(root, successor_ref=None, approved=True):
    route = {
        'schema_id': 'gwc.engineering-coordination-route/v1',
        'workflow_mode': 'Q0_ENGINEERING_COORDINATION',
        'runtime_epoch': 'UNIVERSAL_V2_DEVELOPMENT',
        'work_items': [],
    }
    if successor_ref is not None:
        route['approved_successor_g1'] = {
            'target_change': 'OPTION_B_CONTROLLED_FAILURE_CAMPAIGN',
            'human_approved': approved,
            'successor_plan_ref': successor_ref,
        }
    path = root / 'core/node-architect/q0-engineering-coordination-route-r1.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(route))


def _plan(root, ref):
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'runtime_epoch': 'UNIVERSAL_V2_DEVELOPMENT'}))


def test_falls_back_to_r2_without_a_route(tmp_path):
    assert resolve_active_plan(tmp_path) == PLAN_REF


def test_uses_approved_successor_plan(tmp_path):
    ref = 'core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json'
    _route(tmp_path, ref)
    _plan(tmp_path, ref)
    assert resolve_active_plan(tmp_path) == ref


def test_ignores_unapproved_or_missing_successor(tmp_path):
    ref = 'core/node-architect/successor.json'
    _route(tmp_path, ref, approved=False)
    _plan(tmp_path, ref)
    assert resolve_active_plan(tmp_path) == PLAN_REF

    _route(tmp_path, ref, approved=True)  # approved but the file is absent
    (tmp_path / ref).unlink()
    assert resolve_active_plan(tmp_path) == PLAN_REF
