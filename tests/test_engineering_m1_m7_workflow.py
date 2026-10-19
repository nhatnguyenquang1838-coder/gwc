"""CORRECTION43: engineering route is not protected typed C/E admission."""
import pytest
from test_task_context_binding import context
from tools.node_architect.task_m1_m7_runner import run_task_workflow


def binding(tmp_path,task='TASK-A'):
    c=context(task);c['workflow']['checkpoint_ref']=str(tmp_path/'checkpoint.sqlite');c['workflow']['mode']='Q0_ENGINEERING_COORDINATION'
    c['communication']={'issue_ref':'github://owner/repo/issues/1'}
    c['runtime_plan']={'scope':{'allowed_actions':['run_sandboxed_validation']}}
    c['engineering']={'work_items':[{'id':'login-probe','priority':1,'action':'run_sandboxed_validation','input_digest':'sha256:'+'b'*64,'provenance':'RECONSTRUCTED_REQUIREMENTS_BOUND'}]}
    return c


def capabilities(c,counts):
    def read(ctx):
        counts['read']+=1
        return {'seq':43,'run_id':ctx['run']['id'],'kind':'CORRECTION','from':'GPT','to':'Hermes','issue_ref':ctx['communication']['issue_ref'],'comment_id':123,'body_sha256':'a'*64,'comment_url':'https://github.com/owner/repo/issues/1#issuecomment-123','evidence_class':'HUMAN_COMMUNICATION_ONLY'}
    def execute(ctx,item):
        counts['execute']+=1
        return {'exit_code':0,'result':'REAL_HOST_FIXTURE_RESULT','source_head':ctx['repository']['head_sha'],'stdout_digest':'sha256:'+'c'*64,'artifact_ref':'fixture-artifact','executed_effects':[]}
    return {'engineering.communication_read_once':read,'engineering.validate_context':lambda ctx:True,
            'engineering.execution_ready':lambda ctx,item:True,
            'engineering.execute':execute,'engineering.verify_result':lambda ctx,item,result:result['exit_code']==0}


@pytest.mark.parametrize('task',['TASK-A','TASK-B'])
def test_engineering_route_can_execute_without_typed_observer(tmp_path,task):
    c=binding(tmp_path,task);counts={'read':0,'execute':0}
    r=run_task_workflow(c,host_capabilities=capabilities(c,counts),invocation_key='synthetic-unit-key')
    assert r['activity_results']['M1']['status']=='PASS'
    assert r['activity_results']['M2']['status']=='PASS'
    assert r['activity_results']['M6']['status']=='PASS'
    assert r['workflow_identity']=='generic-engineering-m1-m7/v1'
    assert r['typed_ce_admitted'] is False
    assert counts=={'read':1,'execute':1}


def test_protected_mode_still_holds_without_typed_observer(tmp_path):
    c=binding(tmp_path);c['workflow']['mode']='PROTECTED_TYPED_CE'
    r=run_task_workflow(c,host_capabilities={},invocation_key='protected-fixture-key')
    assert r['verdict']['reason_code']=='OBSERVER_UNQUALIFIED'


def test_duplicate_invocation_and_work_cannot_reexecute(tmp_path):
    c=binding(tmp_path);counts={'read':0,'execute':0};caps=capabilities(c,counts)
    r=run_task_workflow(c,host_capabilities=caps,invocation_key='one')
    replay=run_task_workflow(c,host_capabilities=caps,invocation_key='one')
    assert replay['invocation_replayed'] is True and counts=={'read':1,'execute':1}
    run_task_workflow(c,host_capabilities=caps,invocation_key='two')
    assert counts=={'read':2,'execute':1}


def test_prohibited_effect_does_not_reach_executor(tmp_path):
    c=binding(tmp_path);c['engineering']['work_items'][0]['action']='deploy_approved_release';c['runtime_plan']['scope']['allowed_actions'].append('deploy_approved_release');counts={'read':0,'execute':0}
    r=run_task_workflow(c,host_capabilities=capabilities(c,counts),invocation_key='forbidden')
    assert r['verdict']['reason_code']=='ENGINEERING_EFFECT_AUTHORITY_REQUIRED'
    assert counts['execute']==0
    assert len(r['graph_requests'])==1  # A real effect-authority blocker is routed to Controller.


def test_missing_host_firing_admission_holds_before_work_claim(tmp_path):
    c=binding(tmp_path);counts={'read':0,'execute':0};caps=capabilities(c,counts)
    caps['engineering.execution_ready']=lambda ctx,item:False
    r=run_task_workflow(c,host_capabilities=caps,invocation_key='explicit-source-check')
    assert r['verdict']['reason_code']=='ENGINEERING_GENUINE_FIRING_REQUIRED'
    assert counts['execute']==0
    assert r['graph_requests']==[]  # Native-owner firing admission is not a Controller-planning blocker.


@pytest.mark.parametrize('admission',['missing','none','non_callable'])
def test_absent_callable_admission_cannot_execute_or_claim_work(tmp_path,admission):
    import sqlite3
    c=binding(tmp_path);counts={'read':0,'execute':0};caps=capabilities(c,counts)
    if admission=='missing':caps.pop('engineering.execution_ready')
    else:caps['engineering.execution_ready']=None if admission=='none' else True
    r=run_task_workflow(c,host_capabilities=caps,invocation_key='unadmitted-source-check')
    assert r['verdict']['reason_code']=='ENGINEERING_GENUINE_FIRING_REQUIRED'
    assert counts=={'read':1,'execute':0}
    with sqlite3.connect(c['workflow']['checkpoint_ref']) as db:
        assert db.execute('SELECT count(*) FROM engineering_work').fetchone()[0]==0


def test_head_change_requires_explicit_same_checkpoint_reconciliation(tmp_path):
    from copy import deepcopy
    import subprocess,sqlite3
    from tools.node_architect.engineering_m1_m7_workflow import reconcile_engineering_source_head
    def git(*args):return subprocess.check_output(['git','-C',str(tmp_path),*args],text=True).strip()
    git('init','-b','fix/test');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-m','base')
    old=binding(tmp_path);old['repository']['worktree']=str(tmp_path);old['repository']['head_sha']=git('rev-parse','HEAD')
    counts={'read':0,'execute':0};caps=capabilities(old,counts)
    run_task_workflow(old,host_capabilities=caps,invocation_key='one')
    git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-m','additive')
    new=deepcopy(old);new['repository']['head_sha']=git('rev-parse','HEAD')
    with pytest.raises(ValueError,match='ENGINEERING_CHECKPOINT_CONTEXT_DRIFT'):
        run_task_workflow(new,host_capabilities=caps,invocation_key='two')
    reconcile_engineering_source_head(old,new,repository_root=tmp_path,reason='fixture additive source')
    r=run_task_workflow(new,host_capabilities=caps,invocation_key='two')
    assert r['verdict']['reason_code']=='NO_MATERIAL_CHANGE'
    assert counts=={'read':2,'execute':1}
    with sqlite3.connect(new['workflow']['checkpoint_ref']) as db:
        assert db.execute('SELECT count(*) FROM engineering_invocations').fetchone()[0]==2


def test_executor_crash_is_not_retried_on_another_invocation(tmp_path):
    c=binding(tmp_path);counts={'read':0,'execute':0};caps=capabilities(c,counts)
    def crash(ctx,item):
        counts['execute']+=1
        raise RuntimeError('fixture interruption')
    caps['engineering.execute']=crash
    run_task_workflow(c,host_capabilities=caps,invocation_key='crash')
    r=run_task_workflow(c,host_capabilities=caps,invocation_key='after-crash')
    assert counts['execute']==1
    assert r['verdict']['reason_code']=='ENGINEERING_EXECUTION_RECONCILIATION_REQUIRED'


def test_terminal_result_dispatches_when_no_ready_work_remains(tmp_path):
    """RC1 repair: a non-PASS halt before M7 must still emit a structured
    ENGINEERING_TERMINAL_RESULT instead of vanishing into END with no blocker
    payload for the Controller. The verdict stays WAIT; only the evidence is new."""
    c=binding(tmp_path);c['engineering']['work_items']=[]  # nothing left to do
    r=run_task_workflow(c,host_capabilities=capabilities(c,{'read':0,'execute':0}),invocation_key='terminal')
    assert r['verdict']['status']=='WAIT'
    assert r['verdict']['reason_code']=='NO_MATERIAL_CHANGE'
    # M8 is the terminal dispatch node that absorbs the M3 halt; the original
    # halt activity is preserved inside the terminal payload.
    assert r['verdict']['current_activity']=='M8'
    assert r['terminal']['kind']=='ENGINEERING_TERMINAL_RESULT'
    assert r['terminal']['activity']=='M3'
    assert r['terminal']['source_head']==c['repository']['head_sha']
    assert r['terminal']['runtime_plan_digest']==c['run']['runtime_plan_digest']
    assert r['terminal']['work_id'] is None
    assert 'duplicate_guard' in r['terminal']


def test_terminal_result_preserves_blocked_reason_code(tmp_path):
    """M8 is a dispatch node, not a gate: a blocked verdict must not be
    converted to PASS by attaching a terminal payload."""
    c=binding(tmp_path);c['engineering']['work_items'][0]['action']='deploy_approved_release'
    c['runtime_plan']['scope']['allowed_actions'].append('deploy_approved_release')
    r=run_task_workflow(c,host_capabilities=capabilities(c,{'read':0,'execute':0}),invocation_key='blocked')
    assert r['verdict']['reason_code']=='ENGINEERING_EFFECT_AUTHORITY_REQUIRED'
    assert r['terminal']['activity']=='M5'
    assert r['terminal']['reason_code']=='ENGINEERING_EFFECT_AUTHORITY_REQUIRED'
    assert r['terminal']['blocker']


def test_m8_reserves_one_host_coordination_request_and_reuses_it(tmp_path):
    import sqlite3, json
    from tools.node_architect.controller_exchange_adapter import ExchangeOutbox
    c=binding(tmp_path);c['engineering']['work_items']=[]
    counts={'read':0,'execute':0};caps=capabilities(c,counts)
    frontier={'source_head':c['repository']['head_sha'],
              'runtime_plan_digest':c['run']['runtime_plan_digest'],
              'authority_granted':False,'selected_work':None,
              'items':[{'id':'trace','status':'BLOCKED_EXTERNAL_EVIDENCE',
                        'work':{'id':'trace','plan_node_id':'F2-INCIDENT-RED',
                                'missing_external_evidence':['authentic original trace']}}]}
    caps['engineering.work_frontier']=lambda ctx:frontier
    first=run_task_workflow(c,host_capabilities=caps,invocation_key='terminal-one')
    assert len(first['graph_requests'])==1
    req=first['graph_requests'][0]
    assert req['lane']=='HOST_COORDINATION'
    assert req['authority_granted'] is False and req['typed_ce_admitted'] is False
    assert first['terminal']['decision_packet']['proposal_only'] is True
    assert first['terminal']['decision_packet']['plan_mutated'] is False
    box=ExchangeOutbox(c['workflow']['checkpoint_ref']+'.engineering-exchange.sqlite')
    assert box.read(req)['status']=='EXCHANGE_REQUESTED'
    assert first['terminal_exchange_status']=='EXCHANGE_REQUESTED'
    with sqlite3.connect(c['workflow']['checkpoint_ref']) as db:
        rows=db.execute('SELECT state FROM engineering_workflow WHERE run=?',(c['run']['id'],)).fetchone()
        state=json.loads(rows[0])
        assert state['terminal']['kind']=='ENGINEERING_TERMINAL_RESULT'
        assert state['terminal_exchange_request']==req
        assert state['terminal_exchange_status']=='EXCHANGE_REQUESTED'
    with sqlite3.connect(box.path) as outbox_db:
        assert outbox_db.execute('SELECT count(*) FROM exchange').fetchone()[0]==1
    second=run_task_workflow(c,host_capabilities=caps,invocation_key='terminal-two')
    assert second['graph_requests']==[req]
    assert second['terminal_exchange_status']=='EXCHANGE_REQUESTED'
    assert box.read(req)['status']=='EXCHANGE_REQUESTED'
    assert counts['read']==2 and counts['execute']==0


def test_m8_correlates_response_as_observation_without_resuming_or_granting_authority(tmp_path):
    from tools.node_architect.controller_exchange_adapter import ExchangeOutbox
    c=binding(tmp_path);c['engineering']['work_items']=[]
    counts={'read':0,'execute':0};caps=capabilities(c,counts)
    frontier={'source_head':c['repository']['head_sha'],
              'runtime_plan_digest':c['run']['runtime_plan_digest'],
              'authority_granted':False,'selected_work':None,'items':[]}
    caps['engineering.work_frontier']=lambda ctx:frontier
    first=run_task_workflow(c,host_capabilities=caps,invocation_key='response-one')
    req=first['graph_requests'][0]
    box=ExchangeOutbox(c['workflow']['checkpoint_ref']+'.engineering-exchange.sqlite')
    base={k:req[k] for k in ['conversation_url','request_digest','marker','task_id','run_id','session_id']}
    base.update(user_turn_ref='user:'+req['marker'],evidence_class='BROWSER_EXCHANGE_VERIFIED',
                authority_granted=False,typed_ce_admitted=False)
    box.record(req,{**base,'status':'MESSAGE_SENT_VERIFIED'})
    box.record(req,{**base,'status':'CONTROLLER_ACTION_REQUIRED',
                    'response_to_marker':req['marker'],'response_text':'ACK #56 — SEARCH_EXHAUSTED / WAIT_EXTERNAL_EVIDENCE. No acceptance target changed.',
                    'assistant_turn_ref':'assistant:'+req['marker'],
                    'response_complete_observed':True,'strong_receipt_verified':False,
                    'workflow_resume_allowed':False,'receipt_strength':'RENDERED_TEXT_CORRELATION_ONLY'})
    second=run_task_workflow(c,host_capabilities=caps,invocation_key='response-two')
    observation=second['terminal']['controller_response_observation']
    assert observation['classification']=='RENDERED_TEXT_CORRELATED_WEAK'
    assert observation['response_to_marker']==req['marker']
    assert observation['authority_granted'] is False and observation['typed_ce_admitted'] is False
    assert observation['workflow_resume_allowed'] is False
    assert observation['disposition_observation']['disposition']=='SEARCH_EXHAUSTED_WAIT_EXTERNAL_EVIDENCE'
    assert observation['disposition_observation']['planning_state']=='WAIT_EXTERNAL_INPUT'
    assert observation['disposition_observation']['acceptance_target_changed'] is False
    assert second['decision_packet']['controller_disposition_observation']==observation['disposition_observation']
    assert second['graph_requests']==[]
    assert second['pending_controller_exchange_requests']==[]
    assert second['verdict']['status']=='WAIT'
    assert counts['execute']==0


def test_m8_does_not_create_second_request_while_m7_exchange_is_pending(tmp_path):
    import sqlite3
    from tools.node_architect.controller_exchange_adapter import ExchangeOutbox
    c=binding(tmp_path);counts={'read':0,'execute':0};caps=capabilities(c,counts)
    first=run_task_workflow(c,host_capabilities=caps,invocation_key='work-and-m7')
    original=first['graph_requests'][0]
    assert original['lane']=='HOST_COORDINATION'
    second=run_task_workflow(c,host_capabilities=caps,invocation_key='m3-after-m7')
    assert second['verdict']['current_activity']=='M8'
    assert second['terminal']['blocked_by_pending_exchange_marker']==original['marker']
    assert second['graph_requests']==[original]
    assert second['terminal_exchange_request'] is None
    box=ExchangeOutbox(c['workflow']['checkpoint_ref']+'.engineering-exchange.sqlite')
    assert box.read(original)['status']=='EXCHANGE_REQUESTED'
    with sqlite3.connect(box.path) as db:
        assert db.execute('SELECT count(*) FROM exchange').fetchone()[0]==1


def test_m7_uses_shared_marker_response_reconciliation_before_next_request(tmp_path):
    from tools.node_architect.controller_exchange_adapter import ExchangeOutbox
    c=binding(tmp_path);base=c['engineering']['work_items'][0]
    second={**base,'id':'login-probe-second','priority':2,'input_digest':'sha256:'+'e'*64}
    c['engineering']['work_items']=[base,second]
    counts={'read':0,'execute':0};caps=capabilities(c,counts)
    first=run_task_workflow(c,host_capabilities=caps,invocation_key='m7-response-one')
    request=first['graph_requests'][0]
    box=ExchangeOutbox(c['workflow']['checkpoint_ref']+'.engineering-exchange.sqlite')
    binding_fields={k:request[k] for k in ['conversation_url','request_digest','marker','task_id','run_id','session_id']}
    browser_base={**binding_fields,'user_turn_ref':'user:'+request['marker'],
                  'assistant_turn_ref':'assistant:'+request['marker'],
                  'evidence_class':'BROWSER_EXCHANGE_VERIFIED','authority_granted':False,'typed_ce_admitted':False}
    box.record(request,{**browser_base,'status':'MESSAGE_SENT_VERIFIED'})
    box.record(request,{**browser_base,'status':'CONTROLLER_ACTION_REQUIRED',
        'response_to_marker':request['marker'],'response_text':'ACK: SEARCH_EXHAUSTED / WAIT_EXTERNAL_EVIDENCE',
        'response_complete_observed':True,'receipt_strength':'RENDERED_TEXT_CORRELATION_ONLY',
        'strong_receipt_verified':False,'workflow_resume_allowed':False})
    second_result=run_task_workflow(c,host_capabilities=caps,invocation_key='m7-response-two')
    observation=second_result['controller_response_observation']
    assert observation['request_digest']==request['request_digest']
    assert observation['classification']=='RENDERED_TEXT_CORRELATED_WEAK'
    assert observation['authority_granted'] is False and observation['typed_ce_admitted'] is False
    assert observation['workflow_resume_allowed'] is False
    assert second_result['verdict']['reason_code']=='ENGINEERING_HOST_REPORT_AND_EXCHANGE_REQUIRED'


def test_m4_external_dependency_dispatches_terminal_result_to_controller(tmp_path):
    c=binding(tmp_path);c['engineering']['work_items'][0]['external_dependency']='controller-owned dependency'
    counts={'read':0,'execute':0}
    r=run_task_workflow(c,host_capabilities=capabilities(c,counts),invocation_key='m4-controller-blocker')
    assert r['activity_results']['M4']['reason_code']=='ENGINEERING_EXTERNAL_DEPENDENCY'
    assert r['terminal']['activity']=='M4'
    assert len(r['graph_requests'])==1
    assert r['graph_requests'][0]['lane']=='HOST_COORDINATION'
    assert 'controller-owned dependency' in r['graph_requests'][0]['report']
    assert r['authority_granted'] is False and r['typed_ce_admitted'] is False


def test_terminal_request_dedup_is_stable_across_additive_source_head(tmp_path):
    import copy,subprocess,sqlite3
    from tools.node_architect.engineering_m1_m7_workflow import reconcile_engineering_source_head
    from tools.node_architect.controller_exchange_adapter import ExchangeOutbox
    c=binding(tmp_path);c['repository']['worktree']=str(tmp_path);c['engineering']['work_items']=[]
    (tmp_path/'plan.json').write_text('{"plan":"frozen"}\n')
    def git(*args):return subprocess.check_output(['git','-C',str(tmp_path),*args],text=True).strip()
    git('init','-b',c['repository']['branch']);git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','base')
    c['repository']['head_sha']=git('rev-parse','HEAD')
    def frontier(ctx):
        return {'source_head':ctx['repository']['head_sha'],'runtime_plan_digest':ctx['run']['runtime_plan_digest'],
                'authority_granted':False,'selected_work':None,'items':[
                    {'id':'trace','status':'BLOCKED_EXTERNAL_EVIDENCE','work':{
                        'id':'trace','plan_node_id':'F2-INCIDENT-RED',
                        'missing_external_evidence':['authentic original trace']}}]}
    caps=capabilities(c,{'read':0,'execute':0});caps['engineering.work_frontier']=frontier
    first=run_task_workflow(c,host_capabilities=caps,invocation_key='terminal-head-one')
    original=first['terminal_exchange_request'];identity=first['terminal']['blocker_identity']
    git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-m','additive source change')
    newer=copy.deepcopy(c);newer['repository']['head_sha']=git('rev-parse','HEAD')
    reconcile_engineering_source_head(c,newer,repository_root=tmp_path,reason='fixture additive commit preserving same blocker')
    second=run_task_workflow(newer,host_capabilities=caps,invocation_key='terminal-head-two')
    assert second['terminal']['blocker_identity']==identity
    assert second['terminal_exchange_request']==original
    assert second['graph_requests']==[original]
    assert second['terminal_exchange_status']=='EXCHANGE_REQUESTED'
    box=ExchangeOutbox(c['workflow']['checkpoint_ref']+'.engineering-exchange.sqlite')
    with sqlite3.connect(box.path) as db:
        assert db.execute('SELECT count(*) FROM exchange').fetchone()[0]==1
