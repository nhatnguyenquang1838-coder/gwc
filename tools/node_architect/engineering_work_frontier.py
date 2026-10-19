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


def build_recovery_decision_packet(*,run_id,goal,runtime_plan,frontier):
    """Describe exhausted-frontier options without mutating the frozen plan.

    This is Controller-planning evidence only. It cannot create READY work,
    change acceptance criteria, grant effect authority, or release external
    evidence requirements.
    """
    require(isinstance(run_id,str) and run_id,'RECOVERY_RUN_ID_REQUIRED')
    require(isinstance(goal,str) and goal.strip(),'RECOVERY_GOAL_REQUIRED')
    require(isinstance(runtime_plan,dict),'RECOVERY_RUNTIME_PLAN_REQUIRED')
    require(isinstance(frontier,dict) and frontier.get('selected_work') is None,
            'RECOVERY_FRONTIER_NOT_EXHAUSTED')
    require(frontier.get('authority_granted') is False,'RECOVERY_AUTHORITY_MUST_REMAIN_FALSE')
    items=frontier.get('items',[])
    root=runtime_plan.get('recursive_plan',runtime_plan)
    completed=[{'id':row['id'],'status':'VERIFIED'} for row in items if row.get('status')=='VERIFIED']
    blocked=[]
    for row in items:
        if row.get('status') in {'BLOCKED_EXTERNAL_EVIDENCE','BLOCKED_AUTHORITY','WAIT_INPUT'}:
            work=row.get('work') or {}
            blocked.append({'id':row['id'],'status':row['status'],
                            'missing_inputs':list(work.get('missing_inputs',[])),
                            'missing_external_evidence':list(work.get('missing_external_evidence',[])),
                            'plan_node_id':work.get('plan_node_id')})
    return {
        'schema_id':'gwc.q0.recovery-decision-proposal/v1',
        'run_id':run_id,
        'goal':goal,
        'source_head':frontier.get('source_head'),
        'runtime_plan_digest':frontier.get('runtime_plan_digest'),
        'plan_root_id':root.get('id') if isinstance(root,dict) else None,
        'plan_root_atomic':root.get('atomic') if isinstance(root,dict) else None,
        'frontier_digest':digest(frontier),
        'completed_work_ids':sorted(row['id'] for row in completed),
        'blocked_dependencies':blocked,
        'alternatives':[
            {'id':'RECOVER_ORIGINAL_TRACE',
             'description':'Obtain and validate the authentic original DWO execution trace, then reproduce that failure.',
             'requires_human_decision':False,
             'release_condition':['execution_host','original_run_id','failing_input_and_pre_state',
                                  'error_boundary','immutable_artifact_locator_and_digest'],
             'boundary':'Until those inputs are validated, original replay remains BLOCKED_EXTERNAL_EVIDENCE.'},
            {'id':'PROPOSE_G1_ACCEPTANCE_REPLAN',
             'description':'Prepare a controlled runtime-failure campaign as a candidate alternative verification target.',
             'requires_human_decision':True,
             'release_condition':['immutable_successor_G1_plan','explicit_human_acceptance_target_decision'],
             'boundary':'A controlled failure does not reproduce the original DWO incident and does not close F2-INCIDENT-RED.'}
        ],
        'recommended_action':'WAIT_FOR_TRACE_OR_HUMAN_G1_DECISION',
        'decision_owner':'original trace holder for option A; human for acceptance-target change in option B',
        'proposal_only':True,
        'plan_mutated':False,
        'authority_granted':False,
        'acceptance_target_changed':False
    }


def classify_controller_observation(response_text):
    """Recognize only stable advisory disposition tokens; never yields authority.

    The browser bridge may provide rendered-text correlation without a strong
    assistant-turn identity. That evidence can update the local planning
    observation, but cannot become typed NEXT or release any gate/effect.
    """
    require(isinstance(response_text,str) and response_text.strip(),
            'CONTROLLER_RESPONSE_TEXT_REQUIRED')
    text=response_text.upper()
    if 'SEARCH_EXHAUSTED' in text and 'WAIT_EXTERNAL_EVIDENCE' in text:
        disposition='SEARCH_EXHAUSTED_WAIT_EXTERNAL_EVIDENCE'
        planning_state='WAIT_EXTERNAL_INPUT'
        owner='original trace holder; human only for acceptance-target change'
    else:
        disposition='UNCLASSIFIED_ADVISORY_RESPONSE'
        planning_state='UNCHANGED'
        owner='DWA must review the exact correlated response'
    return {'disposition':disposition,'planning_state':planning_state,'owner':owner,
            'typed_next':False,'authority_granted':False,'acceptance_target_changed':False}
