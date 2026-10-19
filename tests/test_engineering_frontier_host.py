
import pytest
from test_engineering_work_frontier import setup_frontier


def agent_fixture(tmp_path,recovery=True):
    import json,subprocess,hashlib
    from tools.node_architect.task_m1_m7_runner import run_task_workflow
    from test_engineering_m1_m7_workflow import capabilities
    from tools.node_architect.engineering_work_frontier import project_frontier
    c,items=setup_frontier(tmp_path);c['repository']['worktree']=str(tmp_path)
    c['engineering']['work_items']=[]
    item={**items[1],'plan_relation':'CONDITIONAL_RUNTIME_DEFECT_REPAIR_UNDER_EXISTING_RECOVERY_POLICY'}
    plan={'run_id':c['run']['id'],'branch':c['repository']['branch'],'scope':c['runtime_plan']['scope'],
          'recursive_plan':c['runtime_plan']['recursive_plan'],'implementation_mode':'continuous_tdd_self_remediation',
          'authority_basis':{'kind':'standing_q0_autonomous_development_policy'},'recovery_policy':'On GWC_RUNTIME_DEFECT use bounded same-branch repair.' if recovery else ''}
    (tmp_path/'tools').mkdir();(tmp_path/'tools/repair.py').write_text('VALUE = 0\n')
    (tmp_path/'agent-profile.json').write_text(json.dumps({'items':[{**item,'read_paths':['tools/repair.py']}]}))
    path=tmp_path/c['run']['runtime_plan_ref'];path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(plan))
    c['run']['runtime_plan_digest']='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
    def git(*args):return subprocess.check_output(['git','-C',str(tmp_path),*args],text=True).strip()
    git('init','-b',c['repository']['branch']);git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','base')
    c['repository']['head_sha']=git('rev-parse','HEAD');caps=capabilities(c,{'read':0,'execute':0})
    caps['engineering.work_frontier']=lambda ctx:project_frontier(ctx,[item],verified_fingerprints=[])
    r=run_task_workflow(c,host_capabilities=caps,invocation_key='agent-request')
    return c,r['host_action_request'],git


def test_agent_claim_blocks_duplicate_start_and_request_is_not_completion(tmp_path):
    import sqlite3
    from tools.node_architect.engineering_host_adapter import reserve_agent_work,start_agent_work
    c,r,_=agent_fixture(tmp_path)
    reserve_agent_work(c,r,guard=lambda:True);start_agent_work(c,r,guard=lambda:True)
    with pytest.raises(ValueError,match='AGENT_WORK_STATE_CONFLICT'):
        start_agent_work(c,r,guard=lambda:True)
    with sqlite3.connect(c['workflow']['checkpoint_ref']) as db:
        assert db.execute('SELECT status FROM engineering_work WHERE fingerprint=?',(r['work_fingerprint'],)).fetchone()[0]=='IN_FLIGHT'


def test_agent_completion_requires_actual_git_delta_and_log_readback(tmp_path):
    import json,subprocess,hashlib,sqlite3
    from tools.node_architect.engineering_host_adapter import reserve_agent_work,start_agent_work,record_agent_execution,verify_agent_execution
    c,r,git=agent_fixture(tmp_path);reserve_agent_work(c,r,guard=lambda:True);start_agent_work(c,r,guard=lambda:True)
    file=tmp_path/'tools/repair.py';file.write_text('VALUE = 1\n');git('add','tools/repair.py');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','repair')
    outdir=tmp_path/'engineering-agent-results';outdir.mkdir();log=outdir/'validation.log'
    actual=subprocess.run(['python','-c','print("unit fixture validation")'],capture_output=True,text=True);log.write_text(actual.stdout)
    payload={'request_digest':r['request_digest'],'base_head':r['source_head'],'result_head':git('rev-parse','HEAD'),
             'verification_exit_code':actual.returncode,'verification_log_ref':str(log),'verification_log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
    artifact=outdir/'execution.json';artifact.write_text(json.dumps(payload))
    record_agent_execution(c,r,artifact_ref=artifact,guard=lambda:True,profile_ref='agent-profile.json')
    log.write_text('corrupted fixture log')
    with pytest.raises(ValueError,match='AGENT_VERIFICATION_LOG_INVALID'):
        verify_agent_execution(c,r,artifact_ref=artifact,guard=lambda:True,profile_ref='agent-profile.json')
    log.write_text(actual.stdout)
    verify_agent_execution(c,r,artifact_ref=artifact,guard=lambda:True,profile_ref='agent-profile.json')
    import copy
    from tools.node_architect.engineering_host_adapter import read_source_bound_frontier
    current=copy.deepcopy(c);current['repository']['head_sha']=git('rev-parse','HEAD')
    projection=read_source_bound_frontier(current,profile_ref='agent-profile.json',guard=lambda:True)
    assert projection['selected_work'] is None and projection['items'][0]['status']=='VERIFIED'
    with sqlite3.connect(c['workflow']['checkpoint_ref']) as db:
        assert db.execute('SELECT status FROM engineering_work WHERE fingerprint=?',(r['work_fingerprint'],)).fetchone()[0]=='VERIFIED'
    with pytest.raises(ValueError,match='AGENT_WORK_STATE_CONFLICT'):
        verify_agent_execution(c,r,artifact_ref=artifact,guard=lambda:True)


def test_agent_rejects_root_shortcut_without_recovery_policy(tmp_path):
    import json
    from tools.node_architect.engineering_host_adapter import reserve_agent_work
    c,r,git=agent_fixture(tmp_path,recovery=False)
    with pytest.raises(ValueError,match='AGENT_CONDITIONAL_REPAIR_UNPROVEN'):
        reserve_agent_work(c,r,guard=lambda:True)


def test_interrupted_agent_work_cannot_restart(tmp_path):
    from tools.node_architect.engineering_host_adapter import reserve_agent_work,start_agent_work,quarantine_agent_work
    c,r,_=agent_fixture(tmp_path);reserve_agent_work(c,r,guard=lambda:True);start_agent_work(c,r,guard=lambda:True)
    quarantine_agent_work(c,r,guard=lambda:True,reason_code='HOST_RESULT_UNKNOWN')
    with pytest.raises(ValueError,match='AGENT_WORK_STATE_CONFLICT'):
        start_agent_work(c,r,guard=lambda:True)


def test_source_bound_host_frontier_loads_real_policy_and_trace_status(tmp_path):
    import json,subprocess
    from tools.node_architect.engineering_host_adapter import read_source_bound_frontier
    c,items=setup_frontier(tmp_path);c['repository']['worktree']=str(tmp_path)
    (tmp_path/'trace.json').write_text(json.dumps({'original_trace_status':'MISSING'}))
    (tmp_path/'code.py').write_text('# source-bound repair input\n')
    profile={'items':[{**items[0],'read_paths':['code.py'],'evidence_requirements':[{'path':'trace.json','field':'original_trace_status','equals':'RECOVERED','name':'original trace'}]},
                      {**items[1],'read_paths':['code.py']}]}
    (tmp_path/'profile.json').write_text(json.dumps(profile))
    def git(*args):return subprocess.check_output(['git','-C',str(tmp_path),*args],text=True).strip()
    git('init','-b','fix/test');git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','bound inputs')
    c['repository']['head_sha']=git('rev-parse','HEAD')
    r=read_source_bound_frontier(c,profile_ref='profile.json',guard=lambda:True)
    assert r['selected_work']['id']=='repair'
    assert next(i for i in r['items'] if i['id']=='trace')['status']=='BLOCKED_EXTERNAL_EVIDENCE'
    (tmp_path/'code.py').write_text('# drift\n')
    with pytest.raises(ValueError,match='ENGINEERING_FRONTIER_SOURCE_DRIFT'):
        read_source_bound_frontier(c,profile_ref='profile.json',guard=lambda:True)


def test_local_verifier_accepts_only_bound_terminal_bridge_suite_artifact(tmp_path):
    import json,hashlib
    from tools.node_architect.engineering_host_adapter import local_engineering_capabilities
    from tools.node_architect.task_context_binding import digest
    c,request,git=agent_fixture(tmp_path)
    caps=local_engineering_capabilities(c,guard=lambda:True,
        artifact_directory=tmp_path/'validation-results',
        allowed_commands=[['-m','pytest','tests/test_engineering_m1_m7_workflow.py','-q']])
    argv=['-m','pytest','tests/test_engineering_m1_m7_workflow.py','-q']
    item={'id':'bridge-validation','action':'run_sandboxed_validation','argv':argv,
          'verification_profile':'Q0_TERMINAL_RESULT_SUITE','required_test_files':['tests/test_engineering_m1_m7_workflow.py'],
          'minimum_tests_passed':1,'expected_result':'Q0_TERMINAL_RESULT_SUITE_PASS'}
    stdout='.................... [100%]\n20 passed in 0.42s\n'
    artifact=tmp_path/'validation-results'/'bridge.json';artifact.parent.mkdir(parents=True)
    payload={'argv':argv,'source_head':c['repository']['head_sha'],'exit_code':0,'stdout':stdout,'stderr':'','input_hashes':{}}
    artifact.write_text(json.dumps(payload,sort_keys=True))
    result={'artifact_ref':str(artifact),'artifact_digest':digest(payload),'stdout_digest':digest(stdout),'exit_code':0,'source_head':c['repository']['head_sha'],'result':'Q0_TERMINAL_RESULT_SUITE_PASS','executed_effects':[]}
    assert caps['engineering.verify_result'](c,item,result) is True
    bad=dict(payload);bad['argv']=['-c','print("not tests")'];artifact.write_text(json.dumps(bad,sort_keys=True))
    bad_result={**result,'artifact_digest':digest(bad)}
    assert caps['engineering.verify_result'](c,item,bad_result) is False


def test_host_executes_exact_terminal_bridge_suite_and_verifies_artifact(tmp_path):
    import hashlib,subprocess
    from tools.node_architect.engineering_host_adapter import local_engineering_capabilities
    from tools.node_architect.task_context_binding import digest
    c,_,git=agent_fixture(tmp_path)
    files=['tests/test_engineering_m1_m7_workflow.py','tests/test_engineering_work_frontier.py',
           'tests/test_engineering_frontier_host.py','tests/test_controller_exchange_adapter.py',
           'tests/test_exchange_outbox_transitions.py']
    for path in files:
        target=tmp_path/path;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('def test_fixture_passes():\n    assert True\n')
    git('add','tests');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','validation suite inputs')
    c['repository']['head_sha']=git('rev-parse','HEAD')
    argv=['-m','pytest',*files,'-q']
    item={'id':'bridge-validation','action':'run_sandboxed_validation','argv':argv,
          'verification_profile':'Q0_TERMINAL_RESULT_SUITE','required_test_files':files,
          'minimum_tests_passed':5,'expected_result':'Q0_TERMINAL_RESULT_SUITE_PASS',
          'read_paths':files,'input_digest':digest({p:hashlib.sha256((tmp_path/p).read_bytes()).hexdigest() for p in files})}
    item['fingerprint']=digest(item)
    caps=local_engineering_capabilities(c,guard=lambda:True,
        artifact_directory=tmp_path/'validation-results',allowed_commands=[argv])
    result=caps['engineering.execute'](c,item)
    assert result['exit_code']==0 and result['result']=='Q0_TERMINAL_RESULT_SUITE_PASS'
    assert caps['engineering.verify_result'](c,item,result) is True
    changed={**result,'source_head':'f'*40}
    assert caps['engineering.verify_result'](c,item,changed) is False


def test_source_bound_frontier_input_digest_is_accepted_by_host_executor(tmp_path):
    import json,hashlib,subprocess
    from tools.node_architect.engineering_host_adapter import read_source_bound_frontier,local_engineering_capabilities
    from tools.node_architect.task_context_binding import digest
    c,_,git=agent_fixture(tmp_path)
    files=['tests/test_engineering_m1_m7_workflow.py','tests/test_engineering_work_frontier.py',
           'tests/test_engineering_frontier_host.py','tests/test_controller_exchange_adapter.py',
           'tests/test_exchange_outbox_transitions.py']
    for path in files:
        target=tmp_path/path;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('def test_fixture_passes():\n    assert True\n')
    argv=['-m','pytest',*files,'-q']
    item={'id':'bridge-validation','priority':2,'plan_node_id':'ROOT',
          'action':'run_sandboxed_validation','objective':'Validate terminal result path',
          'argv':argv,'expected_result':'Q0_TERMINAL_RESULT_SUITE_PASS',
          'verification_profile':'Q0_TERMINAL_RESULT_SUITE','minimum_tests_passed':5,
          'required_test_files':files,'read_paths':files,'write_paths':[]}
    profile={'runtime_plan_ref':c['run']['runtime_plan_ref'],'items':[item]}
    (tmp_path/'validation-profile.json').write_text(json.dumps(profile))
    git('add','tests','validation-profile.json')
    git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','bind terminal validation profile')
    c['repository']['head_sha']=git('rev-parse','HEAD')
    projection=read_source_bound_frontier(c,profile_ref='validation-profile.json',guard=lambda:True)
    selected=projection['selected_work'];assert selected['id']=='bridge-validation'
    selected={**selected,'fingerprint':digest(selected)}
    caps=local_engineering_capabilities(c,guard=lambda:True,
        artifact_directory=tmp_path/'validation-results',allowed_commands=[argv])
    result=caps['engineering.execute'](c,selected)
    assert result['exit_code']==0 and result['result']=='Q0_TERMINAL_RESULT_SUITE_PASS'
    assert caps['engineering.verify_result'](c,selected,result) is True
