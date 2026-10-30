#!/usr/bin/env python3
"""Q0 host preflight and M1-M7 workflow entrypoint outside Hermes core.

inspect without --tick and prepare remain read-only. An owned inspect --tick
routes explicitly to the engineering graph: one-shot human communication read,
source-bound allowlisted validation, durable checkpoint and host exchange request.
workflow supports explicit user calls without manufacturing a native firing.
No scheduler writes, typed C/E reads, qualifications or leases.
"""
from __future__ import annotations
from contextlib import closing
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
import sqlite3
import subprocess
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    from tools.node_architect.q0_python_env import sanitize_python_path
    sanitize_python_path()
except Exception:
    pass
from tools.node_architect.q0_m1_m7_integration import (build_q0_operation, PLAN_REF,
                                                      resolve_active_plan, resolve_frontier_ref)
from tools.node_architect.q0_engineering_loop import assess_engineering_resume, engineering_prompt
from tools.node_architect.q0_browser_binding import BrowserBindingError, resolve_binding


def digest(value: Any) -> str:
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _read_json(path, **kwargs):
    """Read a JSON file that another process may be atomically rewriting."""
    from tools.node_architect.stable_json import read_json
    return read_json(path, **kwargs)


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
    plan = _read_json(ROOT / resolve_active_plan(ROOT))
    required = {'modify_approved_files', 'run_sandboxed_validation', 'stage', 'create_commit', 'push_working_branch'}
    agents = subprocess.check_output(['git', '-C', str(ROOT), 'show', 'HEAD:AGENTS.md'], text=True)
    contract_current = (required <= set(plan['scope']['allowed_actions'])
                        and plan.get('runtime_epoch') == 'UNIVERSAL_V2_DEVELOPMENT'
                        and plan.get('contract_mode') == 'EXECUTE'
                        and 'UNIVERSAL_V2_DEVELOPMENT override' in agents)
    with closing(sqlite3.connect((home/'state.db').as_uri()+'?mode=ro', uri=True)) as db:
        with db:
            session = db.execute('SELECT id,source,profile_name FROM sessions WHERE id=?', (args.session,)).fetchone()
            states = {}
            for label in ('loop', 'goal', 'heartbeat'):
                row = db.execute('SELECT value FROM state_meta WHERE key=?', (f'{label}:{args.session}',)).fetchone()
                states[label] = json.loads(row[0]) if row else None
    if not states['loop'] or not session:
        raise ValueError('NATIVE_SESSION_OR_LOOP_NOT_FOUND')
    leases_path = home/'runtime/active_sessions.json'
    leases = find_session_leases(_read_json(leases_path), args.session) if leases_path.exists() else []
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
    try:
        resolve_binding(home, run_id=operation['run_id'], session_id=args.session,
                        controller_url=args.controller_url)
    except BrowserBindingError:
        raise ValueError('CONTROLLER_BROWSER_BINDING_MISMATCH') from None
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
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            with db:
                tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if any(table in tables and db.execute('SELECT 1 FROM '+table+' WHERE run=?',(run_id,)).fetchone()
                       for table in ['workflow','engineering_workflow']):
                    candidates.append(path)
    if len(candidates)>1:
        raise ValueError('WORKFLOW_CHECKPOINT_SELECTION_AMBIGUOUS')
    return candidates[0] if candidates else root/'run-checkpoint'/'checkpoint.sqlite'


DEFAULT_CONTROLLER_URL = ("https://chatgpt.com/g/g-p-6a622940beac81918180ce69e50ef83c-dw-super"
                        "/c/6ad380a6-c280-83ec-bb3f-75cef495e848")


def _resolve_controller_url(session):
    """Prefer the loop's bound Controller URL over a compiled-in default.

    The Controller conversation can be rotated when a chat reaches its length
    limit; a hardcoded literal would then rebuild a stale TaskContext and every
    firing would fail ENGINEERING_CHECKPOINT_CONTEXT_DRIFT.
    """
    import os,sqlite3,re
    home=Path(os.environ.get('HERMES_HOME') or Path.home()/'.hermes')
    try:
        db=sqlite3.connect('file:'+str(home/'state.db')+'?mode=ro',uri=True)
        row=db.execute('SELECT value FROM state_meta WHERE key=?',('loop:'+session,)).fetchone()
        if row:
            match=re.search(r'bound GPT URL:\s*(\S+)',json.loads(row[0]).get('prompt',''))
            if match:return match.group(1)
    except Exception:
        pass
    return DEFAULT_CONTROLLER_URL


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
                                  ['-m','pytest','tests/test_engineering_m1_m7_workflow.py','tests/test_engineering_work_frontier.py','tests/test_engineering_frontier_host.py','tests/test_controller_exchange_adapter.py','tests/test_exchange_outbox_transitions.py','-q'],
                                  ['-m','pytest','tests/test_q0_native_g1_admission.py','tests/test_q0_universal_qualification.py','tests/test_scrum781_q0_mandatory_matrix_coverage.py','tests/test_scrum781_q0_native_host.py','-q']])
            host_capabilities['engineering.execution_ready']=lambda c,item:args.tick is not None and guard()
            from tools.node_architect.engineering_host_adapter import read_source_bound_frontier
            host_capabilities['engineering.work_frontier']=lambda c:read_source_bound_frontier(
                c,profile_ref=resolve_frontier_ref(ROOT),guard=guard)
    elif mode=='PROTECTED_TYPED_CE':
        context['workflow']['mode']='PROTECTED_TYPED_CE'
        if host_capabilities is None:
            from tools.node_architect.hermes_skill_capability_bridge import resolve_installed_hermes_skills
            host_capabilities=resolve_installed_hermes_skills(context,home=home,host_session_id=args.session)
    else:raise ValueError('TASK_WORKFLOW_MODE_INVALID')
    try:
        result = run_task_workflow(context, host_capabilities=host_capabilities,
                                   invocation_key=f'{args.session}:native:{args.tick}' if args.tick is not None else None)
        if mode=='Q0_ENGINEERING_COORDINATION':
            from tools.node_architect.task_context_binding import build_context_manifest,seal_context_manifest
            seal_context_manifest(path,build_context_manifest(context),authorized=True)
    except ValueError as exc:
        if str(exc) != 'ENGINEERING_CHECKPOINT_CONTEXT_DRIFT':
            raise
        # Recover the exact historical binding from a sealed manifest before
        # considering the legacy telemetry-based head-swap reconstruction.
        from tools.node_architect.task_context_binding import (
            classify_context_delta, digest as context_digest, load_context_manifests,
        )
        from tools.node_architect.engineering_m1_m7_workflow import (
            HISTORICAL_CONTEXT_NOT_PROVABLE, _historical_context_recovery,
            reconcile_engineering_source_head, resolve_prior_context,
        )
        with closing(sqlite3.connect(str(path))) as db:
            with db:
                row = db.execute('SELECT context_digest FROM engineering_workflow WHERE run=?',
                                 (preflight['run_id'],)).fetchone()
                stored_digest = row[0] if row else None
        manifests = load_context_manifests(path,preflight['run_id'])
        old = None
        for sealed in manifests:
            if sealed['context_digest'] != stored_digest:
                continue
            try:
                manifest=json.loads(sealed['manifest'])
                if context_digest(manifest) != sealed['manifest_digest']:
                    continue
                candidate=manifest.get('context')
                if candidate is not None and context_digest(candidate)==stored_digest:
                    old=candidate
                    break
            except (TypeError,ValueError,json.JSONDecodeError):
                continue
        if old is None:
            with closing(sqlite3.connect(str(path))) as db:
                with db:
                    telemetry = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                           "AND name='engineering_firing_telemetry'").fetchone()
                    row = (db.execute('SELECT source_head FROM engineering_firing_telemetry '
                                      'WHERE run=? ORDER BY rowid DESC LIMIT 1',
                                      (preflight['run_id'],)).fetchone() if telemetry else None)
            previous_head = row[0] if row else None
            if previous_head:
                old = json.loads(json.dumps(context))
                old['repository']['head_sha'] = previous_head
        if old is None:
            raise HISTORICAL_CONTEXT_NOT_PROVABLE(_historical_context_recovery(
                path,preflight['run_id'],current_head=context['repository']['head_sha']))
        resolve_prior_context(path,preflight['run_id'],candidate_old=old,candidate_new=context)
        delta=classify_context_delta(old,context,repository_root=ROOT)
        if delta['classification']!='HEAD_ONLY_SAFE':
            raise HISTORICAL_CONTEXT_NOT_PROVABLE(_historical_context_recovery(
                path,preflight['run_id'],current_head=context['repository']['head_sha']))
        reconcile_engineering_source_head(old, context, repository_root=ROOT,
            reason=f'additive host-tooling commit {context["repository"]["head_sha"][:12]}; no campaign work/evidence changed')
        manifest=build_context_manifest(context)
        manifest['previous_context_digest']=context_digest(old)
        result = run_task_workflow(context, host_capabilities=host_capabilities,
                                   invocation_key=f'{args.session}:native:{args.tick}' if args.tick is not None else None)
        seal_context_manifest(path,manifest,authorized=True)
    return {**preflight, 'workflow': result, 'workflow_checkpoint': str(path),
            'capability_binding':host_capabilities.get('capability_binding',{'status':'HOST_INJECTED'}),
            'trigger': 'NATIVE_OWNER_FIRING' if args.tick is not None else 'EXPLICIT_USER_REQUEST_NOT_NATIVE_TICK'}


def _attach_stall(result: dict, args) -> dict:
    """Classify repeated identical WAIT firings; never escalates by itself."""
    from tools.node_architect.loop_stall_detector import detect_stall
    verdict = (result.get("workflow") or {}).get("verdict") or {}
    if verdict.get("status") != "WAIT":
        result["stall"] = {"stalled": False, "stage": "NOT_APPLICABLE", "escalate": False}
        return result
    rows = []
    checkpoint = result.get("workflow_checkpoint")
    if checkpoint and Path(checkpoint).is_file():
        try:
            with closing(sqlite3.connect(checkpoint)) as db:
                with db:
                    db.execute("CREATE TABLE IF NOT EXISTS engineering_firing_telemetry "
                               "(run TEXT,firing TEXT,activity TEXT,reason_code TEXT,status TEXT,"
                               "source_head TEXT,result_digest TEXT,request_created INTEGER,"
                               "PRIMARY KEY(run,firing))")
                    cur = db.execute(
                        "SELECT firing, activity, reason_code, status, source_head "
                        "FROM engineering_firing_telemetry WHERE run=? ORDER BY rowid DESC LIMIT 12",
                        (result.get("run_id"),),
                    )
                    cols = ("firing", "activity", "reason_code", "status", "source_head")
                    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        except sqlite3.Error:
            rows = []
    result["stall"] = detect_stall(rows)
    if result["stall"].get("stalled"):
        result["outcome"] = "ENGINEERING_STALL_ESCALATION_REQUIRED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inspect','prepare','workflow'))
    parser.add_argument('--session', default=os.environ.get('HERMES_SESSION_ID'))
    parser.add_argument('--tick', type=int, help='inspect only: actual owner firing counter; never creates a firing')
    parser.add_argument('--workflow-mode',choices=('Q0_ENGINEERING_COORDINATION','PROTECTED_TYPED_CE'),default='Q0_ENGINEERING_COORDINATION')
    parser.add_argument('--controller-url', default=None)
    args = parser.parse_args()
    if getattr(args, 'controller_url', None) in (None, ''):
        args.controller_url = _resolve_controller_url(args.session)
    try:
        result = workflow(args) if args.command == 'workflow' or (args.command == 'inspect' and args.tick is not None) else inspect(args)
    except (ValueError, OSError, sqlite3.Error, KeyError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        if os.environ.get('DWA_TRACE'):
            import traceback; traceback.print_exc()
        print(json.dumps({'outcome':'BLOCKED','reason_code':str(exc),'native_state_modified':False}, indent=2))
        return 2
    result = _attach_stall(result, args)
    print(json.dumps(result, indent=2))
    return 0 if result['outcome'] != 'BLOCKED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
