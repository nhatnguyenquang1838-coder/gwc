"""Generic task binding. Identity and source readback are not effect authority."""
from __future__ import annotations
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

ACTIVITIES = ('M1','M2','M3','M4','M5','M6','M7')


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def require(value, code):
    if not value:
        raise ValueError(code)


def validate_task_context(context):
    c = copy.deepcopy(context)
    require(isinstance(c, dict) and c.get('schema_version') == 1, 'TASK_CONTEXT_INVALID')
    for name in ('task','run','repository','controller','executor','workflow','capabilities'):
        require(isinstance(c.get(name), dict), 'TASK_CONTEXT_SECTION_REQUIRED:'+name)
    require(isinstance(c['task'].get('id'), str) and c['task']['id'].strip(), 'TASK_ID_REQUIRED')
    require(isinstance(c['task'].get('objective'), str) and c['task']['objective'].strip(), 'TASK_OBJECTIVE_REQUIRED')
    ac = c['task'].get('acceptance_criteria')
    require(isinstance(ac, list) and ac and all(isinstance(x,str) and x.strip() for x in ac), 'TASK_ACCEPTANCE_REQUIRED')
    for section, fields in {'task':['source_ref'], 'run':['id','runtime_epoch','runtime_plan_ref'],
                            'repository':['name','branch','worktree'], 'executor':['session_id'],
                            'workflow':['checkpoint_ref']}.items():
        for field in fields:
            require(isinstance(c[section].get(field), str) and c[section][field].strip(), 'TASK_BINDING_REQUIRED:'+section+'.'+field)
    require(re.fullmatch(r'[0-9a-f]{40}', c['repository'].get('head_sha','')), 'TASK_HEAD_INVALID')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}',c['run'].get('runtime_plan_digest','')), 'TASK_PLAN_DIGEST_INVALID')
    require(c['workflow'].get('id') == 'generic-m1-m7' and tuple(c['workflow'].get('activities',[])) == ACTIVITIES, 'TASK_TOPOLOGY_INVALID')
    require(c['workflow'].get('mode','PROTECTED_TYPED_CE') in {'PROTECTED_TYPED_CE','Q0_ENGINEERING_COORDINATION'}, 'TASK_WORKFLOW_MODE_INVALID')
    u = urlsplit(c['controller'].get('conversation_url',''))
    require(u.scheme == 'https' and u.netloc == 'chatgpt.com' and '/c/' in u.path and not u.query and not u.fragment, 'CONTROLLER_URL_INVALID')
    require(c['controller'].get('interaction_mode') == 'hermes_skill', 'CONTROLLER_MODE_INVALID')
    cap = c['capabilities'].get('controller_exchange',{})
    require(cap.get('provider') == 'hermes_skills' and cap.get('transport') == 'browser'
            and cap.get('receipt_type') == 'BROWSER_EXCHANGE_VERIFIED'
            and isinstance(cap.get('skill_ref'),str) and bool(cap['skill_ref']), 'BROWSER_CAPABILITY_INVALID')
    return c


def bind_from_plan(root, *, plan_ref, conversation_url, session_id, checkpoint_ref, skill_ref):
    """Resolve objective/AC from real committed plan, not invented Jira content."""
    root = Path(root).resolve(); plan_path = (root/plan_ref).resolve()
    require(plan_path.is_relative_to(root), 'TASK_PLAN_PATH_ESCAPE')
    def git(*args):
        return subprocess.check_output(['git','-C',str(root),*args])
    head = git('rev-parse','HEAD').decode().strip()
    source = git('show',head+':'+str(plan_path.relative_to(root)))
    require(plan_path.read_bytes() == source, 'TASK_PLAN_SOURCE_DRIFT')
    p = json.loads(source); branch = git('branch','--show-current').decode().strip()
    require(branch == p['branch'], 'TASK_BRANCH_MISMATCH')
    return validate_task_context({
        'schema_version':1,
        'task':{'id':p['parent_task'], 'objective':p['goal'], 'acceptance_criteria':p['acceptance_criteria'], 'source_ref':plan_ref},
        'run':{'id':p['run_id'],'runtime_epoch':p['runtime_epoch'],'runtime_plan_ref':plan_ref,'runtime_plan_digest':'sha256:'+hashlib.sha256(source).hexdigest()},
        'runtime_plan':{'scope':p['scope'], 'dependencies':p.get('depends_on',[]),
                        'authority_basis':p.get('authority_basis',{}), 'recursive_plan':p.get('recursive_plan',{})},
        'repository':{'name':p['source_repo'],'branch':branch,'head_sha':head,'worktree':str(root)},
        'controller':{'type':'GPT','conversation_url':conversation_url,'interaction_mode':'hermes_skill'},
        'executor':{'type':'hermes','session_id':session_id},
        'workflow':{'id':'generic-m1-m7','checkpoint_ref':str(checkpoint_ref),'activities':list(ACTIVITIES)},
        'capabilities':{'controller_exchange':{'provider':'hermes_skills','skill_ref':skill_ref,'transport':'browser','receipt_type':'BROWSER_EXCHANGE_VERIFIED'}},
    })
