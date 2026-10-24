
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
    repair=next(i for i in r['items'] if i['id']=='repair')
    assert repair['work']['_source_head']==c['repository']['head_sha']
    prior_fingerprint=repair['fingerprint']
    (tmp_path/'unrelated.txt').write_text('additive source revision\n')
    git('add','unrelated.txt');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','advance source head')
    c['repository']['head_sha']=git('rev-parse','HEAD')
    refreshed=read_source_bound_frontier(c,profile_ref='profile.json',guard=lambda:True)
    assert next(i for i in refreshed['items'] if i['id']=='repair')['fingerprint']!=prior_fingerprint
    (tmp_path/'code.py').write_text('# drift\n')
    with pytest.raises(ValueError,match='ENGINEERING_FRONTIER_SOURCE_DRIFT'):
        read_source_bound_frontier(c,profile_ref='profile.json',guard=lambda:True)


def test_local_verifier_accepts_only_bound_terminal_bridge_suite_artifact(tmp_path):
    import json,hashlib
    from pathlib import Path
    from tools.node_architect.engineering_host_adapter import local_engineering_capabilities
    from tools.node_architect.task_context_binding import digest
    c,_,git=agent_fixture(tmp_path)
    ref='tests/test_unit_only.py'
    source=tmp_path/ref;source.parent.mkdir(parents=True)
    source.write_text('def test_unit_fixture_only():\n    assert True\n')
    git('add',ref);git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','unit fixture input')
    c['repository']['head_sha']=git('rev-parse','HEAD')
    argv=['-m','pytest',ref,'-q']
    item={'id':'bridge-validation','action':'run_sandboxed_validation','argv':argv,
          'verification_profile':'Q0_TERMINAL_RESULT_SUITE','required_test_files':[ref],
          'minimum_tests_passed':1,'expected_result':'Q0_TERMINAL_RESULT_SUITE_PASS',
          'read_paths':[ref],'input_digest':digest({ref:hashlib.sha256(source.read_bytes()).hexdigest()})}
    item['fingerprint']=digest(item)
    caps=local_engineering_capabilities(c,guard=lambda:True,
        artifact_directory=tmp_path/'validation-results',allowed_commands=[argv])
    # Positive evidence is emitted by the actual unit-host subprocess, not invented stdout.
    result=caps['engineering.execute'](c,item)
    assert result['exit_code']==0
    assert caps['engineering.verify_result'](c,item,result) is True
    artifact=Path(result['artifact_ref']);payload=json.loads(artifact.read_text())
    bad=dict(payload);bad['argv']=['-c','print("not tests")'];artifact.write_text(json.dumps(bad,sort_keys=True))
    bad_result={**result,'artifact_digest':digest(bad)}
    assert caps['engineering.verify_result'](c,item,bad_result) is False


@pytest.mark.parametrize('gap', ['outside_store', 'command_not_allowlisted', 'input_hashes', 'policy_digest'])
def test_host_verifier_cannot_skip_preflight_or_artifact_binding(tmp_path, gap):
    import hashlib, json
    from tools.node_architect.engineering_host_adapter import local_engineering_capabilities
    from tools.node_architect.task_context_binding import digest
    c, _, _ = agent_fixture(tmp_path)
    allowed = ['-m','pytest','tests/unit_only.py','-q']
    argv = ['-m','pytest','tests/not_allowlisted.py','-q'] if gap == 'command_not_allowlisted' else allowed
    ref = 'tools/repair.py'
    hashes = {ref:hashlib.sha256((tmp_path/ref).read_bytes()).hexdigest()}
    item = {'id':'bound-verification','action':'run_sandboxed_validation','argv':argv,
            'read_paths':[ref], 'input_digest':digest(hashes),
            'verification_profile':'Q0_TERMINAL_RESULT_SUITE','required_test_files':[argv[2]],
            'minimum_tests_passed':1,'expected_result':'UNIT_ONLY_SUITE_PASS'}
    item['fingerprint'] = digest(item)
    artifacts = tmp_path/'validation-results'
    artifacts.mkdir()
    artifact = artifacts/(item['fingerprint'].split(':')[-1]+'.json')
    if gap == 'outside_store':artifact = tmp_path/'untrusted-outside.json'
    stdout = '1 passed in 0.01s\n'  # Adversarial input, NOT observed execution.
    payload = {'argv':argv,'source_head':c['repository']['head_sha'],'exit_code':0,
               'stdout':stdout,'stderr':'','input_hashes':hashes,'input_digest':item['input_digest'],
               'input_policy_ref':None,'input_policy_sha256':None,'task_context_digest':digest(c)}
    if gap == 'input_hashes':payload['input_hashes'] = {ref:'0'*64}
    if gap == 'policy_digest':payload['input_policy_sha256'] = 'unbound-policy'
    artifact.write_text(json.dumps(payload))
    before = artifact.read_bytes()
    result = {'artifact_ref':str(artifact),'artifact_digest':digest(payload),'stdout_digest':digest(stdout),
              'exit_code':0,'source_head':c['repository']['head_sha'],
              'result':item['expected_result'],'executed_effects':[]}
    caps = local_engineering_capabilities(c, guard=lambda:True,
                                         artifact_directory=artifacts, allowed_commands=[allowed])
    assert caps['engineering.verify_result'](c,item,result) is False
    assert artifact.read_bytes() == before


def _terminal_unit_host(tmp_path):
    import hashlib
    from tools.node_architect.engineering_host_adapter import local_engineering_capabilities
    from tools.node_architect.task_context_binding import digest
    c,_,git=agent_fixture(tmp_path)
    ref='tests/test_unit_bound.py';source=tmp_path/ref;source.parent.mkdir(parents=True)
    source.write_text('def test_unit_only():\n    assert True\n')
    git('add',ref);git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','unit input')
    c['repository']['head_sha']=git('rev-parse','HEAD')
    argv=['-m','pytest',ref,'-q']
    item={'id':'unit-bound','action':'run_sandboxed_validation','argv':argv,'read_paths':[ref],
          'input_digest':digest({ref:hashlib.sha256(source.read_bytes()).hexdigest()}),
          'verification_profile':'Q0_TERMINAL_RESULT_SUITE','required_test_files':[ref],
          'minimum_tests_passed':1,'expected_result':'UNIT_ONLY_PASS'}
    item['fingerprint']=digest(item)
    directory=tmp_path/'validation-results'
    caps=local_engineering_capabilities(c,guard=lambda:True,artifact_directory=directory,allowed_commands=[argv])
    return c,item,caps,source,directory,argv


@pytest.mark.parametrize('identity', ['run','task'])
def test_stale_result_cannot_cross_task_context(tmp_path, identity):
    from copy import deepcopy
    from tools.node_architect.engineering_host_adapter import local_engineering_capabilities
    c,item,caps,_,directory,argv=_terminal_unit_host(tmp_path)
    result=caps['engineering.execute'](c,item)
    assert caps['engineering.verify_result'](c,item,result) is True
    other=deepcopy(c);other[identity]['id']+='-other-unit-context'
    successor=local_engineering_capabilities(other,guard=lambda:True,artifact_directory=directory,allowed_commands=[argv])
    assert successor['engineering.verify_result'](other,item,result) is False


@pytest.mark.parametrize('gap', ['input','symlink'])
def test_post_preflight_drift_refused_before_task_subprocess(tmp_path, monkeypatch, gap):
    import sys
    import tools.node_architect.engineering_host_adapter as host
    c,item,caps,source,directory,_=_terminal_unit_host(tmp_path)
    prepared=caps['engineering.preflight'](c,item)
    sentinel=tmp_path/'outside-sentinel';sentinel.write_bytes(b'PRESERVE')
    if gap=='input':source.write_text('changed after preflight\n')
    else:
        directory.mkdir();(directory/(item['fingerprint'].split(':')[-1]+'.json')).symlink_to(sentinel)
    run=host.subprocess.run;calls=[]
    def observed(argv,*args,**kwargs):
        if argv[0]==sys.executable:calls.append(argv)
        return run(argv,*args,**kwargs)
    monkeypatch.setattr(host.subprocess,'run',observed)
    with pytest.raises(ValueError,match='ENGINEERING_INPUT_SOURCE_DRIFT|ENGINEERING_ARTIFACT_PATH_ESCAPE'):
        caps['engineering.execute'](c,item,prepared)
    assert calls==[]
    assert sentinel.read_bytes()==b'PRESERVE'


def test_post_command_input_drift_cannot_publish_completion(tmp_path, monkeypatch):
    import sys
    import tools.node_architect.engineering_host_adapter as host
    c,item,caps,source,directory,_=_terminal_unit_host(tmp_path)
    run=host.subprocess.run;calls=[]
    def changed(argv,*args,**kwargs):
        result=run(argv,*args,**kwargs)
        if argv[0]==sys.executable:
            calls.append(argv);source.write_text('changed while task ran\n')
        return result
    monkeypatch.setattr(host.subprocess,'run',changed)
    with pytest.raises(ValueError,match='ENGINEERING_INPUT_SOURCE_DRIFT'):
        caps['engineering.execute'](c,item)
    assert len(calls)==1  # The initially admitted unit subprocess really ran.
    assert not directory.exists()  # No completed artifact published after drift.


@pytest.mark.parametrize('replacement', ['symlink', 'hardlink', 'store_symlink'])
def test_artifact_replacement_after_containment_check_cannot_overwrite_sentinel(tmp_path,monkeypatch,replacement):
    import os
    from pathlib import Path
    c,item,caps,_,directory,_=_terminal_unit_host(tmp_path)
    artifact=directory/(item['fingerprint'].split(':')[-1]+'.json')
    outside=tmp_path/'outside-store';outside.mkdir()
    sentinel=outside/artifact.name;sentinel.write_bytes(b'PRESERVE')
    resolve=Path.resolve;replaced=[]
    def race(path,*args,**kwargs):
        resolved=resolve(path,*args,**kwargs)
        # Deterministic filesystem replacement after the last containment lookup,
        # not a forged executor result. The real admitted unit subprocess ran.
        if path==artifact and directory.exists() and not replaced:
            replaced.append(replacement)
            if replacement=='symlink':artifact.symlink_to(sentinel)
            elif replacement=='hardlink':os.link(sentinel,artifact)
            else:
                directory.rename(tmp_path/'original-store')
                directory.symlink_to(outside,target_is_directory=True)
        return resolved
    monkeypatch.setattr(Path,'resolve',race)
    error=None
    try:caps['engineering.execute'](c,item)
    except (ValueError,OSError) as exc:error=exc
    assert replaced==[replacement]
    assert sentinel.read_bytes()==b'PRESERVE'  # Must hold BEFORE reporting refusal.
    assert error is not None
    # This is publication fencing, not a claim the task subprocess never ran.
    assert getattr(error,'pre_effect_validation_failed',False) is False


def test_existing_artifact_is_preserved_without_reexecuting_task(tmp_path,monkeypatch):
    import sys
    from pathlib import Path
    import tools.node_architect.engineering_host_adapter as host
    c,item,caps,_,_,_=_terminal_unit_host(tmp_path)
    result=caps['engineering.execute'](c,item)
    artifact=Path(result['artifact_ref']);before=artifact.read_bytes()
    run=host.subprocess.run;calls=[]
    def observed(argv,*args,**kwargs):
        if argv[0]==sys.executable:calls.append(argv)
        return run(argv,*args,**kwargs)
    monkeypatch.setattr(host.subprocess,'run',observed)
    with pytest.raises(ValueError):caps['engineering.execute'](c,item)
    assert calls==[]
    assert artifact.read_bytes()==before
    assert caps['engineering.verify_result'](c,item,result) is True


def test_missing_atomic_publication_support_refuses_before_task(tmp_path,monkeypatch):
    import os,sys
    import tools.node_architect.engineering_host_adapter as host
    c,item,caps,_,directory,_=_terminal_unit_host(tmp_path)
    monkeypatch.setattr(os,'supports_dir_fd',set())
    run=host.subprocess.run;calls=[]
    def observed(argv,*args,**kwargs):
        if argv[0]==sys.executable:calls.append(argv)
        return run(argv,*args,**kwargs)
    monkeypatch.setattr(host.subprocess,'run',observed)
    with pytest.raises(ValueError,match='ENGINEERING_ARTIFACT_FENCE_UNAVAILABLE'):
        caps['engineering.execute'](c,item)
    assert calls==[] and not directory.exists()


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


@pytest.mark.parametrize('fingerprint', [None, 'sha256:../victim', 'sha256:'+'0'*64])
def test_host_rejects_unbound_artifact_fingerprint_before_subprocess(tmp_path, fingerprint):
    import hashlib
    from tools.node_architect.engineering_host_adapter import local_engineering_capabilities
    from tools.node_architect.task_context_binding import digest
    c, _, _ = agent_fixture(tmp_path)
    ref = 'tools/repair.py'
    argv = ['-c', 'print("{}")']
    item = {'id':'fingerprint-refusal', 'action':'run_sandboxed_validation', 'argv':argv,
            'read_paths':[ref], 'input_digest':digest({ref:hashlib.sha256((tmp_path/ref).read_bytes()).hexdigest()})}
    if fingerprint is not None:
        item['fingerprint'] = fingerprint
    victim = tmp_path/'victim.json'
    victim.write_text('preserve this sentinel')
    artifacts = tmp_path/'validation-results'
    caps = local_engineering_capabilities(c, guard=lambda:True,
                                         artifact_directory=artifacts, allowed_commands=[argv])
    with pytest.raises(ValueError, match='ENGINEERING_WORK_FINGERPRINT_INVALID'):
        caps['engineering.execute'](c, item)
    assert victim.read_text() == 'preserve this sentinel'
    assert not artifacts.exists()


def test_host_rejects_preexisting_artifact_symlink_outside_store(tmp_path):
    import hashlib
    from tools.node_architect.engineering_host_adapter import local_engineering_capabilities
    from tools.node_architect.task_context_binding import digest
    c, _, _ = agent_fixture(tmp_path)
    ref = 'tools/repair.py'
    argv = ['-c', 'print("{}")']
    item = {'id':'artifact-refusal', 'action':'run_sandboxed_validation', 'argv':argv,
            'read_paths':[ref], 'input_digest':digest({ref:hashlib.sha256((tmp_path/ref).read_bytes()).hexdigest()})}
    item['fingerprint'] = digest(item)
    victim = tmp_path/'outside.json'
    victim.write_text('preserve')
    artifacts = tmp_path/'validation-results'
    artifacts.mkdir()
    (artifacts/(item['fingerprint'].split(':')[-1]+'.json')).symlink_to(victim)
    caps = local_engineering_capabilities(c, guard=lambda:True,
                                         artifact_directory=artifacts, allowed_commands=[argv])
    with pytest.raises(ValueError, match='ENGINEERING_ARTIFACT_PATH_ESCAPE'):
        caps['engineering.execute'](c, item)
    assert victim.read_text() == 'preserve'


def test_local_preflight_classifies_input_digest_drift_before_execution(tmp_path,monkeypatch):
    import hashlib
    from tools.node_architect.engineering_host_adapter import local_engineering_capabilities
    from tools.node_architect.task_context_binding import digest
    c,_,_=agent_fixture(tmp_path)
    path='tools/repair.py';argv=['-c','print("preflight-only")']
    item={'id':'preflight-check','action':'run_sandboxed_validation','argv':argv,
          'read_paths':[path],'input_digest':digest({path:hashlib.sha256((tmp_path/path).read_bytes()).hexdigest()})}
    item['input_digest']='sha256:'+'0'*64
    import subprocess,sys
    calls={'run':0};real_run=subprocess.run
    def forbidden_run(command,*args,**kwargs):
        if command and command[0]==sys.executable:
            calls['run']+=1
            raise AssertionError('task subprocess must not start on preflight failure')
        return real_run(command,*args,**kwargs)
    monkeypatch.setattr('tools.node_architect.engineering_host_adapter.subprocess.run',forbidden_run)
    caps=local_engineering_capabilities(c,guard=lambda:True,
        artifact_directory=tmp_path/'validation-results',allowed_commands=[argv])
    preflight=caps.get('engineering.preflight')
    assert callable(preflight)
    with pytest.raises(ValueError,match='ENGINEERING_INPUT_DIGEST_DRIFT') as caught:
        preflight(c,item)
    assert getattr(caught.value,'pre_effect_validation_failed',False) is True
    assert calls['run']==0


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
