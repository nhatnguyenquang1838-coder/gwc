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


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def build_q0_operation(root: Path | str, *, activity_id: str) -> tuple[dict, dict]:
    root = Path(root).resolve()
    if not activity_id or any(char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for char in activity_id):
        raise ValueError('ACTIVITY_ID_INVALID')
    head = _git(root, 'rev-parse', 'HEAD')
    source = subprocess.check_output(['git', '-C', str(root), 'show', f'{head}:{PLAN_REF}'])
    if (root / PLAN_REF).read_bytes() != source:
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
