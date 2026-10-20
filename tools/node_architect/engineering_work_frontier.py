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
        'g1_revision_candidate':{
            'candidate_id':'Q0-CONTROLLED-FAILURE-CAMPAIGN-CANDIDATE',
            'status':'CANDIDATE_ONLY_NOT_ACTIVATED',
            'goal':'Qualify GWC Universal V2 against a controlled, reproducible runtime failure without claiming the original DWO incident was reproduced.',
            'dependencies':[
                {'id':'CF-PRECHECK','depends_on':[],'objective':'Bind exact source/runtime identity and validate the recursive dependency DAG.','evidence':['source SHA','RuntimePlan digest','acyclic atomic frontier report']},
                {'id':'CF-RED','depends_on':['CF-PRECHECK'],'objective':'Select a permitted controlled failure scenario and demonstrate a genuine failing RED.','evidence':['scenario provenance','input/state digest','failing command and error boundary']},
                {'id':'CF-FIX','depends_on':['CF-RED'],'objective':'Repair the bounded GWC runtime defect with RED→GREEN on the same branch.','evidence':['minimal source diff','focused GREEN logs','additive commit and remote SHA']},
                {'id':'CF-LOAD','depends_on':['CF-FIX'],'objective':'Reload the exact fixed source identity and prove the active runtime loaded it.','evidence':['commit SHA','process/session identity','loaded module/profile digest','regenerated dependent digests']},
                {'id':'CF-REPLAY','depends_on':['CF-LOAD'],'objective':'Replay the controlled failure and prove forward progress beyond the prior failure boundary.','evidence':['scenario/input digest','replay result','readback beyond prior boundary']},
                {'id':'CF-CERTIFY','depends_on':['CF-REPLAY'],'objective':'Run the qualification matrix and prepare a draft evidence handoff.','evidence':['matrix results','regression logs','draft certification dossier']}
            ],
            'acceptance_criteria':[
                {'id':'CF-AC-01','statement':'Controlled scenario is explicitly distinguished from DWO-LOGIN-AUTH-R1.','evidence':['scenario provenance record','original_incident_replayed=false']},
                {'id':'CF-AC-02','statement':'A genuine RED is observed before the minimal runtime fix and focused GREEN after it.','evidence':['red log','diff','green log']},
                {'id':'CF-AC-03','statement':'Runtime reload proves the exact source commit and loaded module/profile identities.','evidence':['commit SHA','process/session','loaded identities','artifact digests']},
                {'id':'CF-AC-04','statement':'Controlled replay advances beyond its prior failure boundary and the required matrix passes.','evidence':['replay readback','matrix results','regression logs']}
            ],
            'evidence_requirements':['immutable scenario/input digest','source-bound RED/GREEN logs','exact load proof','controlled replay readback','qualification matrix'],
            'requires_human_decision':True,
            'activation_condition':'An explicit human decision changing the acceptance target plus a validated immutable successor G1 RuntimePlan.',
            'boundary':'This candidate does not change the current RuntimePlan, activate execution, close F2-INCIDENT-RED, or qualify the original DWO incident.'
        },
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


def terminal_blocker_identity(*,run_id,runtime_plan_digest,activity,reason_code,work,frontier):
    """Stable identity for one blocker across additive source-head changes."""
    rows=[]
    for row in (frontier or {}).get('items',[]):
        if row.get('status') in {'BLOCKED_EXTERNAL_EVIDENCE','BLOCKED_AUTHORITY','WAIT_INPUT'}:
            item=row.get('work') or {}
            rows.append({'id':row.get('id'),'status':row.get('status'),
                         'plan_node_id':item.get('plan_node_id'),
                         'missing_inputs':sorted(item.get('missing_inputs',[])),
                         'missing_external_evidence':sorted(item.get('missing_external_evidence',[]))})
    selected=work or {}
    return digest({'run_id':run_id,'runtime_plan_digest':runtime_plan_digest,
                   'activity':activity,'reason_code':reason_code,
                   'work_id':selected.get('id'),'work_action':selected.get('action'),
                   'blocked_dependencies':sorted(rows,key=lambda x:(x.get('id') or '',x.get('status') or ''))})


def controller_dispatch_required(activity,reason_code):
    """True only for material blockers that need a Controller decision.

    ACK #69: mandatory reporting is not mandatory approval. A routine firing is
    telemetry; only a material blocker, plan conflict or E2E handoff creates a
    Controller decision request.
    """
    return ((activity=='M2' and reason_code=='ENGINEERING_NEW_INTENT_RECONCILIATION_REQUIRED') or
            (activity=='M3' and reason_code=='ENGINEERING_FRONTIER_WAIT_INPUT') or
            (activity=='M4' and reason_code=='ENGINEERING_EXTERNAL_DEPENDENCY') or
            (activity=='M5' and reason_code in {'ENGINEERING_EFFECT_AUTHORITY_REQUIRED',
                                                 'ENGINEERING_NEW_INTENT_RECONCILIATION_REQUIRED'}))
