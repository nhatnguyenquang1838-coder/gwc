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
