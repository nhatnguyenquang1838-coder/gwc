"""Generic task-bound runner over the existing, unchanged M1-M7 activities.

Host coordination is OUTSIDE graph dependencies. It may request a user-authorized
browser review while M1 holds, but cannot mark M1 passed or settle a native tick.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from .task_context_binding import validate_task_context, digest, require, ACTIVITIES
from .controller_exchange_adapter import make_exchange_request


def reconcile_source_head(old_context,new_context,*,repository_root,reason):
    """Explicit source-only additive transition while the graph is held at M1.

    Never rebinds a URL/session/plan, replays effects, updates native scheduler
    state or edits an old invocation. Preserves the prior row in an audit table.
    """
    import copy
    import subprocess
    old=validate_task_context(old_context);new=validate_task_context(new_context)
    require(isinstance(reason,str) and bool(reason.strip()),'SOURCE_RECONCILE_REASON_REQUIRED')
    comparison=copy.deepcopy(new)
    comparison['repository']['head_sha']=old['repository']['head_sha']
    require(comparison==old,'SOURCE_RECONCILE_NON_HEAD_DRIFT')
    before=old['repository']['head_sha'];after=new['repository']['head_sha']
    require(before!=after,'SOURCE_RECONCILE_UNCHANGED_HEAD')
    root=Path(repository_root).resolve()
    def git(*args):
        return subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True)
    branch=git('branch','--show-current');head=git('rev-parse','HEAD')
    require(branch.returncode==0 and head.returncode==0 and branch.stdout.strip()==new['repository']['branch'] and
            head.stdout.strip()==after and root==Path(new['repository']['worktree']).resolve(), 'SOURCE_RECONCILE_GIT_BINDING_REQUIRED')
    require(git('merge-base','--is-ancestor',before,after).returncode==0,'SOURCE_RECONCILE_NON_ADDITIVE_HEAD')
    with sqlite3.connect(old['workflow']['checkpoint_ref'],timeout=10) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT context_digest,state FROM workflow WHERE run=?',(old['run']['id'],)).fetchone()
        if row is None:
            raise ValueError('SOURCE_RECONCILE_PRIOR_CONTEXT_MISMATCH')
        require(row[0]==digest(old),'SOURCE_RECONCILE_PRIOR_CONTEXT_MISMATCH')
        state=json.loads(row[1]);verdict=state['verdict']
        require(verdict=={'current_activity':'M1','status':'HOLD','reason_code':'OBSERVER_UNQUALIFIED'} and
                not state.get('graph_state',{}).get('executed_effects'), 'SOURCE_RECONCILE_M1_HOLD_REQUIRED')
        for target in [state['checkpoint_projection'],state.get('graph_state',{}).get('operation_envelope',{})]:
            for key in ('base_sha','head_sha'):
                if key in target:
                    require(target[key]==before,'SOURCE_RECONCILE_PROJECTION_MISMATCH')
                    target[key]=after
        receipt={'operation':'SOURCE_HEAD_RECONCILIATION','old_context_digest':digest(old),
                 'new_context_digest':digest(new),'old_head':before,'new_head':after,
                 'reason':reason,'run_id':old['run']['id'],'session_id':old['executor']['session_id'],
                 'typed_ce_admitted':False,'native_state_modified':False,'prior_state_digest':digest(json.loads(row[1]))}
        db.execute('CREATE TABLE IF NOT EXISTS source_reconciliations (key TEXT PRIMARY KEY, prior_state TEXT, receipt TEXT)')
        db.execute('INSERT INTO source_reconciliations VALUES (?,?,?)',(digest(receipt),row[1],json.dumps(receipt,sort_keys=True)))
        cur=db.execute('UPDATE workflow SET context_digest=?,state=? WHERE run=? AND context_digest=? AND state=?',
                       (digest(new),json.dumps(state,sort_keys=True),old['run']['id'],row[0],row[1]))
        require(cur.rowcount==1,'SOURCE_RECONCILE_CAS_CONFLICT')
        db.commit()
    with sqlite3.connect(old['workflow']['checkpoint_ref'],timeout=10) as reader:
        require(reader.execute('SELECT context_digest FROM workflow WHERE run=?',(old['run']['id'],)).fetchone()[0]==digest(new),
                'SOURCE_RECONCILE_DURABLE_READBACK_FAILED')
    return {**receipt,'checkpoint_readback':'PASS'}



def build_task_graph(context):
    from langgraph.graph import END, START, StateGraph
    from . import m1_m7_agent_workflow as activity
    c = validate_task_context(context)
    profile = {'task_id':c['task']['id'],'repository':c['repository']['name'],
               'run_id':c['run']['id'],'base_sha':c['repository']['head_sha'],
               'working_branch':c['repository']['branch'],'scope_hash':digest(c['run']),
               'runtime_plan_digest':c['run']['runtime_plan_digest'],
               'authorized_paths':[], 'authorized_actions':[]}
    graph = StateGraph(activity.WorkflowState)
    graph.add_node('validate_operation',lambda s: activity._validate_operation_binding(s,profile))
    graph.add_edge(START,'validate_operation')
    graph.add_conditional_edges('validate_operation',activity._start_activity,{**{a:a for a in ACTIVITIES},END:END})
    handlers = {'M1':activity._m1_observe,'M2':activity._m2_validate,'M3':activity._m3_review,
                'M4':activity._m4_reconcile,'M5':lambda s:activity._m5_request_host_action(s,profile),
                'M6':activity._m6_verify_host_receipt}
    for index,name in enumerate(ACTIVITIES[:-1]):
        graph.add_node(name,handlers[name]); successor=ACTIVITIES[index+1]
        graph.add_conditional_edges(name,lambda s,n=successor:n if s.get('status')=='CONTINUE' else END,{successor:successor,END:END})
    def m7(state):
        result = activity._m7_settlement_request(state,profile)
        # Preserve settlement/mailbox semantics. A separate host request is data
        # only and is emitted solely when M7 was actually reached.
        report = (state.get('inputs') or {}).get('controller_report')
        if isinstance(report,str) and report.strip():
            result['controller_exchange_requests'] = [make_exchange_request(c,report,lane='M7')]
        return result
    graph.add_node('M7',m7);graph.add_edge('M7',END)
    return graph.compile(), profile


def run_task_workflow(context, *, host_capabilities, report='', coordination_authorized=False, invocation_key=None):
    c = validate_task_context(context);graph,profile = build_task_graph(c)
    operation = {k:profile[k] for k in ('task_id','repository','run_id','base_sha','working_branch','scope_hash','runtime_plan_digest')}
    operation.update(head_sha=operation['base_sha'],operation_id=c['run']['id']+':generic-m1-m7',
                     activity_id='task-workflow',protocol_version='dw.taskcontroller.continuation/v1',continuation_ref='',cursor={})
    # Only a trusted host provider can supply observation input. No public
    # observer_qualified flag and no browser-to-typed-admission conversion.
    provider = host_capabilities.get('typed_observer.read_verified')
    observation = provider(c,operation) if callable(provider) else None
    verifier = host_capabilities.get('typed_observer.verify')
    qualified = bool(observation is not None and callable(verifier) and verifier(c,operation,observation) is True)
    inputs = {'observer_qualified':qualified,'controller_report':report}
    if qualified:
        inputs['observer_receipt'] = observation
    initial = {'operation_envelope':operation,'inputs':inputs,'authority_granted':False,'executed_effects':[]}
    path = Path(c['workflow']['checkpoint_ref']);path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(str(path),timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS workflow (run TEXT PRIMARY KEY, context_digest TEXT, state TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS invocations (run TEXT, key TEXT, binding TEXT, result TEXT, PRIMARY KEY(run,key))')
        db.execute('BEGIN IMMEDIATE')
        invocation_binding = digest({'context':c,'report':report,'coordination_authorized':coordination_authorized})
        if invocation_key is not None:
            require(isinstance(invocation_key,str) and bool(invocation_key),'INVOCATION_KEY_INVALID')
            cached = db.execute('SELECT binding,result FROM invocations WHERE run=? AND key=?',(c['run']['id'],invocation_key)).fetchone()
            if cached:
                require(cached[0] == invocation_binding,'INVOCATION_BINDING_DRIFT')
                return {**json.loads(cached[1]),'invocation_replayed':True}
        prior = db.execute('SELECT context_digest,state FROM workflow WHERE run=?',(c['run']['id'],)).fetchone()
        if prior:
            require(prior[0] == digest(c),'TASK_CHECKPOINT_CONTEXT_DRIFT')
            old = json.loads(prior[1])
            initial.update(old.get('graph_state', {}))
            initial['operation_envelope'] = operation
            initial['inputs'] = inputs
            initial['checkpoint_projection'] = old['checkpoint_projection']
        raw = graph.invoke(initial)
        projection = {**operation,'current_activity':raw['current_activity']}
        state = {'checkpoint_projection':projection,
                 'graph_state':{k:v for k,v in raw.items() if k not in {'inputs','checkpoint_projection'}},
                 'verdict':{k:raw[k] for k in ('status','reason_code','current_activity')},
                 'activity_results':raw.get('activity_results',{}),'authority_granted':False}
        encoded = json.dumps(state,sort_keys=True)
        db.execute('INSERT OR REPLACE INTO workflow VALUES (?,?,?)',(c['run']['id'],digest(c),encoded))
        require(db.execute('SELECT state FROM workflow WHERE run=?',(c['run']['id'],)).fetchone()[0] == encoded,'TASK_CHECKPOINT_READBACK_FAILED')
        coordination = make_exchange_request(c,report,lane='HOST_COORDINATION') if coordination_authorized and report else None
        result = {'task_context_digest':digest(c),'verdict':state['verdict'], 'checkpoint_readback':'PASS',
                  'checkpoint_ref':str(path),'activity_results':state['activity_results'],
                  'graph_requests':raw.get('controller_exchange_requests',[]), 'coordination_request':coordination,
                  'host_admission':'QUALIFIED_HOST_OBSERVATION' if qualified else 'OBSERVER_UNQUALIFIED',
                  'typed_ce_admitted':False,'native_tick_settled':False,'executed_effects':[], 'invocation_replayed':False}
        if invocation_key is not None:
            db.execute('INSERT INTO invocations VALUES (?,?,?,?)',(c['run']['id'],invocation_key,invocation_binding,json.dumps(result)))
        db.commit()
        with sqlite3.connect(str(path),timeout=10) as reader:
            require(reader.execute('SELECT state FROM workflow WHERE run=?',(c['run']['id'],)).fetchone()[0] == encoded,
                    'TASK_CHECKPOINT_DURABLE_READBACK_FAILED')
        return result
