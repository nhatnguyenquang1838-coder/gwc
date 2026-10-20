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
    def preflight(ctx,item):return {'prepared':True,'fingerprint':item['fingerprint']}
    def execute(ctx,item,prepared=None):
        counts['execute']+=1
        return {'exit_code':0,'result':'REAL_HOST_FIXTURE_RESULT','source_head':ctx['repository']['head_sha'],'stdout_digest':'sha256:'+'c'*64,'artifact_ref':'fixture-artifact','executed_effects':[]}
    return {'engineering.communication_read_once':read,'engineering.validate_context':lambda ctx:True,
            'engineering.execution_ready':lambda ctx,item:True,
            'engineering.preflight':preflight,'engineering.execute':execute,
            'engineering.verify_result':lambda ctx,item,result:result['exit_code']==0}


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
    # Native-owner admission halt is telemetry: no Controller decision request.
    assert r['graph_requests']==[]


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


def test_additive_route_metadata_requires_explicit_route_reconciliation(tmp_path):
    """A human-approved successor plan may add read-only route metadata.

    The HEAD-only helper must refuse the non-head drift, and an explicit,
    checksum-bound route-metadata reconciliation must advance the same
    checkpoint while preserving every invocation/work/outbox/UNKNOWN row.
    """
    import copy,json,subprocess,sqlite3
    from tools.node_architect.task_context_binding import digest as ctx_digest
    from tools.node_architect.engineering_m1_m7_workflow import (
        reconcile_engineering_source_head, reconcile_engineering_route_metadata)
    def git(*args):return subprocess.check_output(['git','-C',str(tmp_path),*args],text=True).strip()
    git('init','-b','fix/test')
    (tmp_path/'route.json').write_text(json.dumps({
        'workflow_mode':'Q0_ENGINEERING_COORDINATION','runtime_epoch':'UNIVERSAL_V2_DEVELOPMENT',
        'intent_ref':'intent-1','intent_body_sha256':'s',
        'work_items':[{'id':'login-probe','priority':1,'action':'run_sandboxed_validation',
                       'input_digest':'sha256:'+'b'*64,'provenance':'RECONSTRUCTED_REQUIREMENTS_BOUND'}]}))
    git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','base')
    route_ref='route.json'
    old_route=json.loads(git('show','HEAD:'+route_ref))
    c=binding(tmp_path)
    c['repository']['worktree']=str(tmp_path);c['repository']['branch']='fix/test'
    c['repository']['head_sha']=git('rev-parse','HEAD')
    c['engineering']['route_policy_ref']=route_ref
    c['engineering']['route_policy_digest']=ctx_digest(old_route)
    c['engineering']['work_items']=old_route['work_items']
    counts={'read':0,'execute':0};caps=capabilities(c,counts)
    run_task_workflow(c,host_capabilities=caps,invocation_key='route-one')
    new_route=copy.deepcopy(old_route)
    new_route['approved_successor_g1']={'target_change':'OPTION_B_CONTROLLED_FAILURE_CAMPAIGN',
                                        'human_approved':True,'activation_status':'PENDING'}
    (tmp_path/'route.json').write_text(json.dumps(new_route))
    git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','additive route metadata')
    newer=copy.deepcopy(c)
    newer['repository']['head_sha']=git('rev-parse','HEAD')
    newer['engineering']['route_policy_digest']=ctx_digest(new_route)
    # HEAD-only reconciliation must refuse a route-content delta.
    with pytest.raises(ValueError,match='ENGINEERING_RECONCILE_NON_HEAD_DRIFT'):
        reconcile_engineering_source_head(c,newer,repository_root=tmp_path,reason='fixture')
    receipt=reconcile_engineering_route_metadata(c,newer,repository_root=tmp_path,
        reason='fixture additive route metadata',route_ref=route_ref)
    assert receipt['route_metadata_delta'] is True
    assert receipt['old_route_policy_digest']==ctx_digest(old_route)
    assert receipt['new_route_policy_digest']==ctx_digest(new_route)
    r=run_task_workflow(newer,host_capabilities=caps,invocation_key='route-two')
    assert r['verdict']['reason_code']=='NO_MATERIAL_CHANGE'
    with sqlite3.connect(newer['workflow']['checkpoint_ref']) as db:
        assert db.execute('SELECT count(*) FROM engineering_invocations').fetchone()[0]==2
        assert db.execute('SELECT count(*) FROM engineering_work').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM engineering_source_reconciliations').fetchone()[0]>=1


def test_worktree_relocation_requires_explicit_reconciliation(tmp_path):
    """Moving the same run to a canonical linked worktree is a worktree-only delta.

    The HEAD-only helper must refuse it (worktree differs). An explicit
    relocation reconciliation must advance the same checkpoint, keep every
    invocation/work row, and refuse any other context delta.
    """
    import copy,json,subprocess,sqlite3
    from tools.node_architect.task_context_binding import digest as ctx_digest
    from tools.node_architect.engineering_m1_m7_workflow import (
        reconcile_engineering_source_head, reconcile_engineering_worktree_relocation)
    def git(*args,cwd=None):return subprocess.check_output(['git','-C',str(cwd or tmp_path),*args],text=True).strip()
    git('init','-b','fix/test')
    (tmp_path/'route.json').write_text(json.dumps({
        'workflow_mode':'Q0_ENGINEERING_COORDINATION','runtime_epoch':'UNIVERSAL_V2_DEVELOPMENT',
        'intent_ref':'intent-1','intent_body_sha256':'s',
        'work_items':[{'id':'login-probe','priority':1,'action':'run_sandboxed_validation',
                       'input_digest':'sha256:'+'b'*64,'provenance':'RECONSTRUCTED_REQUIREMENTS_BOUND'}]}))
    git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','base')
    route_ref='route.json';old_route=json.loads(git('show','HEAD:'+route_ref))
    c=binding(tmp_path);c['repository']['worktree']=str(tmp_path);c['repository']['branch']='fix/test'
    c['repository']['head_sha']=git('rev-parse','HEAD')
    c['engineering']['route_policy_ref']=route_ref
    c['engineering']['route_policy_digest']=ctx_digest(old_route)
    c['engineering']['work_items']=old_route['work_items']
    counts={'read':0,'execute':0};caps=capabilities(c,counts)
    run_task_workflow(c,host_capabilities=caps,invocation_key='reloc-one')
    # A second checkout of the same repository on the same branch and HEAD.
    linked=tmp_path.parent/'relocated-worktree'
    subprocess.check_output(['git','clone','-q',str(tmp_path),str(linked)],text=True)
    git('checkout','-q','-B','fix/test',cwd=linked)
    newer=copy.deepcopy(c);newer['repository']['worktree']=str(linked)
    with pytest.raises(ValueError,match='ENGINEERING_RECONCILE_NON_HEAD_DRIFT'):
        reconcile_engineering_source_head(c,newer,repository_root=linked,reason='fixture')
    # A detached checkout cannot satisfy a context that declares a branch.
    detached=tmp_path.parent/'detached-wt'
    git('worktree','add','-q','--detach',str(detached),'HEAD')
    detached_ctx=copy.deepcopy(newer);detached_ctx['repository']['worktree']=str(detached)
    with pytest.raises(ValueError,match='WORKTREE_RELOCATION_BRANCH_MISMATCH'):
        reconcile_engineering_worktree_relocation(c,detached_ctx,reason='fixture')
    # A non-worktree delta must still fail closed.
    drifted=copy.deepcopy(newer);drifted['repository']['branch']='fix/other'
    with pytest.raises(ValueError,match='WORKTREE_RELOCATION_CONTEXT_DRIFT'):
        reconcile_engineering_worktree_relocation(c,drifted,reason='fixture')
    receipt=reconcile_engineering_worktree_relocation(c,newer,reason='canonical relocation')
    assert receipt['worktree_relocation'] is True
    assert receipt['old_worktree']==str(tmp_path.resolve())
    assert receipt['new_worktree']==str(linked.resolve())
    assert receipt['head_unchanged'] is True
    r=run_task_workflow(newer,host_capabilities=caps,invocation_key='reloc-two')
    assert r['verdict']['reason_code']=='NO_MATERIAL_CHANGE'
    with sqlite3.connect(newer['workflow']['checkpoint_ref']) as db:
        assert db.execute('SELECT count(*) FROM engineering_invocations').fetchone()[0]==2
        assert db.execute('SELECT count(*) FROM engineering_work').fetchone()[0]==1


def test_worktree_relocation_accepts_standalone_clone_of_same_repository(tmp_path):
    """A standalone clone may relocate into a linked worktree of the same repo."""
    import copy,json,subprocess,sqlite3
    from tools.node_architect.task_context_binding import digest as ctx_digest
    from tools.node_architect.engineering_m1_m7_workflow import reconcile_engineering_worktree_relocation
    origin=tmp_path/'origin';origin.mkdir()
    def git(*args,cwd=None):return subprocess.check_output(['git','-C',str(cwd or origin),*args],text=True).strip()
    git('init','-b','fix/test')
    (origin/'route.json').write_text(json.dumps({'workflow_mode':'Q0_ENGINEERING_COORDINATION'}))
    git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','base')
    standalone=tmp_path/'standalone'
    subprocess.check_output(['git','clone','-q',str(origin),str(standalone)],text=True)
    git('checkout','-q','-B','fix/test',cwd=standalone)
    linked=origin.parent/'linked-wt'
    subprocess.check_output(['git','clone','-q',str(origin),str(linked)],text=True)
    git('checkout','-q','-B','fix/test',cwd=linked)
    c=binding(origin);c['repository']={'name':'fixture/repo','branch':'fix/test',
        'head_sha':git('rev-parse','HEAD'),'worktree':str(standalone)}
    c['engineering']['route_policy_digest']=ctx_digest({'workflow_mode':'Q0_ENGINEERING_COORDINATION'})
    counts={'read':0,'execute':0};caps=capabilities(c,counts)
    run_task_workflow(c,host_capabilities=caps,invocation_key='standalone-one')
    newer=copy.deepcopy(c);newer['repository']['worktree']=str(linked)
    receipt=reconcile_engineering_worktree_relocation(c,newer,reason='canonical relocation')
    assert receipt['new_worktree']==str(linked.resolve())
    assert receipt['head_unchanged'] is True


def test_worktree_relocation_rejects_same_repo_path_on_different_host(tmp_path):
    """Owner/repo equality alone must not merge two distinct Git hosts."""
    import copy,json,subprocess
    from tools.node_architect.task_context_binding import digest as ctx_digest
    from tools.node_architect.engineering_m1_m7_workflow import reconcile_engineering_worktree_relocation
    origin=tmp_path/'origin';origin.mkdir()
    def git(*args,cwd=None):return subprocess.check_output(['git','-C',str(cwd or origin),*args],text=True).strip()
    git('init','-b','fix/test');(origin/'route.json').write_text(json.dumps({'workflow_mode':'Q0_ENGINEERING_COORDINATION'}))
    git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','base')
    a=tmp_path/'clone-a';b=tmp_path/'clone-b'
    for path in (a,b):
        subprocess.check_output(['git','clone','-q',str(origin),str(path)],text=True)
        git('checkout','-q','-B','fix/test',cwd=path)
    git('remote','set-url','origin','https://host-a.example.com/owner/repo.git',cwd=a)
    git('remote','set-url','origin','https://host-b.example.com/owner/repo.git',cwd=b)
    c=binding(origin);c['repository']={'name':'owner/repo','branch':'fix/test',
        'head_sha':git('rev-parse','HEAD'),'worktree':str(a)}
    c['engineering']['route_policy_digest']=ctx_digest({'workflow_mode':'Q0_ENGINEERING_COORDINATION'})
    counts={'read':0,'execute':0};run_task_workflow(c,host_capabilities=capabilities(c,counts),invocation_key='host-one')
    moved=copy.deepcopy(c);moved['repository']['worktree']=str(b)
    with pytest.raises(ValueError,match='WORKTREE_RELOCATION_REPOSITORY_MISMATCH'):
        reconcile_engineering_worktree_relocation(c,moved,reason='fixture')


def test_route_metadata_reconciliation_rejects_non_additive_delta(tmp_path):
    """A route delta that changes existing keys or work_items must fail closed."""
    import copy,json,subprocess,sqlite3
    from tools.node_architect.task_context_binding import digest as ctx_digest
    from tools.node_architect.engineering_m1_m7_workflow import reconcile_engineering_route_metadata
    def git(*args):return subprocess.check_output(['git','-C',str(tmp_path),*args],text=True).strip()
    git('init','-b','fix/test')
    (tmp_path/'route.json').write_text(json.dumps({
        'workflow_mode':'Q0_ENGINEERING_COORDINATION','runtime_epoch':'UNIVERSAL_V2_DEVELOPMENT',
        'intent_ref':'intent-1','intent_body_sha256':'s',
        'work_items':[{'id':'login-probe','priority':1,'action':'run_sandboxed_validation',
                       'input_digest':'sha256:'+'b'*64,'provenance':'RECONSTRUCTED_REQUIREMENTS_BOUND'}]}))
    git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','base')
    route_ref='route.json';old_route=json.loads(git('show','HEAD:'+route_ref))
    c=binding(tmp_path);c['repository']['worktree']=str(tmp_path);c['repository']['branch']='fix/test'
    c['repository']['head_sha']=git('rev-parse','HEAD')
    c['engineering']['route_policy_ref']=route_ref
    c['engineering']['route_policy_digest']=ctx_digest(old_route)
    c['engineering']['work_items']=old_route['work_items']
    counts={'read':0,'execute':0};caps=capabilities(c,counts)
    run_task_workflow(c,host_capabilities=caps,invocation_key='route-nona')
    for delta in ({'workflow_mode':'PROTECTED_TYPED_CE'},
                  {'work_items':[{'id':'other','priority':1,'action':'run_sandboxed_validation','input_digest':'sha256:'+'d'*64}]},
                  {'intent_ref':'different-intent'}):
        new_route=copy.deepcopy(old_route);new_route.update(delta)
        (tmp_path/'route.json').write_text(json.dumps(new_route))
        git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','non additive delta')
        newer=copy.deepcopy(c)
        newer['repository']['head_sha']=git('rev-parse','HEAD')
        newer['engineering']['route_policy_digest']=ctx_digest(new_route)
        with pytest.raises(ValueError,match='ROUTE_METADATA_(DELTA_NOT_ADDITIVE|POLICY_KEY_CHANGED|WORK_ITEMS_CHANGED)'):
            reconcile_engineering_route_metadata(c,newer,repository_root=tmp_path,
                reason='fixture non additive delta',route_ref=route_ref)


def test_executor_crash_is_not_retried_on_another_invocation(tmp_path):
    import sqlite3
    c=binding(tmp_path);counts={'read':0,'execute':0};caps=capabilities(c,counts)
    def crash(ctx,item,prepared=None):
        counts['execute']+=1
        raise RuntimeError('fixture interruption')
    caps['engineering.execute']=crash
    run_task_workflow(c,host_capabilities=caps,invocation_key='crash')
    r=run_task_workflow(c,host_capabilities=caps,invocation_key='after-crash')
    assert counts['execute']==1
    assert r['verdict']['reason_code']=='ENGINEERING_EXECUTION_RECONCILIATION_REQUIRED'
    with sqlite3.connect(c['workflow']['checkpoint_ref']) as db:
        assert db.execute('SELECT status FROM engineering_work WHERE run=?',(c['run']['id'],)).fetchone()[0]=='UNKNOWN'


def test_preflight_failure_is_recorded_as_no_effect_and_retryable_on_same_fingerprint(tmp_path):
    import json,sqlite3
    c=binding(tmp_path);counts={'read':0,'execute':0,'preflight':0};caps=capabilities(c,counts)
    def preflight(ctx,item):
        counts['preflight']+=1
        if counts['preflight']==1:raise ValueError('ENGINEERING_INPUT_DIGEST_DRIFT')
        return {'prepared':True,'fingerprint':item['fingerprint']}
    caps['engineering.preflight']=preflight
    first=run_task_workflow(c,host_capabilities=caps,invocation_key='preflight-failure')
    assert first['activity_results']['M5']['reason_code']=='ENGINEERING_PRE_EFFECT_VALIDATION_FAILED'
    assert counts=={'read':1,'execute':0,'preflight':1}
    with sqlite3.connect(c['workflow']['checkpoint_ref']) as db:
        status,result=db.execute('SELECT status,result FROM engineering_work WHERE run=?',(c['run']['id'],)).fetchone()
    detail=json.loads(result)
    assert status=='PRE_EFFECT_VALIDATION_FAILED'
    assert detail['effect_started'] is False and detail['reason_code']=='ENGINEERING_INPUT_DIGEST_DRIFT'
    assert first['terminal']['pre_effect_failure']==detail
    assert first['terminal']['controller_dispatch_required'] is False
    assert first['graph_requests']==[]
    import sqlite3 as _s
    with _s.connect(c['workflow']['checkpoint_ref']) as db:
        row=db.execute('SELECT request_created FROM engineering_firing_telemetry WHERE run=?',(c['run']['id'],)).fetchone()
    assert row==(0,)  # telemetry recorded, no Controller decision request
    retry=run_task_workflow(c,host_capabilities=caps,invocation_key='same-fingerprint-recovery')
    assert retry['activity_results']['M5']['status']=='PASS'
    assert retry['activity_results']['M6']['status']=='PASS'
    assert counts=={'read':2,'execute':1,'preflight':2}
    with sqlite3.connect(c['workflow']['checkpoint_ref']) as db:
        status,result=db.execute('SELECT status,result FROM engineering_work WHERE run=?',(c['run']['id'],)).fetchone()
    record=json.loads(result);history=record['attempt_history']
    assert status=='VERIFIED'
    assert history[0]['status']=='PRE_EFFECT_VALIDATION_FAILED'
    assert history[0]['reason_code']=='ENGINEERING_INPUT_DIGEST_DRIFT'
    assert history[1]['status']=='PREFLIGHT_PASSED' and history[1]['effect_started'] is False
    assert history[2]['status']=='EXECUTED'


def test_same_fingerprint_pre_effect_recovery_claim_is_atomic(tmp_path):
    import json,sqlite3,threading
    c=binding(tmp_path);counts={'read':0,'execute':0,'preflight':0};caps=capabilities(c,counts)
    def fail_once(ctx,item):
        counts['preflight']+=1
        raise ValueError('ENGINEERING_INPUT_DIGEST_DRIFT')
    caps['engineering.preflight']=fail_once
    run_task_workflow(c,host_capabilities=caps,invocation_key='preflight-failure')
    barrier=threading.Barrier(2);started=threading.Event();release=threading.Event();any_done=threading.Event();lock=threading.Lock()
    def recovered_preflight(ctx,item):
        with lock:counts['preflight']+=1
        barrier.wait(timeout=5)
        return {'prepared':True,'fingerprint':item['fingerprint']}
    def slow_execute(ctx,item,prepared=None):
        with lock:counts['execute']+=1
        started.set()
        assert release.wait(timeout=5)
        return {'exit_code':0,'result':'REAL_HOST_FIXTURE_RESULT','source_head':ctx['repository']['head_sha'],
                'stdout_digest':'sha256:'+'c'*64,'artifact_ref':'fixture-artifact','executed_effects':[]}
    caps['engineering.preflight']=recovered_preflight;caps['engineering.execute']=slow_execute
    results={}
    def worker(key):
        results[key]=run_task_workflow(c,host_capabilities=caps,invocation_key=key)
        any_done.set()
    threads=[threading.Thread(target=worker,args=(f'recovery-{n}',)) for n in range(2)]
    for thread in threads:thread.start()
    assert started.wait(timeout=5)
    assert any_done.wait(timeout=5)  # the losing invocation must observe IN_FLIGHT and return
    release.set()
    for thread in threads:thread.join(timeout=5);assert not thread.is_alive()
    assert counts['execute']==1
    assert sorted(r['activity_results']['M5']['reason_code'] for r in results.values())==[
        'ACTUAL_HOST_VALIDATION_EXECUTED','ENGINEERING_EXECUTION_RECONCILIATION_REQUIRED']
    with sqlite3.connect(c['workflow']['checkpoint_ref']) as db:
        status,result=db.execute('SELECT status,result FROM engineering_work WHERE run=?',(c['run']['id'],)).fetchone()
    record=json.loads(result);history=record['attempt_history']
    assert status=='VERIFIED'
    assert [item['status'] for item in history]==['PRE_EFFECT_VALIDATION_FAILED','PREFLIGHT_PASSED','EXECUTED']


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


def test_m8_reserves_a_host_coordination_request_per_firing(tmp_path):
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
    # Same blocker, later firing: a fresh request is reserved for that firing
    # (mandatory per-turn response) while the first stays open for its owner.
    assert len(second['graph_requests'])==1
    assert second['graph_requests'][0]['marker']!=req['marker']
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
    # The correlated response is recorded AND this firing still reports its own result.
    assert len(second['graph_requests'])==1
    assert second['graph_requests'][0]['marker']!=req['marker']
    assert [r['marker'] for r in second['pending_controller_exchange_requests']]==[second['graph_requests'][0]['marker']]
    assert second['verdict']['status']=='WAIT'
    assert counts['execute']==0


def test_m8_records_telemetry_without_a_second_request_while_exchange_pending(tmp_path):
    import sqlite3
    from tools.node_architect.controller_exchange_adapter import ExchangeOutbox
    c=binding(tmp_path);counts={'read':0,'execute':0};caps=capabilities(c,counts)
    first=run_task_workflow(c,host_capabilities=caps,invocation_key='work-and-m7')
    original=first['graph_requests'][0]
    assert original['lane']=='HOST_COORDINATION'
    second=run_task_workflow(c,host_capabilities=caps,invocation_key='m3-after-m7')
    assert second['verdict']['current_activity']=='M8'
    # ACK #69: an unchanged/non-material firing records telemetry only.
    assert second['graph_requests']==[]
    assert second['terminal_exchange_request'] is None
    box=ExchangeOutbox(c['workflow']['checkpoint_ref']+'.engineering-exchange.sqlite')
    assert box.read(original)['status']=='EXCHANGE_REQUESTED'
    with sqlite3.connect(box.path) as db:
        assert db.execute('SELECT count(*) FROM exchange').fetchone()[0]==1
    with sqlite3.connect(c['workflow']['checkpoint_ref']) as db:
        rows=db.execute('SELECT firing,request_created FROM engineering_firing_telemetry ORDER BY firing').fetchall()
    assert ('m3-after-m7',0) in rows


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


def test_terminal_blocker_identity_is_stable_but_each_firing_reports(tmp_path):
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
    # Same blocker, new firing: the response obligation is per-turn, so the
    # second firing reserves its own request while the blocker identity stays stable.
    assert second['terminal_exchange_request']['marker']!=original['marker']
    assert second['graph_requests']==[second['terminal_exchange_request']]
    assert second['terminal_exchange_status']=='EXCHANGE_REQUESTED'
    box=ExchangeOutbox(c['workflow']['checkpoint_ref']+'.engineering-exchange.sqlite')
    with sqlite3.connect(box.path) as db:
        assert db.execute('SELECT count(*) FROM exchange').fetchone()[0]==2
