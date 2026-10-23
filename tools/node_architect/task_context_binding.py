"""Generic task binding. Identity and source readback are not effect authority."""
from __future__ import annotations
import copy
import hashlib
import json
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
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


def build_context_manifest(context) -> dict:
    """Capture the complete source binding so a prior context can be proven later."""
    c = validate_task_context(context)
    engineering = c.get('engineering', {})
    plan_digest = c['run']['runtime_plan_digest']
    return {
        'schema_version': 1,
        'context_digest': digest(c),
        'head_sha': c['repository']['head_sha'],
        'branch': c['repository']['branch'],
        'worktree': c['repository']['worktree'],
        'plan_ref': c['run']['runtime_plan_ref'],
        'plan_blob_sha256': plan_digest.removeprefix('sha256:'),
        'runtime_plan_digest': plan_digest,
        'route_policy_ref': engineering.get('route_policy_ref'),
        'route_policy_digest': engineering.get('route_policy_digest'),
        'conversation_url': c['controller']['conversation_url'],
        'session_id': c['executor']['session_id'],
        'checkpoint_ref': c['workflow']['checkpoint_ref'],
        'workflow_epoch': c['run']['runtime_epoch'],
        'workflow_id': c['workflow']['id'],
        'previous_context_digest': c.get('previous_context_digest'),
        # This is required to reconstruct the exact historical binding; digest-only
        # evidence cannot establish equality with the checkpoint's stored context.
        'context': c,
    }


def seal_context_manifest(checkpoint_ref, manifest, *, authorized: bool = False) -> str:
    """Persist a manifest only after the caller has validated its context."""
    require(authorized is True, 'MANIFEST_SEAL_NOT_AUTHORIZED')
    manifest_digest = digest(manifest)
    Path(checkpoint_ref).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(checkpoint_ref), timeout=30) as db:
        db.execute('CREATE TABLE IF NOT EXISTS engineering_context_manifests('
                   'manifest_digest TEXT PRIMARY KEY, run TEXT, context_digest TEXT, '
                   'manifest TEXT, sealed_at TEXT)')
        db.execute('INSERT OR IGNORE INTO engineering_context_manifests '
                   '(manifest_digest,run,context_digest,manifest,sealed_at) VALUES (?,?,?,?,?)',
                   (manifest_digest, manifest.get('context', {}).get('run', {}).get('id'),
                    manifest.get('context_digest'),
                    json.dumps(manifest, sort_keys=True, separators=(',', ':')),
                    datetime.now(timezone.utc).isoformat()))
    return manifest_digest


def load_context_manifests(checkpoint_ref, run) -> list[dict]:
    """Return sealed rows as dictionaries, in their durable sealing order."""
    with sqlite3.connect(str(checkpoint_ref), timeout=30) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                            ('engineering_context_manifests',)).fetchone()
        if not exists:
            return []
        rows = db.execute('SELECT manifest_digest,run,context_digest,manifest,sealed_at '
                          'FROM engineering_context_manifests WHERE run=? ORDER BY sealed_at, rowid',
                          (run,)).fetchall()
    return [{'manifest_digest': row[0], 'run': row[1], 'context_digest': row[2],
             'manifest': row[3], 'sealed_at': row[4]} for row in rows]


def _leaf_differences(old, new, prefix=''):
    if isinstance(old, dict) and isinstance(new, dict):
        result = []
        for key in sorted(set(old) | set(new)):
            path = f'{prefix}.{key}' if prefix else key
            if key not in old or key not in new:
                value = new[key] if key in new else old[key]
                result.extend(_tree_leaf_paths(value, path))
            else:
                result.extend(_leaf_differences(old[key], new[key], path))
        return result
    return [] if old == new else [prefix]


def _tree_leaf_paths(value, prefix):
    if isinstance(value, dict) and value:
        return [leaf for key in sorted(value)
                for leaf in _tree_leaf_paths(value[key], f'{prefix}.{key}')]
    return [prefix]


def classify_context_delta(old_context, new_context, *, repository_root=None) -> dict:
    """Classify context changes deterministically without granting reconciliation."""
    try:
        old = validate_task_context(old_context)
        new = validate_task_context(new_context)
    except (TypeError, ValueError, AttributeError):
        return {'classification': 'UNKNOWN', 'changed_fields': [], 'head_only': False,
                'detail': {'reason': 'invalid_task_context'}}

    changed = _leaf_differences(old, new)
    detail = {}
    if 'run.runtime_plan_ref' in changed or 'run.runtime_plan_digest' in changed:
        return {'classification': 'PLAN_TRANSITION', 'changed_fields': changed,
                'head_only': False, 'detail': detail}

    head_path = 'repository.head_sha'
    non_head = [field for field in changed if field != head_path]
    if non_head:
        # Task inputs, route policy identity, and edits/removals to existing
        # engineering fields remain material even when other metadata is added.
        if ('controller.conversation_url' in changed and len(changed) == 1):
            kind = 'SESSION_ROTATION'
        else:
            route_digest_unchanged = (old.get('engineering', {}).get('route_policy_digest') ==
                                      new.get('engineering', {}).get('route_policy_digest'))
            additive_engineering = all(
                field.startswith('engineering.') and
                field != 'engineering.work_items' and
                _path_missing(old, field) and _path_present(new, field)
                for field in non_head
            )
            if additive_engineering and route_digest_unchanged:
                kind = 'ADDITIVE_ROUTE_METADATA'
            else:
                kind = 'MATERIAL_DRIFT'
        return {'classification': kind, 'changed_fields': changed,
                'head_only': False, 'detail': detail}

    if changed and changed != [head_path]:
        return {'classification': 'MATERIAL_DRIFT', 'changed_fields': changed,
                'head_only': False, 'detail': detail}
    if old['repository']['head_sha'] == new['repository']['head_sha']:
        return {'classification': 'HEAD_ONLY_SAFE', 'changed_fields': changed,
                'head_only': not changed, 'detail': {'ancestor_verified': True}}

    if repository_root is None:
        return {'classification': 'HEAD_ONLY_UNVERIFIED', 'changed_fields': changed,
                'head_only': True, 'detail': {'ancestor_verified': False}}
    try:
        subprocess.run(['git', '-C', str(Path(repository_root).resolve()), 'merge-base',
                        '--is-ancestor', old['repository']['head_sha'],
                        new['repository']['head_sha']], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return {'classification': 'HEAD_ONLY_UNVERIFIED', 'changed_fields': changed,
                'head_only': True, 'detail': {'ancestor_verified': False}}
    return {'classification': 'HEAD_ONLY_SAFE', 'changed_fields': changed,
            'head_only': True, 'detail': {'ancestor_verified': True}}


def _path_missing(value, dotted_path):
    for key in dotted_path.split('.'):
        if not isinstance(value, dict) or key not in value:
            return True
        value = value[key]
    return False


def _path_present(value, dotted_path):
    return not _path_missing(value, dotted_path)
