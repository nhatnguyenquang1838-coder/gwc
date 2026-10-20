#!/usr/bin/env python3
"""Q0 host preflight and M1-M7 workflow entrypoint outside Hermes core.

inspect without --tick and prepare remain read-only. An owned inspect --tick
routes explicitly to the engineering graph: one-shot human communication read,
source-bound allowlisted validation, durable checkpoint and host exchange request.
workflow supports explicit user calls without manufacturing a native firing.
No scheduler writes, typed C/E reads, qualifications or leases.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.node_architect.q0_m1_m7_integration import build_q0_operation, PLAN_REF, resolve_active_plan
from tools.node_architect.q0_engineering_loop import assess_engineering_resume, engineering_prompt


def digest(value: Any) -> str:
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def find_session_leases(value: Any, session_id: str) -> list[dict]:
    if isinstance(value, dict):
        found = [value] if value.get('session_id') == session_id else []
        for child in value.values():
            found.extend(find_session_leases(child, session_id))
        return found
    if isinstance(value, list):
        return [item for child in value for item in find_session_leases(child, session_id)]
    return []


def inspect(args: argparse.Namespace) -> dict:
    if args.session != os.environ.get('HERMES_SESSION_ID'):
        raise ValueError('SESSION_ENV_BINDING_MISMATCH')
    home = Path(os.environ.get('HERMES_HOME', str(Path.home()/'.hermes'))).resolve()
    operation, _ = build_q0_operation(ROOT, activity_id='engineering-resume-inspection')
    plan = json.loads((ROOT / resolve_active_plan(ROOT)).read_text())
    required = {'modify_approved_files', 'run_sandboxed_validation', 'stage', 'create_commit', 'push_working_branch'}
    agents = subprocess.check_output(['git', '-C', str(ROOT), 'show', 'HEAD:AGENTS.md'], text=True)
    contract_current = (required <= set(plan['scope']['allowed_actions'])
                        and plan.get('runtime_epoch') == 'UNIVERSAL_V2_DEVELOPMENT'
                        and plan.get('contract_mode') == 'EXECUTE'
                        and 'UNIVERSAL_V2_DEVELOPMENT override' in agents)
    with sqlite3.connect((home/'state.db').as_uri()+'?mode=ro', uri=True) as db:
        session = db.execute('SELECT id,source,profile_name FROM sessions WHERE id=?', (args.session,)).fetchone()
        states = {}
        for label in ('loop', 'goal', 'heartbeat'):
            row = db.execute('SELECT value FROM state_meta WHERE key=?', (f'{label}:{args.session}',)).fetchone()
            states[label] = json.loads(row[0]) if row else None
    if not states['loop'] or not session:
        raise ValueError('NATIVE_SESSION_OR_LOOP_NOT_FOUND')
    leases_path = home/'runtime/active_sessions.json'
    leases = find_session_leases(json.loads(leases_path.read_text()), args.session) if leases_path.exists() else []
    owner_verified = len(leases) == 1 and session[1] == 'desktop' and session[2] in (None, '', 'default')
    if owner_verified:
        pid = leases[0].get('pid')
        try:
            if type(pid) is not int or pid <= 0:
                raise ValueError('INVALID_OWNER_PID')
            os.kill(pid, 0)
        except (OSError, ValueError):
            owner_verified = False
    loop = states['loop']
    if args.tick is not None and (args.command != 'inspect' or args.tick != loop['ticks_fired'] or not loop['awaiting_response']):
        raise ValueError('TICK_BINDING_MISMATCH')
    browser_binding = json.loads((home/'loop-checkpoints'/operation['run_id']/'browser-report39-039e1f6-delivery.json').read_text())
    if (browser_binding.get('session_id') != args.session
            or browser_binding.get('run_id') != operation['run_id']
            or browser_binding.get('conversation_url') != args.controller_url
            or browser_binding.get('send_outcome') != 'SENT_VERIFIED'):
        raise ValueError('CONTROLLER_BROWSER_BINDING_MISMATCH')
    expected = {'session_id': args.session, 'run_id': operation['run_id'], 'head_sha': operation['head_sha']}
    # This is preparation under the current native Q0 engineering plan and
    # direct user request, not a reading of unknown typed TaskController RunState.
    verdict = assess_engineering_resume(expected=expected, observed=expected,
        loop_role='ENGINEERING_WORK', execute_contract_current=contract_current,
        user_paused=loop['status'] != 'active', run_hold=False,
        awaiting_response=bool(loop['awaiting_response']), owner_verified=owner_verified,
        observer_qualified=False, prepare_only=args.command == 'prepare',
        owned_firing_verified=args.command == 'inspect' and args.tick is not None and owner_verified)
    if args.command == 'inspect':
        verdict['outcome'] = 'ENGINEERING_INSPECTION_COMPLETE' if verdict['outcome'] == 'ENGINEERING_LOOP_RESUME_READY' else verdict['outcome']
    return {**verdict, 'evidence_class': 'NATIVE_HOST_PREFLIGHT_NOT_EFFECT_AUTHORITY',
            'run_id': operation['run_id'], 'session_id': args.session,
            'code_head': operation['head_sha'], 'branch': operation['working_branch'],
            'runtime_plan_digest': operation['runtime_plan_digest'],
            'native_controls_digest': digest(states),
            'native_loop': {key: loop.get(key) for key in ('status','ticks_fired','interval_seconds','awaiting_response','route')},
            'native_q0_contract_source_verified': contract_current,
            'live_desktop_owner_verified': owner_verified,
            'typed_runstate': 'NOT_READ_NOT_ADMITTED',
            'run_hold_basis': 'Preparation only under current native Q0 plan and direct repair request; recheck any new stop/RUN_HOLD at the effect boundary',
            'native_state_modified': False,
            'prompt': engineering_prompt(run_id=operation['run_id'], session_id=args.session,
                repository_root=ROOT, controller_url=args.controller_url) if args.command == 'prepare' else None}


def select_workflow_checkpoint(root,run_id):
    """Keep the existing run checkpoint even when source HEAD advances."""
    root=Path(root)
    candidates=[]
    for path in sorted(root.glob('*/checkpoint.sqlite')):
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if any(table in tables and db.execute('SELECT 1 FROM '+table+' WHERE run=?',(run_id,)).fetchone()
                   for table in ['workflow','engineering_workflow']):
                candidates.append(path)
    if len(candidates)>1:
        raise ValueError('WORKFLOW_CHECKPOINT_SELECTION_AMBIGUOUS')
    return candidates[0] if candidates else root/'run-checkpoint'/'checkpoint.sqlite'


def configure_engineering_context(context):
    """Q0 adapter policy is task-specific; the engineering graph is generic."""
    from tools.node_architect.task_context_binding import digest as context_digest
    ref='core/node-architect/q0-engineering-coordination-route-r1.json'
    raw=(ROOT/ref).read_bytes()
    if raw != subprocess.check_output(['git','-C',str(ROOT),'show',context['repository']['head_sha']+':'+ref]):
        raise ValueError('ENGINEERING_ROUTE_SOURCE_DRIFT')
    route=json.loads(raw)
    if route['runtime_epoch']!=context['run']['runtime_epoch'] or route['workflow_mode']!='Q0_ENGINEERING_COORDINATION':
        raise ValueError('ENGINEERING_ROUTE_PLAN_MISMATCH')
    context['workflow']['mode']=route['workflow_mode']
    context['communication']={'issue_ref':f"github://{context['repository']['name']}/issues/{route['communication_issue']}",
                              'allowed_authors':[context['repository']['name'].split('/')[0]]}
    items=[]
    for item in route['work_items']:
        hashes={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in item['read_paths']}
        items.append({**item,'input_digest':context_digest(hashes)})
    context['engineering']={'intent_ref':route['intent_ref'],'intent_body_sha256':route['intent_body_sha256'],
                            'route_policy_ref':ref,'route_policy_digest':context_digest(route),'work_items':items}
    return context


def workflow(args: argparse.Namespace, *, host_capabilities=None) -> dict:
    """Host preflight then actual M1-M7 invocation; never grants admission."""
    preflight_args = argparse.Namespace(**vars(args))
    preflight_args.command = 'inspect'
    preflight = inspect(preflight_args)
    if preflight.get('outcome') != 'ENGINEERING_PREFLIGHT_PASS':
        raise ValueError(preflight.get('reason_code', 'WORKFLOW_PREFLIGHT_BLOCKED'))
    from tools.node_architect.task_context_binding import bind_from_plan
    from tools.node_architect.task_m1_m7_runner import run_task_workflow
    home = Path(os.environ.get('HERMES_HOME', str(Path.home()/'.hermes'))).resolve()
    trigger = f'native-tick-{args.tick}' if args.tick is not None else 'explicit-user-request'
    path = select_workflow_checkpoint(home/'cache/scratch/q0-m1-m7-host'/args.session,preflight['run_id'])
    context = bind_from_plan(ROOT, plan_ref=resolve_active_plan(ROOT), conversation_url=args.controller_url,
                             session_id=args.session, checkpoint_ref=path, skill_ref='dwa-gpt-exchange')
    if context['repository']['head_sha'] != preflight['code_head']:
        raise ValueError('WORKFLOW_SOURCE_CHANGED_AFTER_PREFLIGHT')
    mode=getattr(args,'workflow_mode','Q0_ENGINEERING_COORDINATION')
    if mode=='Q0_ENGINEERING_COORDINATION':
        context=configure_engineering_context(context)
        if host_capabilities is None:
            from tools.node_architect.engineering_host_adapter import local_engineering_capabilities
            def guard():
                current=inspect(preflight_args)
                return (current['live_desktop_owner_verified'] and current['code_head']==preflight['code_head'] and
                        current['native_loop']['status']=='active' and
                        current['outcome']=='ENGINEERING_PREFLIGHT_PASS')
            host_capabilities=local_engineering_capabilities(context,guard=guard,
                artifact_directory=path.parent/'engineering-results',
                allowed_commands=[['-m','scripts.scrum781_q0_login_fixture','--engine','native'],
                                  ['-m','pytest','tests/test_engineering_m1_m7_workflow.py','tests/test_engineering_work_frontier.py','tests/test_engineering_frontier_host.py','tests/test_controller_exchange_adapter.py','tests/test_exchange_outbox_transitions.py','-q']])
            host_capabilities['engineering.execution_ready']=lambda c,item:args.tick is not None and guard()
            from tools.node_architect.engineering_host_adapter import read_source_bound_frontier
            host_capabilities['engineering.work_frontier']=lambda c:read_source_bound_frontier(
                c,profile_ref='core/node-architect/q0-engineering-frontier-r1.json',guard=guard)
    elif mode=='PROTECTED_TYPED_CE':
        context['workflow']['mode']='PROTECTED_TYPED_CE'
        if host_capabilities is None:
            from tools.node_architect.hermes_skill_capability_bridge import resolve_installed_hermes_skills
            host_capabilities=resolve_installed_hermes_skills(context,home=home,host_session_id=args.session)
    else:raise ValueError('TASK_WORKFLOW_MODE_INVALID')
    result = run_task_workflow(context, host_capabilities=host_capabilities,
                               invocation_key=f'{args.session}:native:{args.tick}' if args.tick is not None else None)
    return {**preflight, 'workflow': result, 'workflow_checkpoint': str(path),
            'capability_binding':host_capabilities.get('capability_binding',{'status':'HOST_INJECTED'}),
            'trigger': 'NATIVE_OWNER_FIRING' if args.tick is not None else 'EXPLICIT_USER_REQUEST_NOT_NATIVE_TICK'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inspect','prepare','workflow'))
    parser.add_argument('--session', default=os.environ.get('HERMES_SESSION_ID'))
    parser.add_argument('--tick', type=int, help='inspect only: actual owner firing counter; never creates a firing')
    parser.add_argument('--workflow-mode',choices=('Q0_ENGINEERING_COORDINATION','PROTECTED_TYPED_CE'),default='Q0_ENGINEERING_COORDINATION')
    parser.add_argument('--controller-url', default='https://chatgpt.com/g/g-p-6a622940beac81918180ce69e50ef83c-dw-super/c/6ad380a6-c280-83ec-bb3f-75cef495e848')
    args = parser.parse_args()
    try:
        result = workflow(args) if args.command == 'workflow' or (args.command == 'inspect' and args.tick is not None) else inspect(args)
    except (ValueError, OSError, sqlite3.Error, KeyError, subprocess.CalledProcessError) as exc:
        print(json.dumps({'outcome':'BLOCKED','reason_code':str(exc),'native_state_modified':False}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result['outcome'] != 'BLOCKED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
