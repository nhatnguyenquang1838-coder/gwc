"""Host-owned one-shot human read and allowlisted read-only subprocess execution.

These capabilities are engineering evidence only. No typed C/E/continuation read,
GUI, credential access, Loop lifecycle operation or legacy gate receipt is used.
"""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from .task_context_binding import require,digest


def select_human_communication(comments,context):
    selected=[];issue_ref=context['communication']['issue_ref'];run=context['run']['id']
    authors=context['communication'].get('allowed_authors',[context['repository']['name'].split('/')[0]])
    for comment in comments:
        body=comment.get('body','');header=body.split('\n\n',1)[0]
        if '<!-- dw.taskcontroller.communication/v2 -->' not in header or not re.search(r'^run:\s*'+re.escape(run)+r'\s*$',header,re.M):continue
        if (comment.get('user') or {}).get('login') not in authors:continue
        fields={}
        for key in ['seq','kind','from','to','source_ref','reply_to']:
            match=re.search(r'^'+key+r':\s*(.+)$',header,re.M)
            fields[key]=match.group(1).strip() if match else ''
        require(fields['seq'].isdigit(),'HUMAN_COMMUNICATION_SEQ_INVALID')
        # A correction that targets a comment in this issue inherits the
        # source_ref it corrects; requiring the field verbatim would reject a
        # valid correction whose reply_to already binds it to this issue.
        if fields['kind']=='CORRECTION' and not fields['source_ref'] and fields['reply_to'].startswith(
                'https://github.com/'+issue_ref.removeprefix('github://')+'#issuecomment-'):
            fields['source_ref']=issue_ref
        selected.append({**fields,'seq':int(fields['seq']),'run_id':run,'issue_ref':issue_ref,
                         'comment_id':comment['id'],'comment_url':comment['html_url'],'author':comment['user']['login'],
                         'body_sha256':hashlib.sha256(body.encode()).hexdigest(),'body':body,
                         'evidence_class':'HUMAN_COMMUNICATION_ONLY'})
    require(selected,'HUMAN_COMMUNICATION_NOT_FOUND')
    require(len({r['seq'] for r in selected})==len(selected),'HUMAN_COMMUNICATION_DUPLICATE_SEQ')
    commands=[r for r in selected if r['kind'] in {'COMMAND','CORRECTION'}]
    require(commands,'HUMAN_COMMAND_NOT_FOUND');result=max(commands,key=lambda r:r['seq'])
    require(all(result[k] for k in ['from','to','source_ref','reply_to']),'HUMAN_COMMUNICATION_FIELD_REQUIRED')
    require(result['source_ref']==issue_ref and result['author'] in authors,'HUMAN_COMMUNICATION_BINDING_INVALID')
    require(result['from']=='GPT' and result['to']=='Hermes','HUMAN_COMMUNICATION_ACTOR_MISMATCH')
    issue_url='https://github.com/'+issue_ref.removeprefix('github://')
    require(result['reply_to'].startswith(issue_url+'#issuecomment-'),'HUMAN_COMMUNICATION_REPLY_BINDING_INVALID')
    require(result['comment_url']==issue_url+'#issuecomment-'+str(result['comment_id']),'HUMAN_COMMENT_IDENTITY_MISMATCH')
    return {**result,'latest_communication_seq':max(r['seq'] for r in selected)}


def local_engineering_capabilities(context,*,guard,artifact_directory,allowed_commands):
    """guard is the source/native-owner revalidation callback, never a cached flag."""
    root=Path(context['repository']['worktree']).resolve();artifacts=Path(artifact_directory).resolve()
    def validate(c):
        if guard() is not True:return False
        head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        branch=subprocess.check_output(['git','-C',str(root),'branch','--show-current'],text=True).strip()
        if head!=c['repository']['head_sha'] or branch!=c['repository']['branch']:return False
        ref=c['run']['runtime_plan_ref'];raw=(root/ref).read_bytes()
        return raw==subprocess.check_output(['git','-C',str(root),'show',head+':'+ref]) and 'sha256:'+hashlib.sha256(raw).hexdigest()==c['run']['runtime_plan_digest']
    def read_once(c):
        require(guard() is True,'ENGINEERING_HOST_OWNER_UNVERIFIED')
        match=re.fullmatch(r'github://([^/]+/[^/]+)/issues/([1-9][0-9]*)',c['communication']['issue_ref'])
        if match is None:raise ValueError('HUMAN_ISSUE_REF_INVALID')
        repo,number=match.groups();require(repo==c['repository']['name'],'HUMAN_ISSUE_REPOSITORY_MISMATCH')
        raw=subprocess.check_output(['gh','api','--paginate','--slurp',f'repos/{repo}/issues/{number}/comments?per_page=100'],text=True)
        # Typed rows stay opaque. Only the filtered human command is persisted.
        selected=select_human_communication([row for page in json.loads(raw) for row in page],c)
        return selected
    class EngineeringPreEffectValidationError(ValueError):
        pre_effect_validation_failed=True
        def __init__(self,reason_code):
            self.reason_code=str(reason_code)[:160]
            super().__init__(self.reason_code)

    def preflight(c,item):
        """Validate source, policy and command bindings without starting the task subprocess."""
        try:
            require(validate(c),'ENGINEERING_SOURCE_OR_OWNER_CHANGED')
            argv=tuple(item.get('argv',[]));require(argv in {tuple(a) for a in allowed_commands},'ENGINEERING_COMMAND_NOT_ALLOWLISTED')
            hashes={}
            for ref in item['read_paths']:
                path=(root/ref).resolve();require(path.is_relative_to(root),'ENGINEERING_SOURCE_PATH_ESCAPE')
                data=path.read_bytes();require(data==subprocess.check_output(['git','-C',str(root),'show',c['repository']['head_sha']+':'+ref]),'ENGINEERING_INPUT_SOURCE_DRIFT')
                hashes[ref]=hashlib.sha256(data).hexdigest()
            policy_ref=item.get('_source_policy_ref')
            policy_sha256=None
            if policy_ref:
                policy_path=(root/policy_ref).resolve();require(policy_path.is_relative_to(root),'ENGINEERING_POLICY_PATH_ESCAPE')
                policy_raw=policy_path.read_bytes()
                require(policy_raw==subprocess.check_output(['git','-C',str(root),'show',c['repository']['head_sha']+':'+policy_ref]),'ENGINEERING_POLICY_SOURCE_DRIFT')
                policy_sha256=hashlib.sha256(policy_raw).hexdigest()
                require(policy_sha256==item.get('_source_policy_sha256') and hashes==item.get('_source_input_hashes'),
                        'ENGINEERING_INPUT_BINDINGS_DRIFT')
                input_binding={'policy_sha256':policy_sha256,'input_hashes':hashes}
            else:
                input_binding=hashes
            require(digest(input_binding)==item['input_digest'],'ENGINEERING_INPUT_DIGEST_DRIFT')
            require(item['action'] in c['runtime_plan']['scope']['allowed_actions'] and item['action']=='run_sandboxed_validation','ENGINEERING_EFFECT_AUTHORITY_REQUIRED')
            require(validate(c),'ENGINEERING_EFFECT_REVALIDATION_FAILED')
            return {'argv':list(argv),'source_head':c['repository']['head_sha'],'input_hashes':hashes,
                    'input_policy_ref':policy_ref,'input_policy_sha256':policy_sha256,
                    'input_digest':item['input_digest']}
        except EngineeringPreEffectValidationError:
            raise
        except Exception as exc:
            reason=str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            raise EngineeringPreEffectValidationError(reason) from exc

    def execute(c,item,prepared=None):
        if prepared is None:prepared=preflight(c,item)
        current=preflight(c,item)
        if current!=prepared:raise EngineeringPreEffectValidationError('ENGINEERING_PREFLIGHT_BINDING_CHANGED')
        argv=tuple(prepared['argv']);hashes=prepared['input_hashes']
        policy_ref=prepared['input_policy_ref'];policy_sha256=prepared['input_policy_sha256']
        result=subprocess.run([sys.executable,*argv],cwd=root,capture_output=True,text=True,timeout=90)
        artifacts.mkdir(parents=True,exist_ok=True)
        payload={'argv':list(argv),'source_head':c['repository']['head_sha'],'exit_code':result.returncode,
                 'stdout':result.stdout,'stderr':result.stderr,'input_hashes':hashes,
                 'input_policy_ref':policy_ref,'input_policy_sha256':policy_sha256 if policy_ref else None,
                 'input_digest':item['input_digest']}
        path=artifacts/(item['fingerprint'].split(':')[-1]+'.json');encoded=json.dumps(payload,sort_keys=True)
        path.write_text(encoded)
        try:observed=json.loads(result.stdout)
        except ValueError:observed={}
        outcome=observed.get('result','HOST_PROCESS_FAILED')
        if item.get('verification_profile')=='Q0_TERMINAL_RESULT_SUITE':
            summary=re.search(r'(?m)(\d+) passed(?:,\s*\d+ subtests?)? in [0-9.]+s\s*$',result.stdout)
            if (result.returncode==0 and summary is not None and
                    int(summary.group(1))>=item.get('minimum_tests_passed',1) and
                    not re.search(r'(?m)^\d+ (?:failed|error|errors)\b',result.stdout) and
                    all(test_path in argv for test_path in item.get('required_test_files',[]))):
                outcome=item.get('expected_result')
        return {'exit_code':result.returncode,'result':outcome,
                'source_head':c['repository']['head_sha'],'stdout_digest':digest(result.stdout),
                'artifact_ref':str(path),'artifact_digest':digest(payload),'observed':observed,'executed_effects':[]}
    def verify(c,item,result):
        raw=json.loads(Path(result['artifact_ref']).read_text())
        if digest(raw)!=result['artifact_digest'] or digest(raw['stdout'])!=result['stdout_digest']:return False
        if item.get('verification_profile')=='Q0_TERMINAL_RESULT_SUITE':
            if raw.get('argv')!=item.get('argv') or raw.get('source_head')!=c['repository']['head_sha'] or result.get('source_head')!=c['repository']['head_sha'] or raw.get('exit_code')!=0:return False
            if raw.get('input_digest')!=item.get('input_digest') or raw.get('input_policy_ref')!=item.get('_source_policy_ref'):return False
            if item.get('_source_policy_ref') and raw.get('input_policy_sha256')!=item.get('_source_policy_sha256'):return False
            if not all(path in raw['argv'] for path in item.get('required_test_files',[])):return False
            summary=re.search(r'(?m)(\d+) passed(?:,\s*\d+ subtests?)? in [0-9.]+s\s*$',raw['stdout'])
            if summary is None or int(summary.group(1))<item.get('minimum_tests_passed',1):return False
            if re.search(r'(?m)^\d+ (?:failed|error|errors)\b',raw['stdout']):return False
            return (validate(c) and result['exit_code']==0 and
                    result.get('result')==item.get('expected_result') and
                    result.get('executed_effects')==[])
        observed=json.loads(raw['stdout']) if raw['exit_code']==0 else {}
        return (validate(c) and raw['source_head']==c['repository']['head_sha'] and result['exit_code']==raw['exit_code']==0 and
                observed.get('result')==item['expected_result'] and
                observed.get('provenance_class')=='RECONSTRUCTED_REQUIREMENTS_BOUND' and
                observed.get('q0_l3_qualified') is False and observed.get('authentic_dwo_login_replay') is False and
                observed.get('executed_effects')==[])
    return {'engineering.communication_read_once':read_once,'engineering.validate_context':validate,
        'engineering.preflight':preflight,'engineering.execute':execute,'engineering.verify_result':verify}


def read_source_bound_frontier(context,*,profile_ref,guard):
    """One local source read, never another communication poll or effect grant."""
    import sqlite3
    from .engineering_work_frontier import project_frontier
    require(guard() is True,'ENGINEERING_HOST_OWNER_UNVERIFIED')
    root=Path(context['repository']['worktree']).resolve();head=context['repository']['head_sha']
    require(subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()==head,'ENGINEERING_FRONTIER_SOURCE_DRIFT')
    def source(ref):
        path=(root/ref).resolve();require(path.is_relative_to(root),'ENGINEERING_FRONTIER_PATH_ESCAPE')
        data=path.read_bytes()
        require(data==subprocess.check_output(['git','-C',str(root),'show',head+':'+ref]),'ENGINEERING_FRONTIER_SOURCE_DRIFT')
        return data
    policy_raw=source(profile_ref);policy=json.loads(policy_raw);policy_sha256=hashlib.sha256(policy_raw).hexdigest();items=[]
    require(policy.get('runtime_plan_ref',context['run']['runtime_plan_ref'])==context['run']['runtime_plan_ref'],'ENGINEERING_FRONTIER_PLAN_DRIFT')
    for declared in policy['items']:
        item=dict(declared);hashes={ref:hashlib.sha256(source(ref)).hexdigest() for ref in item.get('read_paths',[])}
        missing=list(item.get('missing_external_evidence',[]))
        for need in item.get('evidence_requirements',[]):
            raw=source(need['path']);hashes[need['path']]=hashlib.sha256(raw).hexdigest()
            value=json.loads(raw)
            for part in need['field'].split('.'):value=value.get(part,{}) if isinstance(value,dict) else None
            if value!=need['equals']:missing.append(need['name'])
        item['_stable_fingerprint']=digest({k:v for k,v in item.items() if not k.startswith('_')})
        item['missing_external_evidence']=missing
        item['_source_policy_ref']=profile_ref
        item['_source_policy_sha256']=policy_sha256
        item['_source_input_hashes']=hashes
        item['input_digest']=digest({'policy_sha256':policy_sha256,'input_hashes':hashes})
        items.append(item)
    cp=Path(context['workflow']['checkpoint_ref']);verified=[]
    if cp.is_file():
        with sqlite3.connect(cp.as_uri()+'?mode=ro',uri=True) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='engineering_work'").fetchone():
                records=db.execute('SELECT fingerprint,result FROM engineering_work WHERE run=? AND status=?',(context['run']['id'],'VERIFIED')).fetchall()
                verified=[r[0] for r in records]
                current_keys={digest(i) for i in items}
                for _,raw in records:
                    receipt=json.loads(raw) if raw else {}
                    alias=receipt.get('completion_fingerprint')
                    if alias in current_keys and receipt.get('evidence_class')=='HOST_AGENT_EFFECT_READBACK_NOT_GATE_AUTHORITY' and receipt.get('authority_granted') is False:
                        ancestor=subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',receipt['result_head'],head],capture_output=True)
                        require(ancestor.returncode==0,'ENGINEERING_COMPLETION_SOURCE_DRIFT')
                        verified.append(alias)
    require(guard() is True,'ENGINEERING_HOST_OWNER_UNVERIFIED')
    result=project_frontier(context,items,verified_fingerprints=verified)
    for item in context.get('engineering',{}).get('work_items',[]):
        if digest(item) in verified:result['items'].append({'id':item['id'],'status':'VERIFIED','fingerprint':digest(item),'work':item})
    return result


def _validate_agent_request(context,request,guard,*,before_effect):
    """Dispatch binding + actual recovery policy, never root-node permission."""
    import sqlite3
    from .engineering_work_frontier import work_within_scope
    require(guard() is True,'AGENT_OWNER_UNVERIFIED')
    require(request.get('request_digest')==digest({k:v for k,v in request.items() if k!='request_digest'}) and
            request.get('task_context_digest')==digest(context) and request.get('run_id')==context['run']['id'] and
            request.get('session_id')==context['executor']['session_id'] and
            request.get('source_head')==context['repository']['head_sha'],'AGENT_REQUEST_BINDING_INVALID')
    require(request.get('executor')=='CURRENT_HERMES_AGENT' and request.get('authority_granted') is False and
            request.get('effect_executed') is False,'AGENT_REQUEST_INVALID')
    work=request['work'];require(request['work_fingerprint']==digest({k:v for k,v in work.items() if k!='fingerprint'}),'AGENT_WORK_FINGERPRINT_INVALID')
    require(work_within_scope(context,work) and work['action']=='modify_approved_files','AGENT_WRITE_SCOPE_INVALID')
    root=Path(context['repository']['worktree']).resolve()
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
    require(git('branch','--show-current')==context['repository']['branch'],'AGENT_BRANCH_DRIFT')
    if before_effect:require(git('rev-parse','HEAD')==request['source_head'],'AGENT_SOURCE_DRIFT')
    ref=context['run']['runtime_plan_ref'];raw=(root/ref).read_bytes()
    require(raw==subprocess.check_output(['git','-C',str(root),'show',request['source_head']+':'+ref]) and
            'sha256:'+hashlib.sha256(raw).hexdigest()==request['runtime_plan_digest']==context['run']['runtime_plan_digest'],'AGENT_PLAN_DRIFT')
    plan=json.loads(raw)
    require(plan['run_id']==context['run']['id'] and plan['branch']==context['repository']['branch'] and
            plan['scope']==context['runtime_plan']['scope'],'AGENT_PLAN_BINDING_INVALID')
    require(plan.get('implementation_mode')=='continuous_tdd_self_remediation' and
            plan.get('authority_basis',{}).get('kind')=='standing_q0_autonomous_development_policy' and
            'GWC_RUNTIME_DEFECT' in plan.get('recovery_policy','') and
            work.get('plan_relation')=='CONDITIONAL_RUNTIME_DEFECT_REPAIR_UNDER_EXISTING_RECOVERY_POLICY' and
            work.get('plan_node_id')==plan['recursive_plan']['id'] and plan['recursive_plan'].get('atomic') is False,
            'AGENT_CONDITIONAL_REPAIR_UNPROVEN')
    for ref in work['write_paths']:
        require((root/ref).resolve().is_relative_to(root),'AGENT_WRITE_PATH_ESCAPE')
    with sqlite3.connect(context['workflow']['checkpoint_ref']) as db:
        rows=db.execute('SELECT result FROM engineering_invocations WHERE run=? AND result IS NOT NULL',(context['run']['id'],)).fetchall()
        require(any(json.loads(row[0]).get('host_action_request')==request for row in rows),'AGENT_DISPATCH_NOT_FOUND')
    return root


def _agent_transition(context,request,expected,status,payload):
    import sqlite3
    run=context['run']['id'];key=request['work_fingerprint']
    with sqlite3.connect(context['workflow']['checkpoint_ref']) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT status,result FROM engineering_work WHERE run=? AND fingerprint=?',(run,key)).fetchone()
        require((row is None if expected is None else row is not None and row[0]==expected),'AGENT_WORK_STATE_CONFLICT')
        if row:
            prior=json.loads(row[1]);require(prior.get('request_digest')==request['request_digest'],'AGENT_CLAIM_BINDING_MISMATCH')
        db.execute('CREATE TABLE IF NOT EXISTS engineering_agent_work_history (run TEXT, fingerprint TEXT, seq INTEGER, event TEXT, PRIMARY KEY(run,fingerprint,seq))')
        if row:db.execute('UPDATE engineering_work SET status=?,result=? WHERE run=? AND fingerprint=?',(status,json.dumps(payload,sort_keys=True),run,key))
        else:db.execute('INSERT INTO engineering_work VALUES (?,?,?,?)',(run,key,status,json.dumps(payload,sort_keys=True)))
        seq=db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM engineering_agent_work_history WHERE run=? AND fingerprint=?',(run,key)).fetchone()[0]
        db.execute('INSERT INTO engineering_agent_work_history VALUES (?,?,?,?)',(run,key,seq,json.dumps({'status':status,**payload},sort_keys=True)))
    with sqlite3.connect(context['workflow']['checkpoint_ref']) as db:
        actual=db.execute('SELECT status,result FROM engineering_work WHERE run=? AND fingerprint=?',(run,key)).fetchone()
        require(actual[0]==status and json.loads(actual[1])==payload,'AGENT_DURABLE_READBACK_FAILED')
    return payload


def reserve_agent_work(context,request,*,guard):
    _validate_agent_request(context,request,guard,before_effect=True)
    payload={'request_digest':request['request_digest'],'source_head':request['source_head'],
             'session_id':request['session_id'],'plan_digest':request['runtime_plan_digest'],'conditional_repair':True}
    return _agent_transition(context,request,None,'RESERVED',payload)


def start_agent_work(context,request,*,guard):
    _validate_agent_request(context,request,guard,before_effect=True)
    payload={'request_digest':request['request_digest'],'source_head':request['source_head'],
             'session_id':request['session_id'],'plan_digest':request['runtime_plan_digest'],'conditional_repair':True}
    return _agent_transition(context,request,'RESERVED','IN_FLIGHT',payload)


def _read_agent_execution(context,request,artifact_ref,guard,profile_ref):
    root=_validate_agent_request(context,request,guard,before_effect=False)
    path=Path(artifact_ref).resolve();store=Path(context['workflow']['checkpoint_ref']).resolve().parent
    require(path.is_relative_to(store),'AGENT_ARTIFACT_PATH_ESCAPE')
    raw=path.read_bytes();data=json.loads(raw)
    require(data['request_digest']==request['request_digest'] and data['base_head']==request['source_head'] and
            data['verification_exit_code']==0,'AGENT_EXECUTION_BINDING_INVALID')
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
    require(git('rev-parse','HEAD')==data['result_head'],'AGENT_RESULT_HEAD_DRIFT')
    subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',request['source_head'],data['result_head']],check=True)
    changed=git('diff','--name-only',request['source_head'],data['result_head']).splitlines()
    require(bool(changed) and set(changed)<=set(request['work']['write_paths']),'AGENT_EFFECT_SCOPE_INVALID')
    require(not git('diff','--name-only','HEAD'),'AGENT_UNCOMMITTED_SOURCE')
    log=Path(data['verification_log_ref']).resolve()
    require(log.is_relative_to(store) and hashlib.sha256(log.read_bytes()).hexdigest()==data['verification_log_sha256'],'AGENT_VERIFICATION_LOG_INVALID')
    receipt={'request_digest':request['request_digest'],'work_id':request['work']['id'],
             'source_head':request['source_head'],'result_head':data['result_head'],'changed_paths':changed,
             'artifact_ref':str(path),'artifact_sha256':hashlib.sha256(raw).hexdigest(),
             'verification_log_sha256':data['verification_log_sha256'],'verification_exit_code':0,
             'evidence_class':'HOST_AGENT_EFFECT_READBACK_NOT_GATE_AUTHORITY','authority_granted':False}
    if profile_ref:
        import copy
        current=copy.deepcopy(context);current['repository']['head_sha']=data['result_head']
        projection=read_source_bound_frontier(current,profile_ref=profile_ref,guard=guard)
        matches=[r for r in projection['items'] if r['id']==request['work']['id']]
        require(len(matches)==1,'AGENT_COMPLETION_FRONTIER_BINDING_INVALID')
        receipt['completion_fingerprint']=matches[0]['fingerprint']
    require(guard() is True,'AGENT_OWNER_UNVERIFIED')
    return receipt


def quarantine_agent_work(context,request,*,guard,reason_code):
    _validate_agent_request(context,request,guard,before_effect=False)
    require(reason_code in {'HOST_RESULT_UNKNOWN','HOST_EXECUTION_INTERRUPTED'},'AGENT_REASON_INVALID')
    return _agent_transition(context,request,'IN_FLIGHT','UNKNOWN',
                             {'request_digest':request['request_digest'],'reason_code':reason_code,'requires_reconciliation':True})


def record_agent_execution(context,request,*,artifact_ref,guard,profile_ref=None):
    receipt=_read_agent_execution(context,request,artifact_ref,guard,profile_ref)
    return _agent_transition(context,request,'IN_FLIGHT','EXECUTED',receipt)


def verify_agent_execution(context,request,*,artifact_ref,guard,profile_ref=None):
    import sqlite3
    receipt=_read_agent_execution(context,request,artifact_ref,guard,profile_ref)
    with sqlite3.connect(context['workflow']['checkpoint_ref']) as db:
        row=db.execute('SELECT status,result FROM engineering_work WHERE run=? AND fingerprint=?',(context['run']['id'],request['work_fingerprint'])).fetchone()
        require(row is not None and row[0]=='EXECUTED','AGENT_WORK_STATE_CONFLICT')
        require(json.loads(row[1])==receipt,'AGENT_EXECUTION_RECEIPT_DRIFT')
    return _agent_transition(context,request,'EXECUTED','VERIFIED',receipt)
