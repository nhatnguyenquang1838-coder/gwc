"""CF-PRECHECK: activation is receipt-bound, and PENDING is never silent R2."""
import hashlib
import json

import pytest

from tools.node_architect.q0_m1_m7_integration import (
    ACTIVATION_RECEIPT_REF, PLAN_REF, resolve_active_plan)

R3 = 'core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json'


def _route(root, successor_ref=None, status=None):
    route = {
        'schema_id': 'gwc.engineering-coordination-route/v1',
        'workflow_mode': 'Q0_ENGINEERING_COORDINATION',
        'runtime_epoch': 'UNIVERSAL_V2_DEVELOPMENT',
        'work_items': [],
    }
    if successor_ref is not None:
        route['approved_successor_g1'] = {
            'target_change': 'OPTION_B_CONTROLLED_FAILURE_CAMPAIGN',
            'human_approved': True,
            'successor_plan_ref': successor_ref,
            'activation_status': status or (
                'PENDING_HERMES_CF_PRECHECK_AND_NATIVE_CHECKPOINT_RECONCILIATION'),
        }
    path = root / 'core/node-architect/q0-engineering-coordination-route-r1.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(route))


def _plan(root, ref):
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'runtime_epoch': 'UNIVERSAL_V2_DEVELOPMENT'}))
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt(root, ref, digest, checkpoint_receipt='sha256:deadbeef'):
    path = root / ACTIVATION_RECEIPT_REF
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'schema_id': 'gwc.q0.plan-activation/v1',
                                'plan_ref': ref, 'plan_digest': digest,
                                'checkpoint_receipt_digest': checkpoint_receipt}))


def test_falls_back_to_r2_without_a_route(tmp_path):
    assert resolve_active_plan(tmp_path) == PLAN_REF


def test_pending_activation_is_not_silent_r2(tmp_path):
    _route(tmp_path, R3)
    _plan(tmp_path, R3)
    with pytest.raises(ValueError, match='Q0_PLAN_ACTIVATION_PENDING'):
        resolve_active_plan(tmp_path)


def test_activated_without_receipt_fails_closed(tmp_path):
    _route(tmp_path, R3, status='ACTIVATED')
    _plan(tmp_path, R3)
    with pytest.raises(ValueError, match='Q0_PLAN_ACTIVATION_INVALID'):
        resolve_active_plan(tmp_path)


def test_activated_with_mismatched_digest_fails_closed(tmp_path):
    _route(tmp_path, R3, status='ACTIVATED')
    _plan(tmp_path, R3)
    _receipt(tmp_path, R3, 'sha256:' + '0' * 64)
    with pytest.raises(ValueError, match='Q0_PLAN_ACTIVATION_INVALID'):
        resolve_active_plan(tmp_path)


def test_activated_with_valid_receipt_returns_r3(tmp_path):
    _route(tmp_path, R3, status='ACTIVATED')
    digest = _plan(tmp_path, R3)
    _receipt(tmp_path, R3, digest)
    assert resolve_active_plan(tmp_path) == R3


def test_activation_survives_later_additive_commit(tmp_path):
    """The receipt binds the plan digest, not HEAD, so new commits keep it valid."""
    _route(tmp_path, R3, status='ACTIVATED')
    digest = _plan(tmp_path, R3)
    _receipt(tmp_path, R3, digest)
    (tmp_path / 'unrelated.txt').write_text('later commit')
    assert resolve_active_plan(tmp_path) == R3
