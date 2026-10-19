"""Generic engineering coordination, NOT the frozen protected typed workflow.

Host capabilities perform I/O; this graph owns orchestration only. Human
communication, engineering execution and protected typed authority are distinct.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import TypedDict,Any
from .task_context_binding import validate_task_context,digest,require,ACTIVITIES
from .controller_exchange_adapter import make_exchange_request,ExchangeOutbox

MODE='Q0_ENGINEERING_COORDINATION'
IDENTITY='generic-engineering-m1-m7/v1'


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
    terminal_exchange_request:dict
    terminal_exchange_status:str
    terminal_digest:str
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
    def m2(s):
        if c.get('engineering',{}).get('intent_body_sha256') not in (None,s['communication']['body_sha256']):
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
                key=digest(item);row=db.execute('SELECT status FROM engineering_work WHERE run=? AND fingerprint=?',(run,key)).fetchone()
                if not row or row[0]!='VERIFIED':
                    return outcome(s,'M3','PASS','PLAN_PRIORITIZED_WORK_SELECTED',work={**item,'fingerprint':key})
        frontier=host_capabilities.get('engineering.work_frontier')
        if callable(frontier):
            projection=frontier(c)
            require(projection.get('source_head')==c['repository']['head_sha'] and
                    projection.get('runtime_plan_digest')==c['run']['runtime_plan_digest'] and
                    projection.get('authority_granted') is False,'ENGINEERING_FRONTIER_BINDING_INVALID')
            item=projection.get('selected_work')
            if item:
                key=digest(item)
                with _connect(path) as db:
                    row=db.execute('SELECT status FROM engineering_work WHERE run=? AND fingerprint=?',(run,key)).fetchone()
                if not row or row[0]!='VERIFIED':
                    return outcome(s,'M3','PASS','PLAN_DRIVEN_FRONTIER_SELECTED',work={**item,'fingerprint':key},work_frontier=projection)
            return outcome(s,'M3','WAIT','ENGINEERING_FRONTIER_WAIT_INPUT',work_frontier=projection)
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
        ready=host_capabilities.get('engineering.execution_ready')
        if not callable(ready) or ready(c,item) is not True:
            return outcome(s,'M5','WAIT','ENGINEERING_GENUINE_FIRING_REQUIRED')
        with _connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status,result FROM engineering_work WHERE run=? AND fingerprint=?',(run,item['fingerprint'])).fetchone()
            if row:
                if row[0] in {'EXECUTED','VERIFIED'}:
                    return outcome(s,'M5','PASS','ENGINEERING_PRIOR_EXECUTION_REUSED',execution=json.loads(row[1]))
                return outcome(s,'M5','WAIT','ENGINEERING_EXECUTION_RECONCILIATION_REQUIRED')
            db.execute('INSERT INTO engineering_work VALUES (?,?,?,NULL)',(run,item['fingerprint'],'IN_FLIGHT'));db.commit()
        try:r=execute(c,item)
        except Exception as exc:
            with _connect(path) as db:db.execute('UPDATE engineering_work SET status=?,result=? WHERE run=? AND fingerprint=?',('UNKNOWN',json.dumps({'exception_type':type(exc).__name__}),run,item['fingerprint']))
            return outcome(s,'M5','WAIT','ENGINEERING_EXECUTION_RECONCILIATION_REQUIRED')
        with _connect(path) as db:db.execute('UPDATE engineering_work SET status=?,result=? WHERE run=? AND fingerprint=?',('EXECUTED',json.dumps(r,sort_keys=True),run,item['fingerprint']))
        return outcome(s,'M5','PASS','ACTUAL_HOST_VALIDATION_EXECUTED',execution=r)
    def m6(s):
        verify=host_capabilities.get('engineering.verify_result');r=s['execution']
        if not callable(verify) or verify(c,s['work'],r) is not True:
            return outcome(s,'M6','WAIT','ENGINEERING_EXECUTION_RESULT_NOT_VERIFIED')
        require(r.get('source_head')==c['repository']['head_sha'] and r.get('artifact_ref') and r.get('stdout_digest') and
                r.get('executed_effects')==[],'ENGINEERING_RESULT_BINDING_INVALID')
        with _connect(path) as db:db.execute('UPDATE engineering_work SET status=? WHERE run=? AND fingerprint=?',('VERIFIED',run,s['work']['fingerprint']))
        return outcome(s,'M6','PASS','ACTUAL_EXECUTION_ARTIFACT_VERIFIED')
    def m7(s):
        report=f"{c['task']['id']} engineering coordination; run {run}; session {c['executor']['session_id']}; source {c['repository']['head_sha']}. Actual work {s['work']['id']}: {s['execution']['result']}; artifact {s['execution']['artifact_ref']}. Human command seq {s['communication']['seq']}. Protected typed C/E remains separately gated. No original replay, LOAD_PROOF or Q0 L3 claimed. Please review result and return the smallest source-bound NEXT."
        box=ExchangeOutbox(str(path)+'.engineering-exchange.sqlite')
        for pending in old.get('pending_controller_exchange_requests',[]):
            prior_receipt=box.read(pending)
            if prior_receipt['status']!='CONTROLLER_RESPONSE_VERIFIED' and not (prior_receipt.get('receipt') or {}).get('response_complete_observed'):
                return outcome(s,'M7','WAIT','ENGINEERING_PRIOR_EXCHANGE_PENDING',controller_exchange_requests=[pending])
        request=make_exchange_request(c,report,lane='HOST_COORDINATION')
        with _connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS engineering_exchange_contexts (digest TEXT PRIMARY KEY, context TEXT)')
            db.execute('INSERT OR IGNORE INTO engineering_exchange_contexts VALUES (?,?)',(digest(c),json.dumps(c,sort_keys=True)))
        box.reserve(request)
        return outcome(s,'M7','WAIT','ENGINE_HOST_REPORT_AND_EXCHANGE_REQUIRED',
                        controller_exchange_requests=[request],
                        terminal={'kind':'ENGINEERING_TERMINAL_RESULT','activity':'M7',
                                  'reason_code':'ENGINEERING_HOST_REPORT_AND_EXCHANGE_REQUIRED',
                                  'blocker':'Controller must consume the reserved HOST_COORDINATION exchange',
                                  'frontier_digest':digest(s.get('work_frontier') or {}),
                                  'work_id':s.get('work',{}).get('id'),
                                  'duplicate_guard':digest({'run':run,'activity':'M7','reason_code':'ENGINEERING_HOST_REPORT_AND_EXCHANGE_REQUIRED'})})
    graph:Any=StateGraph(EngineeringState)
    for name,handler in zip(ACTIVITIES,[m1,m2,m3,m4,m5,m6,m7]):graph.add_node(name,handler)
    graph.add_edge(START,'M1')
    for a,b in zip(ACTIVITIES,ACTIVITIES[1:]):graph.add_conditional_edges(a,lambda s,n=b:n if s['status']=='PASS' else 'M8',{b:b,'M8':'M8',END:END})
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
        terminal={'kind':'ENGINEERING_TERMINAL_RESULT','activity':s['current_activity'],
                  'reason_code':s['reason_code'],'status':s['status'],
                  'blocker':blocker,
                  'frontier':frontier,
                  'source_head':c['repository']['head_sha'],
                  'runtime_plan_digest':c['run']['runtime_plan_digest'],
                  'work_id':(s.get('work') or {}).get('id'),
                  'duplicate_guard':digest({'run':run,'activity':s['current_activity'],
                                             'reason_code':s['reason_code'],'source_head':c['repository']['head_sha']})}
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
        response_observation=None
        controller_exchange_requests=[]
        # M3 exhaustion is a Controller-planning handoff, not protected M7.
        # Reserve the exact deterministic request once; on later invocations
        # resume/read that same outbox record and never stage/send it again.
        if decision_packet is not None:
            box=ExchangeOutbox(str(path)+'.engineering-exchange.sqlite')
            prior=old.get('terminal_exchange_request')
            prior_terminal_digest=old.get('terminal_digest')
            if prior:
                prior_state=box.read(prior)
                terminal_exchange_status=prior_state['status']
                receipt=prior_state.get('receipt') or {}
                response_complete=(receipt.get('response_complete_observed') is True and
                    receipt.get('response_to_marker')==prior['marker'] and
                    receipt.get('request_digest')==prior['request_digest'])
                if prior_terminal_digest==terminal_digest:
                    terminal_exchange_request=prior
                    if response_complete:
                        from .engineering_work_frontier import classify_controller_observation
                        disposition=classify_controller_observation(receipt.get('response_text',''))
                        decision_packet['controller_disposition_observation']=disposition
                        response_observation={
                            'classification':'RENDERED_TEXT_CORRELATED_WEAK',
                            'request_digest':prior['request_digest'],
                            'response_to_marker':prior['marker'],
                            'response_sha256':digest(receipt.get('response_text','')),
                            'receipt_strength':receipt.get('receipt_strength'),
                            'assistant_turn_ref':receipt.get('assistant_turn_ref'),
                            'evidence_class':'HUMAN_COORDINATION_OBSERVATION_NOT_TYPED_NEXT',
                            'disposition_observation':disposition,
                            'authority_granted':False,'typed_ce_admitted':False,
                            'workflow_resume_allowed':False}
                    else:
                        controller_exchange_requests=[prior]
                elif not response_complete:
                    # One materially unchanged blocker has only one outstanding
                    # Controller request, even if the source head advanced.
                    terminal_exchange_request=prior
                    controller_exchange_requests=[prior]
                else:
                    prior=None
            if not prior:
                active_pending=None
                for outstanding in old.get('pending_controller_exchange_requests',[]):
                    outstanding_state=box.read(outstanding)
                    outstanding_receipt=outstanding_state.get('receipt') or {}
                    completed=(outstanding_state['status']=='CONTROLLER_RESPONSE_VERIFIED' or
                        (outstanding_receipt.get('response_complete_observed') is True and
                         outstanding_receipt.get('response_to_marker')==outstanding['marker'] and
                         outstanding_receipt.get('request_digest')==outstanding['request_digest']))
                    if not completed:
                        active_pending=outstanding
                        terminal_exchange_status=outstanding_state['status']
                        break
                if active_pending:
                    # Do not create a second browser request while any exact
                    # same-run Controller exchange is unresolved. Preserve and
                    # surface the original request/marker for its owner.
                    terminal['blocked_by_pending_exchange_marker']=active_pending['marker']
                    controller_exchange_requests=[active_pending]
                else:
                    report=(f"{c['task']['id']} Q0 terminal engineering result; run {run}; "
                            f"session {c['executor']['session_id']}; source {c['repository']['head_sha']}; "
                            f"terminal {terminal_digest}. No READY work remains. Proposal only: "
                            f"{json.dumps(decision_packet,sort_keys=True,separators=(',',':'))}. "
                            "No typed C/E admission, authority, plan mutation, original replay, LOAD_PROOF or L3 claim. "
                            "Please review and return a source-bound disposition; any acceptance-target change still requires an explicit human-approved immutable G1 revision.")
                    request=make_exchange_request(c,report,lane='HOST_COORDINATION')
                    with _connect(path) as db:
                        db.execute('CREATE TABLE IF NOT EXISTS engineering_exchange_contexts (digest TEXT PRIMARY KEY, context TEXT)')
                        db.execute('INSERT OR IGNORE INTO engineering_exchange_contexts VALUES (?,?)',
                                   (request['task_context_digest'],json.dumps(c,sort_keys=True)))
                    box.reserve(request)
                    terminal_exchange_request=request
                    terminal_exchange_status=box.read(request)['status']
                    controller_exchange_requests=[request]
        if response_observation is not None:
            terminal['controller_response_observation']=response_observation
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
            receipt=prior.get('receipt') or {}
            response_processed=(prior['status']=='CONTROLLER_RESPONSE_VERIFIED' or
                (receipt.get('response_complete_observed') is True and
                 receipt.get('response_to_marker')==request['marker'] and
                 receipt.get('request_digest')==request['request_digest']))
            if not response_processed:
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


def reconcile_engineering_source_head(old_context,new_context,*,repository_root,reason):
    """Explicit HEAD-only continuation; retains old invocations and effect claims."""
    import copy,subprocess
    old=validate_task_context(old_context);new=validate_task_context(new_context);equivalent=copy.deepcopy(new)
    equivalent['repository']['head_sha']=old['repository']['head_sha'];require(equivalent==old and reason,'ENGINEERING_RECONCILE_NON_HEAD_DRIFT')
    root=Path(repository_root).resolve()
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
    require(root==Path(new['repository']['worktree']).resolve() and git('rev-parse','HEAD')==new['repository']['head_sha'] and git('branch','--show-current')==new['repository']['branch'],'ENGINEERING_RECONCILE_GIT_BINDING_REQUIRED')
    subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',old['repository']['head_sha'],new['repository']['head_sha']],check=True)
    with _connect(old['workflow']['checkpoint_ref']) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT context_digest,state FROM engineering_workflow WHERE run=?',(old['run']['id'],)).fetchone()
        if row is None:raise ValueError('ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
        require(row[0]==digest(old),'ENGINEERING_RECONCILE_PRIOR_CONTEXT_MISMATCH')
        db.execute('CREATE TABLE IF NOT EXISTS engineering_source_reconciliations (key TEXT PRIMARY KEY, receipt TEXT, prior_state TEXT)')
        receipt={'old_context_digest':digest(old),'new_context_digest':digest(new),'old_head':old['repository']['head_sha'],'new_head':new['repository']['head_sha'],'reason':reason}
        db.execute('INSERT INTO engineering_source_reconciliations VALUES (?,?,?)',(digest(receipt),json.dumps(receipt),row[1]));db.execute('UPDATE engineering_workflow SET context_digest=? WHERE run=? AND context_digest=?',(digest(new),old['run']['id'],digest(old)));db.commit()
    with _connect(old['workflow']['checkpoint_ref']) as reader:
        require(reader.execute('SELECT context_digest FROM engineering_workflow WHERE run=?',(old['run']['id'],)).fetchone()[0]==digest(new),'ENGINEERING_RECONCILE_DURABLE_READBACK_FAILED')
    return receipt
