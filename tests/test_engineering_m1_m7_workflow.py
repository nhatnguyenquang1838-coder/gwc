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


def test_missing_host_firing_admission_holds_before_work_claim(tmp_path):
    c=binding(tmp_path);counts={'read':0,'execute':0};caps=capabilities(c,counts)
    caps['engineering.execution_ready']=lambda ctx,item:False
    r=run_task_workflow(c,host_capabilities=caps,invocation_key='explicit-source-check')
    assert r['verdict']['reason_code']=='ENGINEERING_GENUINE_FIRING_REQUIRED'
    assert counts['execute']==0


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
