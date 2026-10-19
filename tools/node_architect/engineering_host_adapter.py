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
    def execute(c,item):
        require(validate(c),'ENGINEERING_SOURCE_OR_OWNER_CHANGED')
        argv=tuple(item.get('argv',[]));require(argv in {tuple(a) for a in allowed_commands},'ENGINEERING_COMMAND_NOT_ALLOWLISTED')
        hashes={}
        for ref in item['read_paths']:
            path=(root/ref).resolve();require(path.is_relative_to(root),'ENGINEERING_SOURCE_PATH_ESCAPE')
            data=path.read_bytes();require(data==subprocess.check_output(['git','-C',str(root),'show',c['repository']['head_sha']+':'+ref]),'ENGINEERING_INPUT_SOURCE_DRIFT')
            hashes[ref]=hashlib.sha256(data).hexdigest()
        require(digest(hashes)==item['input_digest'],'ENGINEERING_INPUT_DIGEST_DRIFT')
        require(item['action'] in c['runtime_plan']['scope']['allowed_actions'] and item['action']=='run_sandboxed_validation','ENGINEERING_EFFECT_AUTHORITY_REQUIRED')
        require(validate(c),'ENGINEERING_EFFECT_REVALIDATION_FAILED')
        result=subprocess.run([sys.executable,*argv],cwd=root,capture_output=True,text=True,timeout=90)
        artifacts.mkdir(parents=True,exist_ok=True)
        payload={'argv':list(argv),'source_head':c['repository']['head_sha'],'exit_code':result.returncode,
                 'stdout':result.stdout,'stderr':result.stderr,'input_hashes':hashes}
        path=artifacts/(item['fingerprint'].split(':')[-1]+'.json');encoded=json.dumps(payload,sort_keys=True)
        path.write_text(encoded)
        try:observed=json.loads(result.stdout)
        except ValueError:observed={}
        return {'exit_code':result.returncode,'result':observed.get('result','HOST_PROCESS_FAILED'),
                'source_head':c['repository']['head_sha'],'stdout_digest':digest(result.stdout),
                'artifact_ref':str(path),'artifact_digest':digest(payload),'observed':observed,'executed_effects':[]}
    def verify(c,item,result):
        raw=json.loads(Path(result['artifact_ref']).read_text())
        if digest(raw)!=result['artifact_digest'] or digest(raw['stdout'])!=result['stdout_digest']:return False
        observed=json.loads(raw['stdout']) if raw['exit_code']==0 else {}
        return (validate(c) and raw['source_head']==c['repository']['head_sha'] and result['exit_code']==raw['exit_code']==0 and
                observed.get('result')==item['expected_result'] and
                observed.get('provenance_class')=='RECONSTRUCTED_REQUIREMENTS_BOUND' and
                observed.get('q0_l3_qualified') is False and observed.get('authentic_dwo_login_replay') is False and
                observed.get('executed_effects')==[])
    return {'engineering.communication_read_once':read_once,'engineering.validate_context':validate,
            'engineering.execute':execute,'engineering.verify_result':verify}
