"""Source-bound, observation-only Q0 integration of the frozen M1-M7 library.

No scheduler, mailbox, browser, lease or authority writes. Execution Binding is
identity, NOT an approval. Native qualification remains a separate admission.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

PLAN_REF = 'core/node-architect/scrum781-q0-fresh-execution-plan-r2.json'
ROUTE_REF = 'core/node-architect/q0-engineering-coordination-route-r1.json'
ACTIVATION_RECEIPT_REF = '.gwc/tasks/SCRUM-781/activation/cf-plan-activation.json'


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_active_plan(root: Path | str) -> str:
    """Resolve the active RuntimePlan with fail-closed activation semantics.

    - No approved successor: the lane stays on R2.
    - Approved successor still PENDING: raise Q0_PLAN_ACTIVATION_PENDING instead of
      silently executing the old acceptance target.
    - ACTIVATED: require the durable activation receipt, the plan file at the
      working tree, and matching digests; otherwise Q0_PLAN_ACTIVATION_INVALID.
    - The receipt binds the plan digest at activation time, not the current HEAD,
      so later additive commits do not invalidate activation.
    """
    root = Path(root).resolve()
    route_path = root / ROUTE_REF
    if not route_path.exists():
        return PLAN_REF
    route = json.loads(route_path.read_text())
    successor = route.get('approved_successor_g1') or {}
    if not successor:
        return PLAN_REF
    status = successor.get('activation_status')
    ref = successor.get('successor_plan_ref')
    if status != 'ACTIVATED':
        raise ValueError('Q0_PLAN_ACTIVATION_PENDING')
    if not ref:
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    plan_path = root / ref
    if not plan_path.exists():
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    receipt_path = root / ACTIVATION_RECEIPT_REF
    if not receipt_path.exists():
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get('plan_ref') != ref or
            receipt.get('plan_digest') != _sha256_file(plan_path) or
            not receipt.get('checkpoint_receipt_digest')):
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    checkpoint_ref = receipt.get('checkpoint_ref')
    if not checkpoint_ref:
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    checkpoint_path = Path(checkpoint_ref)
    if not checkpoint_path.is_absolute():
        checkpoint_path = root / checkpoint_ref
    if not checkpoint_path.exists():
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    import sqlite3
    with sqlite3.connect('file:' + str(checkpoint_path) + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT plan_digest,generation FROM engineering_plan_activation WHERE plan_ref=?',
                         (ref,)).fetchone()
    if row is None or row[0] != receipt['plan_digest'] or int(row[1]) < 1:
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    return ref


FRONTIER_R2_REF = 'core/node-architect/q0-engineering-frontier-r1.json'
FRONTIER_R3_REF = 'core/node-architect/q0-controlled-failure-frontier-r3.json'


def resolve_frontier_ref(root: Path | str) -> str:
    """Pick the frontier that matches the active plan (R3 campaign vs R2 lane).

    A route may declare `active_frontier_ref` to bind an explicit successor
    projection for the same plan (for example the CF-RED -> CF-FIX -> CF-LOAD
    candidates that the R3 projection omitted). The declared frontier must
    reference the same RuntimePlan; drift fails closed.
    """
    root = Path(root).resolve()
    plan = resolve_active_plan(root)
    route_path = root / ROUTE_REF
    if route_path.exists():
        route = json.loads(route_path.read_text())
        declared = route.get('active_frontier_ref')
        if declared:
            path = root / declared
            if not path.exists():
                raise ValueError('Q0_FRONTIER_SOURCE_MISSING')
            policy = json.loads(path.read_text())
            if policy.get('runtime_plan_ref') != plan:
                raise ValueError('Q0_FRONTIER_PLAN_DRIFT')
            return declared
    ref = FRONTIER_R3_REF if 'controlled-failure' in plan else FRONTIER_R2_REF
    path = root / ref
    if not path.exists():
        raise ValueError('Q0_FRONTIER_SOURCE_MISSING')
    policy = json.loads(path.read_text())
    if policy.get('runtime_plan_ref') != plan:
        raise ValueError('Q0_FRONTIER_PLAN_DRIFT')
    return ref


def build_q0_operation(root: Path | str, *, activity_id: str) -> tuple[dict, dict]:
    root = Path(root).resolve()
    if not activity_id or any(char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for char in activity_id):
        raise ValueError('ACTIVITY_ID_INVALID')
    head = _git(root, 'rev-parse', 'HEAD')
    plan_ref = resolve_active_plan(root)
    source = subprocess.check_output(['git', '-C', str(root), 'show', f'{head}:{plan_ref}'])
    if (root / plan_ref).read_bytes() != source:
        raise ValueError('Q0_PLAN_SOURCE_DRIFT')
    plan = json.loads(source)
    branch = _git(root, 'branch', '--show-current')
    if plan.get('runtime_epoch') != 'UNIVERSAL_V2_DEVELOPMENT' or plan.get('parent_task') != 'SCRUM-781':
        raise ValueError('Q0_PLAN_IDENTITY_INVALID')
    if branch != plan['branch'] or not branch.startswith('fix/SCRUM-781-q0-') or not plan['run_id'].startswith('scrum781-q0-'):
        raise ValueError('Q0_WORKTREE_BINDING_MISMATCH')
    if plan.get('source_repo') != 'nhatnguyenquang1838-coder/gwc':
        raise ValueError('Q0_REPOSITORY_BINDING_MISMATCH')
    binding = {
        'task_id': plan['parent_task'], 'repository': plan['source_repo'],
        'run_id': plan['run_id'], 'base_sha': head, 'working_branch': branch,
        'scope_hash': _digest(plan['scope']),
        'runtime_plan_digest': 'sha256:' + hashlib.sha256(source).hexdigest(),
        'authorized_actions': [], 'authorized_paths': [],
    }
    operation = {key: value for key, value in binding.items() if key not in ('authorized_actions', 'authorized_paths')}
    operation.update(head_sha=head, activity_id=activity_id,
                     operation_id=f"{plan['run_id']}:{activity_id}",
                     protocol_version='dw.taskcontroller.continuation/v1',
                     continuation_ref='', cursor={})
    return operation, binding


def observe_q0(root: Path | str, *, activity_id: str, state_path: Path | str) -> dict:
    """Run the real library with no admitted observer, retaining same-run state.

    This source/readiness probe is not a native firing, RunState, NodeAllocation,
    gate receipt, original incident replay, observer qualification or authority.
    """
    from .m1_m7_agent_workflow import load_m1_m7_contracts, build_m1_m7_graph, WorkflowState
    from .checkpoint_store import CheckpointInput, load_store, persist_to_file, replay_checkpoint, validate_readback
    operation, binding = build_q0_operation(root, activity_id=activity_id)
    manifest, profile = load_m1_m7_contracts(root)
    graph = build_m1_m7_graph(workflow_manifest=manifest, runtime_profile=profile,
                             activity_source_sha256=manifest['source_sha256'], execution_binding=binding)
    path = Path(state_path)
    store = load_store(path)
    node_id = 'scrum841-m1-m7-workflow'
    prior = replay_checkpoint(store, operation['task_id'], operation['run_id'], node_id)
    initial: WorkflowState = {'operation_envelope': operation, 'inputs': {'observer_qualified': False},
               'authority_granted': False, 'executed_effects': []}
    if prior:
        for key, value in {'repository': operation['repository'], 'branch': operation['working_branch'],
                           'base_sha': operation['base_sha'], 'head_sha': operation['head_sha'],
                           'scope_hash': operation['scope_hash']}.items():
            if prior.get(key) != value:
                raise ValueError('Q0_CHECKPOINT_SOURCE_DRIFT_REQUIRES_RECONCILIATION')
        state = prior.get('state', {})
        if state.get('current_activity') != 'M1' or state.get('reason_code') != 'OBSERVER_UNQUALIFIED' or state.get('executed_effects'):
            raise ValueError('Q0_CHECKPOINT_PRIOR_OPERATION_UNSETTLED')
        if state.get('operation_id') == operation['operation_id']:
            initial['checkpoint_projection'] = state
    raw = graph.invoke(initial)
    projection = {**operation, 'current_activity': raw['current_activity'],
                  'status': raw['status'], 'reason_code': raw['reason_code'],
                  'activity_results': raw.get('activity_results', {}), 'executed_effects': []}
    item = CheckpointInput(task_id=operation['task_id'], run_id=operation['run_id'], node_id=node_id,
                           repository=operation['repository'], branch=operation['working_branch'],
                           base_sha=operation['base_sha'], head_sha=operation['head_sha'], scope_hash=operation['scope_hash'],
                           state=projection, expected_revision=int(store.get('revision', 0)), graph_revision=manifest['workflow_id'])
    # Identical replay does not mint another revision.
    if not prior or prior.get('state') != projection:
        persist_to_file(path, item)
    readback = validate_readback(load_store(path), item)
    return {'operation': operation, 'verdict': {key: raw[key] for key in ('status', 'reason_code', 'current_activity')},
            'checkpoint_readback': readback, 'native_activation_permitted': False,
            'native_admission': 'C_E_LOOP_ACTIVATION_BLOCKED', 'authority_granted': False,
            'executed_effects': [], 'evidence_class': 'SOURCE_BOUND_READINESS_NOT_LIVE_QUALIFICATION'}
