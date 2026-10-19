"""Source/plan-bound engineering frontier projection; never grants authority."""
from __future__ import annotations
from fnmatch import fnmatchcase
from pathlib import PurePosixPath
from .task_context_binding import digest,require


def work_within_scope(context,item):
    scope=context['runtime_plan']['scope']
    if item.get('action') not in scope.get('allowed_actions',[]):return False
    paths=item.get('write_paths',[])
    if item.get('action')=='modify_approved_files' and not paths:return False
    return all(isinstance(p,str) and not PurePosixPath(p).is_absolute() and
               '..' not in PurePosixPath(p).parts and
               any(fnmatchcase(p,pattern) for pattern in scope.get('writable_targets',[])) for p in paths)


def project_frontier(context,items,*,verified_fingerprints):
    """Classify candidates under the frozen plan, not a replacement RuntimePlan.

    Host supplies current source-bound candidates and actual VERIFIED work keys.
    A status is scheduling evidence, never an effect or certification receipt.
    """
    nodes=set()
    def visit(node):
        require(node.get('id') and node['id'] not in nodes,'FRONTIER_PLAN_INVALID')
        nodes.add(node['id'])
        for child in node.get('children',[]):visit(child)
    visit(context['runtime_plan']['recursive_plan'])
    require(len({i['id'] for i in items})==len(items),'FRONTIER_DUPLICATE_WORK_ID')
    verified=set(verified_fingerprints);done={i['id'] for i in items if digest(i) in verified};rows=[]
    for item in sorted(items,key=lambda i:(i['priority'],i['id'])):
        require(item.get('plan_node_id') in nodes,'FRONTIER_PLAN_NODE_UNKNOWN')
        require(item.get('input_digest'),'FRONTIER_INPUT_BINDING_REQUIRED')
        if digest(item) in verified:status='VERIFIED'
        elif not work_within_scope(context,item):status='BLOCKED_AUTHORITY'
        elif item.get('missing_external_evidence'):status='BLOCKED_EXTERNAL_EVIDENCE'
        elif item.get('missing_inputs') or any(d not in done for d in item.get('depends_on',[])):status='WAIT_INPUT'
        else:status='READY'
        rows.append({'id':item['id'],'status':status,'work':item,'fingerprint':digest(item)})
    ready=[r for r in rows if r['status']=='READY']
    return {'source_head':context['repository']['head_sha'],'runtime_plan_digest':context['run']['runtime_plan_digest'],
            'items':rows,'selected_work':ready[0]['work'] if ready else None,'authority_granted':False}
