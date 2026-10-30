"""Generic engineering coordination, NOT the frozen protected typed workflow.

Host capabilities perform I/O; this graph owns orchestration only. Human
communication, engineering execution and protected typed authority are distinct.
"""
from __future__ import annotations
from contextlib import closing
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict,Any,Callable,Literal
from .stable_json import read_json
from .task_context_binding import validate_task_context,digest,require,ACTIVITIES,read_checkpoint
from .controller_exchange_adapter import make_exchange_request,ExchangeOutbox,reconcile_controller_response

MODE='Q0_ENGINEERING_COORDINATION'
IDENTITY='generic-engineering-m1-m7/v1'


class EffectFenceResult(TypedDict):
    """A refusal-only effect-fence readback; this result grants no authority."""
    ok: Literal[True]
    approval_id: str
    scope_hash: str
    latest_command_seq: int
    last_acked_seq: int


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError('FENCE_TIMESTAMP_INVALID') from exc
    require(parsed.tzinfo is not None, 'FENCE_TIMESTAMP_INVALID')
    return parsed.astimezone(timezone.utc)


def assert_effect_fence(*, read_latest_command: Callable[[], dict], last_acked_seq: int,
                        approval_id: str | None, scope_hash: str,
                        approved_scope_prefix: str, expires_at: str | None,
                        now: str) -> EffectFenceResult:
    """Refuse stale/unbound effects; this check never grants execution authority."""
    require(bool(approval_id), 'FENCE_APPROVAL_ID_REQUIRED')
    require(bool(scope_hash) and bool(approved_scope_prefix) and
            scope_hash.startswith(approved_scope_prefix), 'FENCE_SCOPE_PREFIX_MISMATCH')
    if expires_at is not None:
        require(_parse_utc(expires_at) >= _parse_utc(now), 'FENCE_APPROVAL_EXPIRED')
    latest = read_latest_command()
    require(isinstance(latest, dict) and isinstance(latest.get('seq'), int),
            'FENCE_LATEST_COMMAND_INVALID')
    require(isinstance(last_acked_seq, int), 'FENCE_ACK_SEQUENCE_INVALID')
    latest_seq = latest['seq']
    require(latest_seq <= last_acked_seq, 'FENCE_UNCONSUMED_CONTROLLER_COMMAND')
    return {'ok': True, 'approval_id': approval_id, 'scope_hash': scope_hash,
            'latest_command_seq': latest_seq, 'last_acked_seq': last_acked_seq}


def assert_isolated_copy(live_path, copy_path) -> None:
    """Reject aliases, symlinks, and hardlinks before opening a dry-run target."""
    live = Path(live_path)
    copied = Path(copy_path)
    if copied.is_symlink():
        raise ValueError('DRY_RUN_TARGET_SYMLINK')
    try:
        live_stat = live.stat()
        copy_stat = copied.stat()
    except OSError as exc:
        raise ValueError('DRY_RUN_TARGET_COPY_REQUIRED') from exc
    same_inode = (live_stat.st_dev, live_stat.st_ino) == (copy_stat.st_dev, copy_stat.st_ino)
    if same_inode and copy_stat.st_nlink > 1:
        raise ValueError('DRY_RUN_TARGET_HARDLINK')
    if os.path.realpath(live_path) == os.path.realpath(copy_path) or same_inode:
        raise ValueError('DRY_RUN_TARGET_IS_LIVE')


class HISTORICAL_CONTEXT_NOT_PROVABLE(ValueError):
    error_code = 'HISTORICAL_CONTEXT_NOT_PROVABLE'

    def __init__(self, recovery_package):
        super().__init__(self.error_code)
        self.recovery_package = recovery_package


def _historical_context_recovery(checkpoint_ref, run, *, current_head=None):
    from .task_context_binding import load_context_manifests
    package = {'stored_context_digest': None, 'telemetry_previous_head': None,
               'current_head': current_head, 'sealed_manifest_digests': [],
               'attempted_bindings': [],
               'suggested_actions': [
                   'Preserve the checkpoint and inspect its sealed context manifests.',
                   'Recover the exact historical task context from immutable source evidence.',
                   'Resume only after exact digest equality and repository ancestry are proven.',
               ]}
    if not Path(checkpoint_ref).is_file():
        return package
    with read_checkpoint(checkpoint_ref) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='engineering_workflow'").fetchone()
        if exists:
            row = db.execute('SELECT context_digest FROM engineering_workflow WHERE run=?', (run,)).fetchone()
            if row:
                package['stored_context_digest'] = row[0]
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='engineering_firing_telemetry'").fetchone()
        if exists:
            columns = {row[1] for row in db.execute('PRAGMA table_info(engineering_firing_telemetry)')}
            if 'source_head' in columns and 'run' in columns:
                row = db.execute('SELECT source_head FROM engineering_firing_telemetry '
                                 'WHERE run=? ORDER BY rowid DESC LIMIT 1', (run,)).fetchone()
                if row:
                    package['telemetry_previous_head'] = row[0]
        stored = package['stored_context_digest']
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='engineering_invocations'").fetchone()
        if exists and stored:
            rows = db.execute('SELECT key,result FROM engineering_invocations '
                              'WHERE run=? AND binding=? ORDER BY rowid', (run, stored)).fetchall()
            package['attempted_bindings'] = [{'key': row[0], 'result': row[1]} for row in rows]
    package['sealed_manifest_digests'] = [row['manifest_digest'] for row in
                                           load_context_manifests(checkpoint_ref, run)]
    return package


def resolve_prior_context(checkpoint_ref, run, *, candidate_old, candidate_new):
    """Prove a supplied historical context against the checkpoint's exact digest."""
    from .task_context_binding import validate_task_context
    old = validate_task_context(candidate_old)
    new = validate_task_context(candidate_new)
    if not Path(checkpoint_ref).is_file():
        raise HISTORICAL_CONTEXT_NOT_PROVABLE(_historical_context_recovery(
            checkpoint_ref, run, current_head=new['repository']['head_sha']))
    with read_checkpoint(checkpoint_ref) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='engineering_workflow'").fetchone()
        row = (db.execute('SELECT context_digest FROM engineering_workflow WHERE run=?', (run,)).fetchone()
               if exists else None)
    stored = row[0] if row else None
    if stored != digest(old):
        package = _historical_context_recovery(
            checkpoint_ref, run, current_head=new['repository']['head_sha'])
        raise HISTORICAL_CONTEXT_NOT_PROVABLE(package)
    return old


class EngineeringState(TypedDict,total=False):
    current_activity:str
    status:str
    reason_code:str
    activity_results:dict
    communication:dict
    work:dict
    execution:dict
    controller_exchange_requests:list
    work_frontier:dict
    host_action_request:dict
    terminal:dict
    pre_effect_failure:dict
    terminal_exchange_request:dict
    terminal_exchange_status:str
    terminal_digest:str
    work_rounds:int
    controller_response_observation:dict


def _connect(path):
    db=sqlite3.connect(str(path),timeout=30)
    db.execute('CREATE TABLE IF NOT EXISTS engineering_workflow (run TEXT PRIMARY KEY, context_digest TEXT, state TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS engineering_invocations (run TEXT, key TEXT, binding TEXT, result TEXT, PRIMARY KEY(run,key))')
    db.execute('CREATE TABLE IF NOT EXISTS engineering_work (run TEXT, fingerprint TEXT, status TEXT, result TEXT, PRIMARY KEY(run,fingerprint))')
    db.commit()
    return db


def run_engineering_workflow(context:dict,*,host_capabilities:dict[str,Any],invocation_key:str):
    from langgraph.graph import StateGraph,START,END
    c=validate_task_context(context);require(c['workflow'].get('mode')==MODE,'ENGINEERING_MODE_REQUIRED')
    require(c['run']['runtime_epoch']=='UNIVERSAL_V2_DEVELOPMENT','ENGINEERING_EPOCH_UNSUPPORTED')
    require(isinstance(invocation_key,str) and invocation_key,'ENGINEERING_INVOCATION_ID_REQUIRED')
    path=Path(c['workflow']['checkpoint_ref']);path.parent.mkdir(parents=True,exist_ok=True)
    run=c['run']['id'];binding=digest(c)
    # Reject a stale binding before _connect can create any schema on the live
    # checkpoint. This read-only preflight makes context drift a zero-write exit.
    if path.is_file():
        checkpoint_uri=path.resolve().as_uri()+'?mode=ro'
        with closing(sqlite3.connect(checkpoint_uri,uri=True,timeout=30)) as reader:
            with reader:
                reader.execute('PRAGMA query_only=ON')
                has_workflow=reader.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='engineering_workflow'").fetchone()
                prior_binding=(reader.execute('SELECT context_digest FROM engineering_workflow WHERE run=?',
                                              (run,)).fetchone() if has_workflow else None)
        require(prior_binding is None or prior_binding[0]==binding,
                'ENGINEERING_CHECKPOINT_CONTEXT_DRIFT')
    with _connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        cached=db.execute('SELECT binding,result FROM engineering_invocations WHERE run=? AND key=?',(run,invocation_key)).fetchone()
        if cached:
            require(cached[0]==binding,'ENGINEERING_INVOCATION_BINDING_DRIFT')
            if cached[1]:return {**json.loads(cached[1]),'invocation_replayed':True}
            return {'workflow_identity':IDENTITY,'verdict':{'status':'WAIT','current_activity':'M5','reason_code':'ENGINEERING_INVOCATION_OWNER_RECONCILIATION_REQUIRED'},'invocation_replayed':False,'typed_ce_admitted':False}
        prior=db.execute('SELECT context_digest,state FROM engineering_workflow WHERE run=?',(run,)).fetchone()
        require(prior is None or prior[0]==binding,'ENGINEERING_CHECKPOINT_CONTEXT_DRIFT')
        old:dict[str,Any]=json.loads(prior[1]) if prior else {}
        db.execute('INSERT INTO engineering_invocations VALUES (?,?,?,NULL)',(run,invocation_key,binding));db.commit()

    def outcome(s,name,status,reason,**data):
        return {'current_activity':name,'status':status,'reason_code':reason,
                'activity_results':{**s.get('activity_results',{}),name:{'status':status,'reason_code':reason}},**data}
    def _telemetry(activity,reason,status,result_digest,request_created,exchange_marker=None):
        with _connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS engineering_firing_telemetry '
                       '(run TEXT,firing TEXT,activity TEXT,reason_code TEXT,status TEXT,'
                       'source_head TEXT,result_digest TEXT,request_created INTEGER,PRIMARY KEY(run,firing))')
            columns={row[1] for row in db.execute('PRAGMA table_info(engineering_firing_telemetry)')}
            if 'exchange_marker' not in columns:
                db.execute('ALTER TABLE engineering_firing_telemetry ADD COLUMN exchange_marker TEXT')
            db.execute('INSERT OR REPLACE INTO engineering_firing_telemetry '
                       '(run,firing,activity,reason_code,status,source_head,result_digest,request_created,exchange_marker) '
                       'VALUES (?,?,?,?,?,?,?,?,?)',
                       (run,invocation_key or 'explicit',activity,reason,status,
                        c['repository']['head_sha'],result_digest,int(request_created),exchange_marker))
    def _table_exists(name):
        with _connect(path) as db:
            return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None
    def _already_reported(result_digest):
        with _connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS engineering_reported (run TEXT,digest TEXT,PRIMARY KEY(run,digest))')
            return db.execute('SELECT 1 FROM engineering_reported WHERE run=? AND digest=?',
                              (run,result_digest)).fetchone() is not None
    def _mark_reported(result_digest):
        with _connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS engineering_reported (run TEXT,digest TEXT,PRIMARY KEY(run,digest))')
            db.execute('INSERT OR IGNORE INTO engineering_reported VALUES (?,?)',(run,result_digest))

    def _fingerprint(item):
        # Source-bound work is an execution of these exact inputs at this exact
        # head; do not let a stable plan identity suppress a fresh frontier item.
        if item.get('_source_policy_ref'):
            return digest(item)
        return item.get('_stable_fingerprint') or digest(item)
    def _is_verified(item):
        key=_fingerprint(item)
        with _connect(path) as db:
            row=db.execute('SELECT status FROM engineering_work WHERE run=? AND fingerprint=?',(run,key)).fetchone()
            if row is None:
                row=db.execute('SELECT status FROM engineering_work WHERE run=? AND fingerprint=?',(run,digest(item))).fetchone()
        return bool(row) and row[0]=='VERIFIED'
    def m1(s):
        read=host_capabilities.get('engineering.communication_read_once')
        if not callable(read):return outcome(s,'M1','WAIT','ENGINEERING_COMMUNICATION_READER_REQUIRED')
        r=read(c)
        require(r.get('evidence_class')=='HUMAN_COMMUNICATION_ONLY' and r.get('run_id')==run and
                r.get('from')=='GPT' and r.get('to')=='Hermes' and r.get('kind') in {'COMMAND','CORRECTION'} and
                r.get('issue_ref')==c.get('communication',{}).get('issue_ref') and
                type(r.get('seq')) is int and r['seq']>0 and r.get('comment_id') and r.get('body_sha256'),
                'ENGINEERING_COMMUNICATION_BINDING_INVALID')
        previous=old.get('consumed_human_command',{})
        require(r['seq']>=previous.get('seq',0),'ENGINEERING_COMMUNICATION_STALE')
        if r['seq']==previous.get('seq'):
            require(r['body_sha256']==previous['body_sha256'] and r['comment_id']==previous['comment_id'],'ENGINEERING_COMMUNICATION_REVISION_DRIFT')
        return outcome(s,'M1','PASS','HUMAN_COMMUNICATION_READ_NOT_TYPED_ADMISSION',communication=r)
    def _successor_intent_approved(s,body_sha):
        """A human-approved successor G1 binds the new intent command."""
        try:
            from .q0_m1_m7_integration import ROUTE_REF, ACTIVATION_RECEIPT_REF, resolve_active_plan
            root=Path(c['repository']['worktree'])
            route=read_json(root/ROUTE_REF)
            succ=route.get('approved_successor_g1') or {}
            if succ.get('human_approved') is not True or not (root/ACTIVATION_RECEIPT_REF).exists():
                return False
            resolve_active_plan(root)
        except (ValueError,OSError,KeyError):
            return False
        with _connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS engineering_intent_reconciliations '
                       '(run TEXT, body_sha256 TEXT, intent_ref TEXT, PRIMARY KEY(run,body_sha256))')
            db.execute('INSERT OR IGNORE INTO engineering_intent_reconciliations VALUES (?,?,?)',
                       (run,body_sha,s['communication'].get('comment_url')))
        return True
    def m2(s):
        if c.get('engineering',{}).get('intent_body_sha256') not in (None,s['communication']['body_sha256']):
            if _successor_intent_approved(s,s['communication']['body_sha256']):
                return outcome(s,'M2','PASS','ENGINEERING_INTENT_BOUND_TO_HUMAN_APPROVED_SUCCESSOR')
            return outcome(s,'M2','WAIT','ENGINEERING_NEW_INTENT_RECONCILIATION_REQUIRED')
        validator=host_capabilities.get('engineering.validate_context')
        if not callable(validator) or validator(c) is not True:
            return outcome(s,'M2','WAIT','ENGINEERING_CONTEXT_SOURCE_VALIDATION_REQUIRED')
        return outcome(s,'M2','PASS','TASK_PLAN_SOURCE_AND_COMMUNICATION_BOUND')
    def m3(s):
        items=sorted(c.get('engineering',{}).get('work_items',[]),key=lambda item:item['priority'])
        with _connect(path) as db:
            for item in items:
                require(item.get('input_digest') and item.get('id'),'ENGINEERING_WORK_SOURCE_BINDING_REQUIRED')
                key=_fingerprint(item)
                if not _is_verified(item):
                    return outcome(s,'M3','PASS','PLAN_PRIORITIZED_WORK_SELECTED',work={**item,'fingerprint':key})
        frontier=host_capabilities.get('engineering.work_frontier')
        if callable(frontier):
            projection=frontier(c)
            require(projection.get('source_head')==c['repository']['head_sha'] and
                    projection.get('runtime_plan_digest')==c['run']['runtime_plan_digest'] and
                    projection.get('authority_granted') is False,'ENGINEERING_FRONTIER_BINDING_INVALID')
            item=projection.get('selected_work')
            if item:
                key=_fingerprint(item)
                if not _is_verified(item):
                    return outcome(s,'M3','PASS','PLAN_DRIVEN_FRONTIER_SELECTED',work={**item,'fingerprint':key},work_frontier=projection)
                projection={**projection,'items':[
                    {**row,'status':'VERIFIED'} if row.get('id')==item.get('id') else row
                    for row in projection.get('items',[])]}
            from .engineering_work_frontier import classify_empty_frontier
            classification=classify_empty_frontier(projection)
            return outcome(s,'M3','WAIT',classification['reason_code'],work_frontier=projection)
        return outcome(s,'M3','WAIT','NO_MATERIAL_CHANGE')
    def m4(s):
        # Conflicts are scoped to the selected work, not a protected C/E global HOLD.
        work=s['work']
        if work.get('external_dependency'):
            return outcome(s,'M4','WAIT','ENGINEERING_EXTERNAL_DEPENDENCY',work=work)
        return outcome(s,'M4','PASS','SELECTED_WORK_SCOPE_RECONCILED')
    def m5(s):
        item=s['work'];allowed=c.get('runtime_plan',{}).get('scope',{}).get('allowed_actions',[])
        if item.get('action')=='modify_approved_files':
            from .engineering_work_frontier import work_within_scope
            if not work_within_scope(c,item):return outcome(s,'M5','WAIT','ENGINEERING_EFFECT_AUTHORITY_REQUIRED')
            ready=host_capabilities.get('engineering.execution_ready')
            if not callable(ready) or ready(c,item) is not True:
                return outcome(s,'M5','WAIT','ENGINEERING_GENUINE_FIRING_REQUIRED')
            request={'type':'ENGINEERING_HOST_ACTION_REQUEST','run_id':run,'session_id':c['executor']['session_id'],
                     'source_head':c['repository']['head_sha'],'task_context_digest':binding,
                     'runtime_plan_digest':c['run']['runtime_plan_digest'],'work_fingerprint':item['fingerprint'],
                     'work':item,'executor':'CURRENT_HERMES_AGENT','authority_granted':False,'effect_executed':False}
            request['request_digest']=digest(request)
            return outcome(s,'M5','WAIT','ENGINEERING_HOST_ACTION_REQUIRED',host_action_request=request)
        # Sandbox execution remains allowlisted; branch-local agent work is a
        # bound request, not an automatic shell writer or a completed effect.
        if item.get('action')!='run_sandboxed_validation' or item['action'] not in allowed:
            return outcome(s,'M5','WAIT','ENGINEERING_EFFECT_AUTHORITY_REQUIRED')
        execute=host_capabilities.get('engineering.execute')
        if not callable(execute):return outcome(s,'M5','WAIT','ENGINEERING_HOST_EXECUTOR_REQUIRED')
        preflight=host_capabilities.get('engineering.preflight')
        if not callable(preflight):return outcome(s,'M5','WAIT','ENGINEERING_HOST_PREFLIGHT_REQUIRED')
        ready=host_capabilities.get('engineering.execution_ready')
        if not callable(ready) or ready(c,item) is not True:
            return outcome(s,'M5','WAIT','ENGINEERING_GENUINE_FIRING_REQUIRED')
        def result_data(row):
            if not row or not row[1]:return {}
            try:data=json.loads(row[1])
            except (TypeError,ValueError):return {}
            return data if isinstance(data,dict) else {}
        def pre_effect_history(row):
            if not row or row[0]!='PRE_EFFECT_VALIDATION_FAILED':return None
            data=result_data(row)
            if data.get('effect_started') is not False or data.get('subprocess_started') is not False:return None
            history=data.get('attempt_history')
            if isinstance(history,list):return history
            # Upgrade a pre-history row without dropping its original failure evidence.
            return [{'attempt':1,'phase':'PREFLIGHT','status':'PRE_EFFECT_VALIDATION_FAILED',
                     'reason_code':data.get('reason_code','LEGACY_PRE_EFFECT_VALIDATION_FAILED'),
                     'exception_type':data.get('exception_type'),'effect_started':False,
                     'subprocess_started':False}]
        def prior_result(row):
            if not row:return None
            status,result=row
            if status in {'EXECUTED','VERIFIED'}:
                saved=result_data(row);execution=saved.get('execution',saved)
                return outcome(s,'M5','PASS','ENGINEERING_PRIOR_EXECUTION_REUSED',execution=execution)
            if status=='PRE_EFFECT_VALIDATION_FAILED' and pre_effect_history(row) is not None:
                return None
            return outcome(s,'M5','WAIT','ENGINEERING_EXECUTION_RECONCILIATION_REQUIRED')
        def pre_effect_failure(exc,history,attempt,phase):
            message=getattr(exc,'reason_code',None)
            if not message:
                lines=str(exc).strip().splitlines();message=lines[0] if lines else type(exc).__name__
            message=str(message)[:160]
            entry={'attempt':attempt,'phase':phase,'status':'PRE_EFFECT_VALIDATION_FAILED',
                   'reason_code':message,'exception_type':type(exc).__name__,
                   'effect_started':False,'subprocess_started':False}
            return {'classification':'PRE_EFFECT_VALIDATION_FAILED','reason_code':message,
                    'exception_type':type(exc).__name__,'effect_started':False,
                    'subprocess_started':False,
                    'recovery_action':'REVALIDATE_SAME_FINGERPRINT_AFTER_PREFLIGHT_REPAIR',
                    'current_attempt':attempt,'attempt_history':[*(history or []),entry]}
        def next_attempt(history):
            return max((entry.get('attempt',0) for entry in history or []),default=0)+1
        with _connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status,result FROM engineering_work WHERE run=? AND fingerprint=?',(run,item['fingerprint'])).fetchone()
            previous=prior_result(row)
            if previous:return previous
            history=pre_effect_history(row) if row else []
            db.commit()
        try:
            prepared=preflight(c,item)
        except Exception as exc:
            with _connect(path) as db:
                db.execute('BEGIN IMMEDIATE')
                row=db.execute('SELECT status,result FROM engineering_work WHERE run=? AND fingerprint=?',(run,item['fingerprint'])).fetchone()
                previous=prior_result(row)
                if previous:return previous
                current_history=pre_effect_history(row) if row else []
                failure=pre_effect_failure(exc,current_history or [],next_attempt(current_history),'PREFLIGHT')
                if row:
                    updated=db.execute('UPDATE engineering_work SET status=?,result=? WHERE run=? AND fingerprint=? AND status=?',
                        ('PRE_EFFECT_VALIDATION_FAILED',json.dumps(failure,sort_keys=True),run,item['fingerprint'],'PRE_EFFECT_VALIDATION_FAILED')).rowcount
                    require(updated==1,'ENGINEERING_PRE_EFFECT_FAILURE_CAS_FAILED')
                else:
                    db.execute('INSERT INTO engineering_work VALUES (?,?,?,?)',
                        (run,item['fingerprint'],'PRE_EFFECT_VALIDATION_FAILED',json.dumps(failure,sort_keys=True)))
                db.commit()
            return outcome(s,'M5','WAIT','ENGINEERING_PRE_EFFECT_VALIDATION_FAILED',pre_effect_failure=failure)
        with _connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status,result FROM engineering_work WHERE run=? AND fingerprint=?',(run,item['fingerprint'])).fetchone()
            previous=prior_result(row)
            if previous:return previous
            history=pre_effect_history(row) if row else []
            attempt=next_attempt(history)
            pass_entry={'attempt':attempt,'phase':'PREFLIGHT','status':'PREFLIGHT_PASSED',
                        'prepared_digest':digest(prepared),'effect_started':False,'subprocess_started':False}
            flight={'classification':'IN_FLIGHT','current_attempt':attempt,'effect_started':True,
                    'subprocess_started':'MAY_HAVE_STARTED','attempt_history':[*(history or []),pass_entry]}
            if row:
                updated=db.execute('UPDATE engineering_work SET status=?,result=? WHERE run=? AND fingerprint=? AND status=?',
                    ('IN_FLIGHT',json.dumps(flight,sort_keys=True),run,item['fingerprint'],'PRE_EFFECT_VALIDATION_FAILED')).rowcount
                require(updated==1,'ENGINEERING_EXECUTION_CLAIM_CAS_FAILED')
            else:
                db.execute('INSERT INTO engineering_work VALUES (?,?,?,?)',
                    (run,item['fingerprint'],'IN_FLIGHT',json.dumps(flight,sort_keys=True)))
            db.commit()
        history=[*(history or []),pass_entry]
        try:
            r=execute(c,item,prepared)
        except Exception as exc:
            if getattr(exc,'pre_effect_validation_failed',False) is True:
                detail=pre_effect_failure(exc,history,attempt,'EXECUTION_BOUNDARY_REVALIDATION')
                status='PRE_EFFECT_VALIDATION_FAILED';reason='ENGINEERING_PRE_EFFECT_VALIDATION_FAILED'
            else:
                unknown={'attempt':attempt,'phase':'EXECUTION','status':'EFFECT_OUTCOME_UNKNOWN',
                         'exception_type':type(exc).__name__,'effect_started':True,
                         'subprocess_started':'MAY_HAVE_STARTED'}
                detail={'classification':'EFFECT_OUTCOME_UNKNOWN','exception_type':type(exc).__name__,
                        'effect_started':True,'subprocess_started':'MAY_HAVE_STARTED',
                        'current_attempt':attempt,'attempt_history':[ *history,unknown]}
                status='UNKNOWN';reason='ENGINEERING_EXECUTION_RECONCILIATION_REQUIRED'
            with _connect(path) as db:
                db.execute('BEGIN IMMEDIATE')
                updated=db.execute('UPDATE engineering_work SET status=?,result=? WHERE run=? AND fingerprint=? AND status=?',
                    (status,json.dumps(detail,sort_keys=True),run,item['fingerprint'],'IN_FLIGHT')).rowcount
                require(updated==1,'ENGINEERING_EXECUTION_RESULT_CAS_FAILED')
                db.commit()
            if status=='PRE_EFFECT_VALIDATION_FAILED':return outcome(s,'M5','WAIT',reason,pre_effect_failure=detail)
            return outcome(s,'M5','WAIT',reason)
        executed={'attempt':attempt,'phase':'EXECUTION','status':'EXECUTED',
                  'effect_started':True,'subprocess_started':True}
        record={'classification':'EXECUTED','current_attempt':attempt,'effect_started':True,
                'subprocess_started':True,'attempt_history':[ *history,executed],'execution':r}
        with _connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            updated=db.execute('UPDATE engineering_work SET status=?,result=? WHERE run=? AND fingerprint=? AND status=?',
                ('EXECUTED',json.dumps(record,sort_keys=True),run,item['fingerprint'],'IN_FLIGHT')).rowcount
            require(updated==1,'ENGINEERING_EXECUTION_RESULT_CAS_FAILED')
            db.commit()
        return outcome(s,'M5','PASS','ACTUAL_HOST_VALIDATION_EXECUTED',execution=r)
    def m6(s):
        verify=host_capabilities.get('engineering.verify_result');r=s['execution']
        if not callable(verify) or verify(c,s['work'],r) is not True:
            return outcome(s,'M6','WAIT','ENGINEERING_EXECUTION_RESULT_NOT_VERIFIED')
        require(r.get('source_head')==c['repository']['head_sha'] and r.get('artifact_ref') and r.get('stdout_digest') and
                r.get('executed_effects')==[],'ENGINEERING_RESULT_BINDING_INVALID')
        with _connect(path) as db:db.execute('UPDATE engineering_work SET status=? WHERE run=? AND fingerprint=?',('VERIFIED',run,s['work']['fingerprint']))
        result=outcome(s,'M6','PASS','ACTUAL_EXECUTION_ARTIFACT_VERIFIED')
        result['work_rounds']=s.get('work_rounds',0)+1
        return result
    def m7(s):
        report=f"{c['task']['id']} engineering coordination; run {run}; firing {invocation_key or 'explicit'}; session {c['executor']['session_id']}; source {c['repository']['head_sha']}. Actual work {s['work']['id']}: {s['execution']['result']}; artifact {s['execution']['artifact_ref']}. Human command seq {s['communication']['seq']}. Protected typed C/E remains separately gated. No original replay, LOAD_PROOF or Q0 L3 claimed. Please review result and return the smallest source-bound NEXT."
        box=ExchangeOutbox(str(path)+'.engineering-exchange.sqlite')
        response_observation=None
        backlog=[]
        # Mandatory per-firing report: an unresolved earlier request is backlog
        # for its own owner and never suppresses this firing's response.
        for pending in old.get('pending_controller_exchange_requests',[]):
            prior_state=box.read(pending)
            try:
                response_observation=reconcile_controller_response(pending,prior_state)
            except ValueError:
                backlog.append(pending['marker'])
                continue
            prior_receipt=prior_state.get('receipt') or {}
            from .engineering_work_frontier import classify_controller_observation
            disposition=classify_controller_observation(prior_receipt['response_text'])
            response_observation={**response_observation,'disposition_observation':disposition}
        result_digest=digest({'work':(s.get('work') or {}).get('id'),
                              'result':(s.get('execution') or {}).get('result'),
                              'head':c['repository']['head_sha']})
        if _already_reported(result_digest):
            # ACK #69: an unchanged result is telemetry, not a new decision request.
            _telemetry('M7','ENGINEERING_TELEMETRY_RECORDED','WAIT',result_digest,False)
            return outcome(s,'M7','WAIT','ENGINEERING_TELEMETRY_RECORDED',
                           controller_exchange_requests=[],
                           controller_response_observation=response_observation,
                           backlog_pending_exchange_markers=backlog,
                           terminal={'kind':'ENGINEERING_TELEMETRY','activity':'M7',
                                     'reason_code':'ENGINEERING_TELEMETRY_RECORDED',
                                     'result_digest':result_digest,
                                     'work_id':(s.get('work') or {}).get('id')})
        _mark_reported(result_digest)
        _telemetry('M7','ENGINEERING_HOST_REPORT_AND_EXCHANGE_REQUIRED','WAIT',result_digest,True)
        request=make_exchange_request(c,report,lane='HOST_COORDINATION')
        with _connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS engineering_exchange_contexts (digest TEXT PRIMARY KEY, context TEXT)')
            db.execute('INSERT OR IGNORE INTO engineering_exchange_contexts VALUES (?,?)',(digest(c),json.dumps(c,sort_keys=True)))
        box.reserve(request)
        return outcome(s,'M7','WAIT','ENGINEERING_HOST_REPORT_AND_EXCHANGE_REQUIRED',
                        controller_exchange_requests=[request],
                        backlog_pending_exchange_markers=backlog,
                        controller_response_observation=response_observation,
                        terminal={'kind':'ENGINEERING_TERMINAL_RESULT','activity':'M7',
                                  'reason_code':'ENGINEERING_HOST_REPORT_AND_EXCHANGE_REQUIRED',
                                  'blocker':'Controller must consume the reserved HOST_COORDINATION exchange',
                                  'frontier_digest':digest(s.get('work_frontier') or {}),
                                  'work_id':s.get('work',{}).get('id'),
                                  'duplicate_guard':digest({'run':run,'activity':'M7','reason_code':'ENGINEERING_HOST_REPORT_AND_EXCHANGE_REQUIRED'})})
    graph:Any=StateGraph(EngineeringState)
    for name,handler in zip(ACTIVITIES,[m1,m2,m3,m4,m5,m6,m7]):graph.add_node(name,handler)
    graph.add_edge(START,'M1')
    def _advance(nxt):
        return lambda s:{nxt:nxt,'M8':'M8'}[nxt if s['status']=='PASS' else 'M8']
    for a,b in (('M1','M2'),('M2','M3'),('M4','M5'),('M5','M6')):
        graph.add_conditional_edges(a,_advance(b),{b:b,'M8':'M8'})
    # M3 either selects the next READY item or ends the firing: once any item
    # completed in this invocation, an exhausted frontier is a report, not a halt.
    graph.add_conditional_edges('M3',lambda s:({ 'M4':'M4','M7':'M7'}[ 'M4' if s['status']=='PASS' else 'M7']
        if s['status']=='PASS' or s.get('work_rounds') else 'M8'),{'M4':'M4','M7':'M7','M8':'M8'})
    # M6 loops back to M3 until the executable frontier is exhausted (bounded).
    graph.add_conditional_edges('M6',lambda s:('M3' if s['status']=='PASS' and s.get('work_rounds',0)<5
        else ('M7' if s['status']=='PASS' else 'M8')),{'M3':'M3','M7':'M7','M8':'M8'})
    graph.add_edge('M7',END)
    def m8(s):
        # Terminal engineering result for every non-PASS halt before M7.
        # M3 WAIT (no READY work) previously fell straight to END and the
        # Controller never received a structured blocker; M7 still dispatches
        # its own exchange request and is unchanged.
        frontier=s.get('work_frontier') or {
            'source_head':c['repository']['head_sha'],
            'runtime_plan_digest':c['run']['runtime_plan_digest'],
            'items':[],'selected_work':None,'authority_granted':False}
        blocker={
            'M3':'No READY work remains on the frozen plan frontier; all candidates classified READY/VERIFIED/BLOCKED_EXTERNAL_EVIDENCE/BLOCKED_AUTHORITY/WAIT_INPUT',
            'M4':'Selected work has an unresolved external dependency',
            'M5':'Effect authority or genuine firing admission not granted for the selected work',
            'M6':'Execution result not verified against exact source head and artifact binding',
        }.get(s['current_activity'],'Engineering halted before M7 without a selected work result')
        if s['current_activity']=='M5' and s['reason_code'] in {
                'ENGINEERING_PRE_EFFECT_VALIDATION_FAILED','ENGINEERING_PRE_EFFECT_REPAIR_REQUIRED'}:
            blocker='Pre-effect validation failed; no task subprocess started. Repair the source/environment, then revalidate the same fingerprint; preserve the prior failure entry and claim atomically only after preflight passes.'
        terminal={'kind':'ENGINEERING_TERMINAL_RESULT','activity':s['current_activity'],
                  'reason_code':s['reason_code'],'status':s['status'],
                  'blocker':blocker,
                  'frontier':frontier,
                  'source_head':c['repository']['head_sha'],
                  'runtime_plan_digest':c['run']['runtime_plan_digest'],
                  'work_id':(s.get('work') or {}).get('id'),
                  'work_action':(s.get('work') or {}).get('action'),
                  'external_dependency':(s.get('work') or {}).get('external_dependency'),
                  'duplicate_guard':digest({'run':run,'activity':s['current_activity'],
                                             'reason_code':s['reason_code'],'source_head':c['repository']['head_sha']})}
        if s.get('pre_effect_failure') is not None:
            terminal['pre_effect_failure']=s['pre_effect_failure']
        from .engineering_work_frontier import controller_dispatch_required,terminal_blocker_identity
        blocker_identity=terminal_blocker_identity(run_id=run,
            runtime_plan_digest=c['run']['runtime_plan_digest'],activity=s['current_activity'],
            reason_code=s['reason_code'],work=s.get('work'),frontier=frontier)
        terminal['blocker_identity']=blocker_identity
        if s['current_activity']=='M3' and s['reason_code']=='ENGINEERING_FRONTIER_WAIT_AUTHORITY':
            authority_items=[row for row in frontier.get('items',[]) if row.get('status')=='BLOCKED_AUTHORITY']
            work_packages=[]
            for row in authority_items:
                work=row.get('work') or {}
                work_packages.append({'id':row.get('id'),'title':work.get('title',''),
                    'paths':list(work.get('paths',work.get('write_paths',[]))),
                    'acceptance_tests':list(work.get('acceptance_tests',[]))})
            request_fields={'base_sha':c['repository']['head_sha'],
                'authority_requested':'APPROVE_BLOCKED_AUTHORITY_WORK','work_packages':work_packages,
                'decision_required':'APPROVE | REJECT'}
            scope_hash=digest(request_fields)
            request_id=f"approval-{run}-{scope_hash[7:23]}"
            approval_request={'request_id':request_id,'scope_hash':scope_hash,**request_fields}
            with _connect(path) as db:
                db.execute('CREATE TABLE IF NOT EXISTS engineering_approval_requests '
                           '(request_id TEXT PRIMARY KEY, scope_hash TEXT, request TEXT, first_firing TEXT)')
                db.execute('BEGIN IMMEDIATE')
                existing=db.execute('SELECT request FROM engineering_approval_requests '
                                    'WHERE request_id=? AND scope_hash=?',(request_id,scope_hash)).fetchone()
                if existing:
                    terminal['blocked_by_pending_approval_scope']=scope_hash
                else:
                    db.execute('INSERT INTO engineering_approval_requests VALUES (?,?,?,?)',
                        (request_id,scope_hash,json.dumps(approval_request,sort_keys=True),invocation_key or 'explicit'))
                    terminal['approval_request']=approval_request
                db.commit()
        # Deadlock guard. A stall is stable across ticks: same activity +
        # reason_code + status + source_head and no selected work. Re-dispatching
        # the same blocker every firing is the repeated identical WAIT the user
        # flagged. One report per stall_key; the original request stays open and
        # is not re-sent. The guard is invalidated only when the frontier actually
        # moves (new selected work, source head change, or a Controller response
        # that changes the blocker identity) — those produce a NEW stall_key.
        from tools.node_architect.loop_stall_detector import detect_stall
        _stall_rows=[]
        with _connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS engineering_firing_telemetry '
                       '(run TEXT,firing TEXT,activity TEXT,reason_code TEXT,status TEXT,'
                       'source_head TEXT,result_digest TEXT,request_created INTEGER,'
                       'PRIMARY KEY(run,firing))')
            cur=db.execute('SELECT activity,reason_code,status,source_head '
                           'FROM engineering_firing_telemetry WHERE run=? '
                           'ORDER BY rowid DESC LIMIT 12',(run,))
            _stall_rows=[dict(zip(('activity','reason_code','status','source_head'),r)) for r in cur.fetchall()]
        _stall=detect_stall(_stall_rows)
        terminal['stall']={k:_stall.get(k) for k in ('stalled','streak','stage','stall_key','escalate')}
        if _stall.get('stalled'):
            terminal['stall_key']=_stall['stall_key']
        controller_required=controller_dispatch_required(s['current_activity'],s['reason_code'])
        controller_notification_required=controller_required
        # A confirmed stall suppresses a fresh dispatch request for the same
        # stable key; the original report stays open and is not re-sent.
        if _stall.get('stalled') and controller_required:
            controller_required=False
            terminal['controller_dispatch_required']=False
            terminal['stall_suppresses_dispatch']=True
        terminal['controller_dispatch_required']=controller_required
        decision_packet=None
        if s['current_activity']=='M3' and frontier.get('selected_work') is None:
            from .engineering_work_frontier import build_recovery_decision_packet
            plan=c.get('runtime_plan',{})
            decision_packet=build_recovery_decision_packet(
                run_id=run,goal=c['task']['objective'],runtime_plan=plan,frontier=frontier)
            terminal['decision_packet']=decision_packet
        terminal_digest=digest(terminal)
        terminal_exchange_request=None
        terminal_exchange_status=None
        terminal_exchange_state=None
        response_observation=None
        controller_exchange_requests=[]
        # Terminal results owned by the Controller are routed independently of
        # protected M7. The stable blocker identity owns one canonical request;
        # firing identity is retained only in telemetry.
        dispatch_request=controller_required
        request_created=False
        telemetry_marker=None
        if dispatch_request or _table_exists('engineering_terminal_dispatches'):
            box=ExchangeOutbox(str(path)+'.engineering-exchange.sqlite')
            candidate_request=None
            request=None
            if dispatch_request:
                report=(f"{c['task']['id']} Q0 terminal engineering result; run {run}; firing {invocation_key or 'explicit'}; "
                        f"session {c['executor']['session_id']}; source {c['repository']['head_sha']}; "
                        f"terminal {terminal_digest}; blocker_identity ({blocker_identity}). "
                        f"Result: {json.dumps(terminal,sort_keys=True,separators=(',',':'))}. "
                        "No typed C/E admission, authority, plan mutation, original replay, LOAD_PROOF or L3 claim. "
                        "Please review and return the smallest source-bound disposition; an acceptance-target change still requires an explicit human-approved immutable G1 revision.")
                candidate_request=make_exchange_request(c,report,lane='HOST_COORDINATION')
            with _connect(path) as db:
                db.execute('CREATE TABLE IF NOT EXISTS engineering_terminal_dispatches '
                           '(blocker_identity TEXT PRIMARY KEY, request TEXT NOT NULL, '
                           'request_source_head TEXT NOT NULL, response_observation TEXT)')
                columns={row[1] for row in db.execute('PRAGMA table_info(engineering_terminal_dispatches)')}
                if 'first_firing' not in columns:
                    db.execute('ALTER TABLE engineering_terminal_dispatches ADD COLUMN first_firing TEXT')
                if 'last_firing' not in columns:
                    db.execute('ALTER TABLE engineering_terminal_dispatches ADD COLUMN last_firing TEXT')
                db.execute('BEGIN IMMEDIATE')
                existing=db.execute('SELECT request,request_source_head FROM engineering_terminal_dispatches '
                                    'WHERE blocker_identity=?',(blocker_identity,)).fetchone()
                if existing:
                    db.execute('UPDATE engineering_terminal_dispatches SET last_firing=? '
                               'WHERE blocker_identity=?',(invocation_key or 'explicit',blocker_identity))
                elif dispatch_request:
                    db.execute('CREATE TABLE IF NOT EXISTS engineering_exchange_contexts (digest TEXT PRIMARY KEY, context TEXT)')
                    db.execute('INSERT OR IGNORE INTO engineering_exchange_contexts VALUES (?,?)',
                               (candidate_request['task_context_digest'],json.dumps(c,sort_keys=True)))
                    db.execute('INSERT INTO engineering_terminal_dispatches '
                               '(blocker_identity,request,request_source_head,response_observation,first_firing,last_firing) '
                               'VALUES (?,?,?,NULL,?,?)',
                               (blocker_identity,json.dumps(candidate_request,sort_keys=True),c['repository']['head_sha'],
                                invocation_key or 'explicit',invocation_key or 'explicit'))
                else:
                    existing=None
                db.commit()
            if existing:
                request=json.loads(existing[0])
                try:
                    terminal_exchange_state=box.read(request)
                    terminal_exchange_status=terminal_exchange_state['status']
                except Exception as exc:
                    terminal['controller_notification_read_error']=type(exc).__name__
                terminal['outbox_request_source_head']=existing[1]
                telemetry_marker=request['marker']
                try:
                    if terminal_exchange_state is None:
                        raise ValueError('EXCHANGE_READ_FAILED')
                    response_observation=reconcile_controller_response(request,terminal_exchange_state)
                except ValueError:
                    terminal['blocked_by_pending_exchange_marker']=request['marker']
                    terminal['controller_dispatch_required']=False
                else:
                    from .engineering_work_frontier import classify_controller_observation
                    receipt=terminal_exchange_state['receipt']
                    disposition=classify_controller_observation(receipt['response_text'])
                    response_observation={**response_observation,'disposition_observation':disposition}
                    with _connect(path) as db:
                        db.execute('UPDATE engineering_terminal_dispatches SET response_observation=? '
                                   'WHERE blocker_identity=?',(json.dumps(response_observation,sort_keys=True),blocker_identity))
                    if decision_packet is not None:
                        decision_packet['controller_disposition_observation']=disposition
                    terminal['controller_response_observation']=response_observation
            elif dispatch_request:
                request=candidate_request
                box.reserve(request)
                terminal_exchange_request=request
                try:
                    terminal_exchange_state=box.read(request)
                    terminal_exchange_status=terminal_exchange_state['status']
                except Exception as exc:
                    terminal['controller_notification_read_error']=type(exc).__name__
                controller_exchange_requests=[request]
                request_created=True
                telemetry_marker=request['marker']
                terminal['controller_dispatch_required']=True
            if controller_notification_required:
                receipt=(terminal_exchange_state or {}).get('receipt') or {}
                delivery_statuses={
                    'MESSAGE_SENT_VERIFIED','CONTROLLER_ACTION_REQUIRED',
                    'CONTROLLER_RESPONSE_VERIFIED'}
                delivered=((terminal_exchange_state or {}).get('status') in delivery_statuses and
                    receipt.get('status') in delivery_statuses and
                    request is not None and receipt.get('marker')==request.get('marker'))
                terminal['controller_notification']={
                    'required':True,
                    'browser_ack_required':True,
                    'delivery_state':'DELIVERED' if delivered else 'NOT_DELIVERED',
                    'delivery_receipt_ref':request['marker'] if delivered else None,
                    'delivery_evidence':'OUTBOX_RECEIPT' if delivered else 'NONE',
                }
        _telemetry(s['current_activity'],s['reason_code'],s['status'],digest(terminal),request_created,telemetry_marker)
        if response_observation is not None:
            terminal['controller_response_observation']=response_observation
        terminal_digest=digest(terminal)
        # M8 is a result-dispatch node, NOT a gate. It must preserve the
        # original WAIT status and reason_code so the Controller still sees
        # ENGINEERING_EFFECT_AUTHORITY_REQUIRED / ENGINEERING_GENUINE_FIRING_REQUIRED
        # / ENGINEERING_EXECUTION_RECONCILIATION_REQUIRED as the verdict, with the
        # structured terminal payload attached as evidence. Marking it PASS would
        # silently convert a blocked gate into a passed one.
        return outcome(s,'M8',s['status'],s['reason_code'],terminal=terminal,
                       terminal_exchange_request=terminal_exchange_request,
                       terminal_exchange_status=terminal_exchange_status,
                       terminal_digest=terminal_digest,
                       controller_response_observation=response_observation,
                       controller_exchange_requests=controller_exchange_requests)
    graph.add_node('M8',m8)
    graph.add_edge('M8',END)
    try:state=graph.compile().invoke({'activity_results':{}})
    except Exception:
        # Invocation remains reserved after an unexpected interruption; never replay effects blindly.
        raise
    consumed=old.get('consumed_human_command',{})
    newly_consumed=False
    if state.get('activity_results',{}).get('M2',{}).get('status')=='PASS':
        consumed={k:state['communication'][k] for k in ['seq','comment_id','body_sha256','comment_url']}
        newly_consumed=consumed!=old.get('consumed_human_command',{})
    state['consumed_human_command']=consumed
    pending={}
    if old.get('pending_controller_exchange_requests'):
        box=ExchangeOutbox(str(path)+'.engineering-exchange.sqlite')
        for request in old.get('pending_controller_exchange_requests',[]):
            prior=box.read(request)
            try:reconcile_controller_response(request,prior)
            except ValueError:
                pending[request['request_digest']]=request
    pending.update({r['request_digest']:r for r in state.get('controller_exchange_requests',[])})
    state['pending_controller_exchange_requests']=list(pending.values())
    result={'workflow_identity':IDENTITY,'evidence_namespace':'ENGINEERING_COORDINATION_NOT_PROTECTED_CE',
            'verdict':{k:state[k] for k in ['status','reason_code','current_activity']},'activity_results':state['activity_results'],
            'work':state.get('work'),'execution':state.get('execution'),
            'work_frontier':state.get('work_frontier'),'host_action_request':state.get('host_action_request'),
            'communication_consumption':{'cursor':consumed,'newly_consumed':newly_consumed,'is_typed_cursor':False},
            'terminal':state.get('terminal'),
            'terminal_exchange_request':state.get('terminal_exchange_request'),
            'terminal_exchange_status':state.get('terminal_exchange_status'),
            'terminal_digest':state.get('terminal_digest'),
            'controller_response_observation':state.get('controller_response_observation'),
            'decision_packet':(state.get('terminal') or {}).get('decision_packet'),
            'pending_controller_exchange_requests':state['pending_controller_exchange_requests'],
            'graph_requests':state.get('controller_exchange_requests',[]),'invocation_replayed':False,
            'typed_ce_admitted':False,'authority_granted':False,'native_tick_settled':False,
            'executed_effects':[],'checkpoint_ref':str(path),'checkpoint_readback':'PASS'}
    with _connect(path) as db:
        db.execute('BEGIN IMMEDIATE');db.execute('INSERT OR REPLACE INTO engineering_workflow VALUES (?,?,?)',(run,binding,json.dumps(state,sort_keys=True)))
        db.execute('UPDATE engineering_invocations SET result=? WHERE run=? AND key=?',(json.dumps(result,sort_keys=True),run,invocation_key));db.commit()
    with _connect(path) as db:
        require(json.loads(db.execute('SELECT result FROM engineering_invocations WHERE run=? AND key=?',(run,invocation_key)).fetchone()[0])==result,'ENGINEERING_DURABLE_READBACK_FAILED')
    return result


def reconcile_engineering_source_head(old_context,new_context,*,repository_root,reason,dry_run:bool=False,
                                      target_copy: str | None = None,
                                      read_latest_command: Callable[[], dict] | None = None,
                                      last_acked_seq=None,
                                      approval_id=None,scope_hash=None,
                                      approved_scope_prefix=None,expires_at=None,now=None):
    """Explicit HEAD-only continuation; retains old invocations and effect claims.

    Non-dry reconciliation requires an explicit refusal-only fence before any
    checkpoint access; omitted values must not select an unguarded legacy path.
    Passing this fence does not establish trusted approval provenance or grant
    effect authority. Dry runs require a caller-created isolated database copy
    and never open the live checkpoint with a writable connection.
    """
    import copy,subprocess
    if dry_run and target_copy is None:
        raise ValueError('DRY_RUN_REQUIRES_ISOLATED_COPY')
    old=validate_task_context(old_context);new=validate_task_context(new_context);equivalent=copy.deepcopy(new)
    equivalent['repository']['head_sha']=old['repository']['head_sha'];require(equivalent==old and reason,'ENGINEERING_RECONCILE_NON_HEAD_DRIFT')
    if not dry_run:
        if not (callable(read_latest_command) and last_acked_seq is not None and
                approval_id is not None and scope_hash is not None and
                approved_scope_prefix is not None and now is not None):
            raise ValueError('FENCE_CONTEXT_REQUIRED')
        assert_effect_fence(read_latest_command=read_latest_command,
            last_acked_seq=last_acked_seq,approval_id=approval_id,
            scope_hash=scope_hash,approved_scope_prefix=approved_scope_prefix,
            expires_at=expires_at,now=now)
    root=Path(repository_root).resolve()
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
    require(root==Path(new['repository']['worktree']).resolve() and git('rev-parse','HEAD')==new['repository']['head_sha'] and git('branch','--show-current')==new['repository']['branch'],'ENGINEERING_RECONCILE_GIT_BINDING_REQUIRED')
    subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',old['repository']['head_sha'],new['repository']['head_sha']],check=True)
    receipt={'old_context_digest':digest(old),'new_context_digest':digest(new),
             'old_head':old['repository']['head_sha'],'new_head':new['repository']['head_sha'],'reason':reason}
    if dry_run:
        live_path=old['workflow']['checkpoint_ref']
        assert_isolated_copy(live_path,target_copy)
        live_uri=Path(live_path).resolve().as_uri()+'?mode=ro'
        with closing(sqlite3.connect(live_uri,uri=True,timeout=30)) as reader:
            with reader:
                reader.execute('PRAGMA query_only=ON')
                live_table=reader.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='engineering_workflow'").fetchone()
                live_row=(reader.execute('SELECT context_digest FROM engineering_workflow WHERE run=?',
                                         (old['run']['id'],)).fetchone() if live_table else None)
                require(live_row is not None and live_row[0]==digest(old),
                        'ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
        with closing(sqlite3.connect(str(target_copy),timeout=30)) as db:
            with db:
                db.execute('BEGIN IMMEDIATE')
                table=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='engineering_workflow'").fetchone()
                row=(db.execute('SELECT context_digest,state FROM engineering_workflow WHERE run=?',
                                (old['run']['id'],)).fetchone() if table else None)
                require(row is not None and row[0]==digest(old),
                        'ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
                db.execute('CREATE TABLE IF NOT EXISTS engineering_source_reconciliations '
                           '(key TEXT PRIMARY KEY, receipt TEXT, prior_state TEXT)')
                db.execute('INSERT INTO engineering_source_reconciliations VALUES (?,?,?)',
                           (digest(receipt),json.dumps(receipt,sort_keys=True),row[1]))
                updated=db.execute('UPDATE engineering_workflow SET context_digest=? WHERE run=? AND context_digest=?',
                                   (digest(new),old['run']['id'],digest(old)))
                require(updated.rowcount==1,'ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
                db.commit()
        would_apply={'run':old['run']['id'],'old_context_digest':digest(old),
                     'new_context_digest':digest(new),'receipt_digest':digest(receipt)}
        return {'dry_run':True,'would_apply':would_apply,'receipt':receipt}

    with closing(sqlite3.connect(str(old['workflow']['checkpoint_ref']),timeout=30)) as db:
        with db:
            db.execute('BEGIN IMMEDIATE')
            table=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='engineering_workflow'").fetchone()
            row=(db.execute('SELECT context_digest,state FROM engineering_workflow WHERE run=?',(old['run']['id'],)).fetchone()
                 if table else None)
            if row is None:raise ValueError('ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
            require(row[0]==digest(old),'ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
            db.execute('CREATE TABLE IF NOT EXISTS engineering_source_reconciliations (key TEXT PRIMARY KEY, receipt TEXT, prior_state TEXT)')
            db.execute('INSERT INTO engineering_source_reconciliations VALUES (?,?,?)',(digest(receipt),json.dumps(receipt,sort_keys=True),row[1]))
            updated=db.execute('UPDATE engineering_workflow SET context_digest=? WHERE run=? AND context_digest=?',(digest(new),old['run']['id'],digest(old)))
            require(updated.rowcount==1,'ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
            db.commit()
    with _connect(old['workflow']['checkpoint_ref']) as reader:
        require(reader.execute('SELECT context_digest FROM engineering_workflow WHERE run=?',(old['run']['id'],)).fetchone()[0]==digest(new),'ENGINEERING_RECONCILE_DURABLE_READBACK_FAILED')
    return receipt


def reconcile_legacy_terminal_dispatches(checkpoint_ref,run):
    """Audit legacy firing-keyed rows by their blocker identity; mutate nothing."""
    import re
    pattern=re.compile(r'blocker_identity\s*\(?\s*(sha256:[0-9a-f]{64})\s*\)?',re.I)
    groups={};examined=0;unmatched=0
    if not Path(checkpoint_ref).is_file():
        return {'run_id':run,'rows_examined':0,'unmatched_rows':0,'groups':{},
                'authority_granted':False,'typed_ce_admitted':False,'mutated':False}
    with read_checkpoint(checkpoint_ref) as db:
        try:
            rows=db.execute('SELECT blocker_identity,request,request_source_head,response_observation '
                            'FROM engineering_terminal_dispatches').fetchall()
        except sqlite3.OperationalError:
            rows=[]
        for stored_identity,raw_request,source_head,response_observation in rows:
            try:request=json.loads(raw_request)
            except (TypeError,ValueError):continue
            if request.get('run_id')!=run:continue
            examined+=1
            report=str(request.get('report') or '')
            match=pattern.search(report)
            if not match:
                unmatched+=1;continue
            identity=match.group(1)
            groups.setdefault(identity,[]).append({'stored_blocker_identity':stored_identity,
                'marker':request.get('marker'),'request_digest':request.get('request_digest'),
                'request_source_head':source_head,'has_response_observation':response_observation is not None})
    return {'run_id':run,'rows_examined':examined,'unmatched_rows':unmatched,
            'groups':{identity:sorted(rows,key=lambda row:(row.get('marker') or '',row.get('stored_blocker_identity') or ''))
                      for identity,rows in sorted(groups.items())},
            'authority_granted':False,'typed_ce_admitted':False,'mutated':False}


def reconcile_engineering_conversation_binding(old_context,new_context,*,reason):
    """Bind the SAME run to a new Controller conversation (session rotation).

    Only ``controller.conversation_url`` may change. Everything else must stay
    byte-identical, the new URL must be a ChatGPT conversation in the same GPT
    project, and every invocation/work/outbox row is preserved. Rotation is a
    transport relocation, never new authority.
    """
    import copy
    from urllib.parse import urlsplit
    old=validate_task_context(old_context);new=validate_task_context(new_context)
    require(isinstance(reason,str) and bool(reason.strip()),'CONVERSATION_REBIND_REASON_REQUIRED')
    old_url=str(old['controller'].get('conversation_url') or '')
    new_url=str(new['controller'].get('conversation_url') or '')
    require(old_url!=new_url,'CONVERSATION_REBIND_UNCHANGED_URL')
    equivalent=copy.deepcopy(new)
    equivalent['controller']['conversation_url']=old_url
    require(equivalent==old,'CONVERSATION_REBIND_CONTEXT_DRIFT')
    old_parts=urlsplit(old_url);new_parts=urlsplit(new_url)
    require(new_parts.scheme=='https' and new_parts.hostname=='chatgpt.com','CONVERSATION_REBIND_URL_INVALID')
    require(new_parts.path.startswith(old_parts.path.split('/c/')[0]),'CONVERSATION_REBIND_PROJECT_MISMATCH')
    require('/c/' in new_parts.path and new_parts.path!=old_parts.path,'CONVERSATION_REBIND_URL_INVALID')
    with _connect(old['workflow']['checkpoint_ref']) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT context_digest,state FROM engineering_workflow WHERE run=?',(old['run']['id'],)).fetchone()
        if row is None:raise ValueError('CONVERSATION_REBIND_PRIOR_CONTEXT_MISMATCH')
        require(row[0]==digest(old),'CONVERSATION_REBIND_PRIOR_CONTEXT_MISMATCH')
        db.execute('CREATE TABLE IF NOT EXISTS engineering_source_reconciliations (key TEXT PRIMARY KEY, receipt TEXT, prior_state TEXT)')
        receipt={'kind':'CONTROLLER_SESSION_ROTATED','old_context_digest':digest(old),
                 'new_context_digest':digest(new),'old_conversation_url':old_url,'new_conversation_url':new_url,
                 'reason':reason}
        db.execute('INSERT INTO engineering_source_reconciliations VALUES (?,?,?)',(digest(receipt),json.dumps(receipt),row[1]))
        db.execute('UPDATE engineering_workflow SET context_digest=? WHERE run=? AND context_digest=?',(digest(new),old['run']['id'],digest(old)))
        db.commit()
    with _connect(old['workflow']['checkpoint_ref']) as reader:
        require(reader.execute('SELECT context_digest FROM engineering_workflow WHERE run=?',(old['run']['id'],)).fetchone()[0]==digest(new),'CONVERSATION_REBIND_DURABLE_READBACK_FAILED')
    return receipt


def reconcile_engineering_route_metadata(old_context,new_context,*,repository_root,reason,route_ref):
    """Explicit additive route-metadata continuation (e.g. human-approved G1 successor).

    A successor acceptance-target approval may add read-only metadata to the
    coordination route while leaving the executable route policy unchanged.
    This advances the SAME checkpoint across such a delta, but only when the
    delta is provably additive: every pre-existing route key must keep its exact
    value, and the executable policy keys (workflow_mode, runtime_epoch,
    communication_issue, intent_ref, intent_body_sha256, work_items) must be
    byte-identical. All invocations, work rows, outbox rows and UNKNOWN
    statuses are preserved; nothing is erased, retried or replanned.
    """
    import copy,subprocess
    old=validate_task_context(old_context);new=validate_task_context(new_context)
    require(isinstance(reason,str) and bool(reason.strip()),'ROUTE_METADATA_REASON_REQUIRED')
    require(old['repository']['head_sha']!=new['repository']['head_sha'],'ROUTE_METADATA_UNCHANGED_HEAD')
    old_eng=old.get('engineering') or {};new_eng=new.get('engineering') or {}
    equivalent=copy.deepcopy(new)
    equivalent['repository']['head_sha']=old['repository']['head_sha']
    equivalent['engineering']['route_policy_digest']=old_eng.get('route_policy_digest')
    require(equivalent==old,'ROUTE_METADATA_CONTEXT_DRIFT')
    root=Path(repository_root).resolve()
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
    def route_at(sha):return json.loads(git('show',sha+':'+route_ref))
    old_route=route_at(old['repository']['head_sha']);new_route=route_at(new['repository']['head_sha'])
    require(old_route.get('work_items')==new_route.get('work_items'),'ROUTE_METADATA_WORK_ITEMS_CHANGED')
    for key in ('workflow_mode','runtime_epoch','communication_issue','intent_ref','intent_body_sha256'):
        require(old_route.get(key)==new_route.get(key),'ROUTE_METADATA_POLICY_KEY_CHANGED')
    for key,value in old_route.items():
        if key=='work_items':continue
        require(key in new_route and new_route[key]==value,'ROUTE_METADATA_DELTA_NOT_ADDITIVE')
    require(git('rev-parse','HEAD')==new['repository']['head_sha'] and
            git('branch','--show-current')==new['repository']['branch'] and
            root==Path(new['repository']['worktree']).resolve(),'ENGINEERING_RECONCILE_GIT_BINDING_REQUIRED')
    subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',
                    old['repository']['head_sha'],new['repository']['head_sha']],check=True)
    with _connect(old['workflow']['checkpoint_ref']) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT context_digest,state FROM engineering_workflow WHERE run=?',(old['run']['id'],)).fetchone()
        if row is None:raise ValueError('ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
        require(row[0]==digest(old),'ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
        db.execute('CREATE TABLE IF NOT EXISTS engineering_source_reconciliations (key TEXT PRIMARY KEY, receipt TEXT, prior_state TEXT)')
        receipt={'old_context_digest':digest(old),'new_context_digest':digest(new),
                 'old_head':old['repository']['head_sha'],'new_head':new['repository']['head_sha'],
                 'reason':reason,'route_metadata_delta':True,'route_ref':route_ref,
                 'old_route_policy_digest':old_eng.get('route_policy_digest'),
                 'new_route_policy_digest':new_eng.get('route_policy_digest'),
                 'added_route_keys':sorted(set(new_route)-set(old_route))}
        db.execute('INSERT INTO engineering_source_reconciliations VALUES (?,?,?)',(digest(receipt),json.dumps(receipt),row[1]))
        db.execute('UPDATE engineering_workflow SET context_digest=? WHERE run=? AND context_digest=?',
                   (digest(new),old['run']['id'],digest(old)));db.commit()
    with _connect(old['workflow']['checkpoint_ref']) as reader:
        require(reader.execute('SELECT context_digest FROM engineering_workflow WHERE run=?',(old['run']['id'],)).fetchone()[0]==digest(new),
                'ENGINEERING_RECONCILE_DURABLE_READBACK_FAILED')
    return receipt


def invalidate_engineering_work(checkpoint_ref,run,fingerprint,*,reason):
    """Mark a work row INVALID when its evidence does not support the result.

    The row and its artifact are preserved; the correction is recorded so the
    frontier re-selects the work instead of trusting a false verification.
    """
    import datetime
    require(isinstance(reason,str) and bool(reason.strip()),'WORK_INVALIDATION_REASON_REQUIRED')
    with _connect(checkpoint_ref) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT status FROM engineering_work WHERE run=? AND fingerprint=?',
                       (run,fingerprint)).fetchone()
        require(row is not None,'WORK_INVALIDATION_NOT_FOUND')
        require(row[0]!='INVALID','WORK_INVALIDATION_ALREADY_INVALID')
        db.execute('CREATE TABLE IF NOT EXISTS engineering_work_corrections '
                   '(key TEXT PRIMARY KEY, run TEXT, fingerprint TEXT, prior_status TEXT, reason TEXT, at TEXT)')
        receipt={'run':run,'fingerprint':fingerprint,'prior_status':row[0],'new_status':'INVALID','reason':reason}
        db.execute('INSERT OR REPLACE INTO engineering_work_corrections VALUES (?,?,?,?,?,?)',
                   (digest(receipt),run,fingerprint,row[0],reason,
                    datetime.datetime.now(datetime.timezone.utc).isoformat()))
        db.execute('UPDATE engineering_work SET status=? WHERE run=? AND fingerprint=?',
                   ('INVALID',run,fingerprint))
        db.commit()
    with _connect(checkpoint_ref) as reader:
        require(reader.execute('SELECT status FROM engineering_work WHERE run=? AND fingerprint=?',
                               (run,fingerprint)).fetchone()[0]=='INVALID','WORK_INVALIDATION_READBACK_FAILED')
    return receipt


def reconcile_interrupted_invocation(checkpoint_ref,run,invocation_key,*,reason):
    """Release an owner's interrupted invocation that never produced a result.

    Only a row with a NULL result may be released: it records no verified work.
    The release itself is written to engineering_source_reconciliations so the
    interruption stays auditable.
    """
    require(isinstance(reason,str) and bool(reason.strip()),'INVOCATION_RECONCILE_REASON_REQUIRED')
    with _connect(checkpoint_ref) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT binding,result FROM engineering_invocations WHERE run=? AND key=?',
                       (run,invocation_key)).fetchone()
        require(row is not None,'INVOCATION_RECONCILE_NOT_FOUND')
        require(row[1] is None,'INVOCATION_RECONCILE_HAS_RESULT')
        db.execute('CREATE TABLE IF NOT EXISTS engineering_source_reconciliations (key TEXT PRIMARY KEY, receipt TEXT, prior_state TEXT)')
        receipt={'kind':'INTERRUPTED_INVOCATION_RELEASED','run':run,'invocation_key':invocation_key,
                 'binding':row[0],'reason':reason}
        db.execute('INSERT INTO engineering_source_reconciliations VALUES (?,?,?)',
                   (digest(receipt),json.dumps(receipt),None))
        db.execute('DELETE FROM engineering_invocations WHERE run=? AND key=?',(run,invocation_key))
        db.commit()
    with _connect(checkpoint_ref) as reader:
        require(reader.execute('SELECT 1 FROM engineering_invocations WHERE run=? AND key=?',
                               (run,invocation_key)).fetchone() is None,'INVOCATION_RECONCILE_READBACK_FAILED')
    return receipt


def reconcile_engineering_plan_transition(old_context,new_context,*,reason,repository_root,
                                          activation_receipt_ref):
    """Advance the SAME checkpoint from the predecessor plan to an ACTIVATED successor.

    Allowed deltas: an ancestor head advance, the run's plan ref/digest, the
    engineering work items/route digest, and the task/runtime_plan bodies. The
    successor must be proven ACTIVATED by its durable receipt; the transition
    records a generation row used for crash recovery and readback.
    """
    import copy,subprocess,datetime
    from .q0_m1_m7_integration import resolve_active_plan
    old=validate_task_context(old_context);new=validate_task_context(new_context)
    require(isinstance(reason,str) and bool(reason.strip()),'PLAN_TRANSITION_REASON_REQUIRED')
    require(old['run']['id']==new['run']['id'],'PLAN_TRANSITION_RUN_MISMATCH')
    root=Path(repository_root).resolve()
    active=resolve_active_plan(root)
    require(active==new['run']['runtime_plan_ref'],'PLAN_TRANSITION_NOT_ACTIVATED')
    require((root/activation_receipt_ref).exists(),'PLAN_TRANSITION_RECEIPT_MISSING')
    equivalent=copy.deepcopy(new)
    equivalent['repository']['head_sha']=old['repository']['head_sha']
    equivalent['run']['runtime_plan_ref']=old['run']['runtime_plan_ref']
    equivalent['run']['runtime_plan_digest']=old['run']['runtime_plan_digest']
    if old.get('engineering') is not None and new.get('engineering') is not None:
        equivalent['engineering']['work_items']=old['engineering']['work_items']
        equivalent['engineering']['route_policy_digest']=old['engineering']['route_policy_digest']
    equivalent['task']=old['task']
    equivalent['runtime_plan']=old['runtime_plan']
    require(equivalent==old,'PLAN_TRANSITION_CONTEXT_DRIFT')
    plan_path=root/new['run']['runtime_plan_ref']
    require(plan_path.exists() and
            new['run']['runtime_plan_digest']=='sha256:'+hashlib.sha256(plan_path.read_bytes()).hexdigest(),
            'PLAN_TRANSITION_PLAN_DIGEST_MISMATCH')
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
    require(git('rev-parse','HEAD')==new['repository']['head_sha'],'PLAN_TRANSITION_GIT_BINDING_REQUIRED')
    if old['repository']['head_sha']!=new['repository']['head_sha']:
        subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',
                        old['repository']['head_sha'],new['repository']['head_sha']],check=True)
    with _connect(old['workflow']['checkpoint_ref']) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT context_digest,state FROM engineering_workflow WHERE run=?',(old['run']['id'],)).fetchone()
        if row is None:raise ValueError('ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
        require(row[0]==digest(old),'ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
        db.execute('CREATE TABLE IF NOT EXISTS engineering_source_reconciliations (key TEXT PRIMARY KEY, receipt TEXT, prior_state TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS engineering_plan_activation '
                   '(plan_ref TEXT PRIMARY KEY, plan_digest TEXT, context_digest TEXT, '
                   'generation INTEGER, activated_at TEXT)')
        generation=db.execute('SELECT COALESCE(MAX(generation),0)+1 FROM engineering_plan_activation').fetchone()[0]
        db.execute('INSERT OR REPLACE INTO engineering_plan_activation VALUES (?,?,?,?,?)',
                   (new['run']['runtime_plan_ref'],new['run']['runtime_plan_digest'],digest(new),generation,
                    datetime.datetime.now(datetime.timezone.utc).isoformat()))
        receipt={'old_context_digest':digest(old),'new_context_digest':digest(new),
                 'old_head':old['repository']['head_sha'],'new_head':new['repository']['head_sha'],
                 'reason':reason,'plan_transition':True,'activation_generation':generation,
                 'old_plan_ref':old['run']['runtime_plan_ref'],'new_plan_ref':new['run']['runtime_plan_ref'],
                 'old_plan_digest':old['run']['runtime_plan_digest'],'new_plan_digest':new['run']['runtime_plan_digest'],
                 'activation_receipt_ref':activation_receipt_ref}
        db.execute('INSERT INTO engineering_source_reconciliations VALUES (?,?,?)',(digest(receipt),json.dumps(receipt),row[1]))
        db.execute('UPDATE engineering_workflow SET context_digest=? WHERE run=? AND context_digest=?',
                   (digest(new),old['run']['id'],digest(old)))
        db.commit()
    with _connect(old['workflow']['checkpoint_ref']) as reader:
        require(reader.execute('SELECT context_digest FROM engineering_workflow WHERE run=?',(old['run']['id'],)).fetchone()[0]==digest(new),
                'ENGINEERING_RECONCILE_DURABLE_READBACK_FAILED')
        require(reader.execute('SELECT generation FROM engineering_plan_activation WHERE plan_ref=?',
                               (new['run']['runtime_plan_ref'],)).fetchone()[0]>=1,
                'ENGINEERING_RECONCILE_ACTIVATION_READBACK_FAILED')
    return receipt


def reconcile_engineering_worktree_relocation(old_context,new_context,*,reason):
    """Explicit relocation of the SAME run to another linked worktree.

    A canonical worktree move changes only ``repository.worktree``. The
    HEAD-only helper refuses it, so this path binds the relocation explicitly:
    every other context field must stay byte-identical, the new worktree must
    be the active checkout of the recorded branch/HEAD, and both paths must
    share one git common directory when the prior path still exists. All
    invocations, work rows, outbox rows and UNKNOWN statuses are preserved;
    nothing is erased, retried or replanned.
    """
    import copy,subprocess
    old=validate_task_context(old_context);new=validate_task_context(new_context)
    require(isinstance(reason,str) and bool(reason.strip()),'WORKTREE_RELOCATION_REASON_REQUIRED')
    old_wt=Path(old['repository']['worktree']).resolve();new_wt=Path(new['repository']['worktree']).resolve()
    require(old_wt!=new_wt,'WORKTREE_RELOCATION_UNCHANGED_WORKTREE')
    equivalent=copy.deepcopy(new)
    equivalent['repository']['worktree']=old['repository']['worktree']
    equivalent['repository']['head_sha']=old['repository']['head_sha']
    require(equivalent==old,'WORKTREE_RELOCATION_CONTEXT_DRIFT')
    def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
    require(git(new_wt,'rev-parse','HEAD')==new['repository']['head_sha'],'WORKTREE_RELOCATION_GIT_BINDING_REQUIRED')
    declared=new['repository'].get('branch') or ''
    actual=git(new_wt,'branch','--show-current')
    require(declared==actual,'WORKTREE_RELOCATION_BRANCH_MISMATCH')
    head_unchanged=old['repository']['head_sha']==new['repository']['head_sha']
    if not head_unchanged:
        subprocess.run(['git','-C',str(new_wt),'merge-base','--is-ancestor',
                        old['repository']['head_sha'],new['repository']['head_sha']],check=True)
    if old_wt.exists():
        def common_dir(root):
            value=Path(git(root,'rev-parse','--git-common-dir'))
            return (value if value.is_absolute() else (Path(root)/value)).resolve()
        if common_dir(old_wt)!=common_dir(new_wt):
            # A standalone clone relocating into a linked worktree of the same
            # repository has a distinct common dir; require one repository
            # identity before accepting the move.
            def origin(root):
                try:
                    url=git(root,'remote','get-url','origin')
                except subprocess.CalledProcessError:
                    url=str(Path(root).resolve())
                if url.startswith('/'):
                    return 'file://'+str(Path(url).resolve())
                # Keep the host: distinct Git hosts are distinct repositories
                # even when owner/repo coincide. Normalize user and .git only.
                tail=url.split('://',1)[-1] if '://' in url else url
                tail=tail.replace(':','/',1) if ':' in tail.split('/')[0] else tail
                parts=[part for part in tail.strip('/').split('/') if part]
                host=parts[0].split('@')[-1].lower()
                repo='/'.join(parts[-2:]).removesuffix('.git')
                return host+'/'+repo
            require(origin(old_wt)==origin(new_wt),'WORKTREE_RELOCATION_REPOSITORY_MISMATCH')
    with _connect(old['workflow']['checkpoint_ref']) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT context_digest,state FROM engineering_workflow WHERE run=?',(old['run']['id'],)).fetchone()
        if row is None:raise ValueError('ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
        require(row[0]==digest(old),'ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
        db.execute('CREATE TABLE IF NOT EXISTS engineering_source_reconciliations (key TEXT PRIMARY KEY, receipt TEXT, prior_state TEXT)')
        receipt={'old_context_digest':digest(old),'new_context_digest':digest(new),
                 'old_head':old['repository']['head_sha'],'new_head':new['repository']['head_sha'],
                 'head_unchanged':head_unchanged,'reason':reason,'worktree_relocation':True,
                 'old_worktree':str(old_wt),'new_worktree':str(new_wt)}
        db.execute('INSERT INTO engineering_source_reconciliations VALUES (?,?,?)',(digest(receipt),json.dumps(receipt),row[1]))
        db.execute('UPDATE engineering_workflow SET context_digest=? WHERE run=? AND context_digest=?',
                   (digest(new),old['run']['id'],digest(old)));db.commit()
    with _connect(old['workflow']['checkpoint_ref']) as reader:
        require(reader.execute('SELECT context_digest FROM engineering_workflow WHERE run=?',(old['run']['id'],)).fetchone()[0]==digest(new),
                'ENGINEERING_RECONCILE_DURABLE_READBACK_FAILED')
    return receipt
