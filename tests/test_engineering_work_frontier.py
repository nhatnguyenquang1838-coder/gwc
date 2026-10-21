"""Plan-bound frontier continuation without protected admission or fake evidence."""
import pytest
import json
from test_engineering_m1_m7_workflow import binding,capabilities
from tools.node_architect.task_m1_m7_runner import run_task_workflow
from tools.node_architect.task_context_binding import digest


def setup_frontier(tmp_path):
    c=binding(tmp_path)
    c['runtime_plan']['recursive_plan']={'id':'ROOT','atomic':False,'children':[{'id':'ORIGINAL','atomic':True}]}
    c['runtime_plan']['scope']['allowed_actions'].append('modify_approved_files')
    c['runtime_plan']['scope']['writable_targets']=['tools/**','tests/**']
    base={'priority':2,'input_digest':'sha256:'+'d'*64,'plan_node_id':'ROOT'}
    items=[{**base,'id':'trace','action':'run_sandboxed_validation','missing_external_evidence':['original trace']},
           {**base,'id':'repair','action':'modify_approved_files','write_paths':['tools/repair.py'],'depends_on':[]}]
    return c,items


def test_classify_empty_frontier_authority_vs_input_vs_exhausted():
    from tools.node_architect.engineering_work_frontier import classify_empty_frontier
    authority={'id':'restricted','status':'BLOCKED_AUTHORITY','plan_node_id':'ROOT',
               'work':{'id':'restricted','plan_node_id':'ROOT','missing_inputs':['approval']}}
    external={'id':'trace','status':'BLOCKED_EXTERNAL_EVIDENCE','plan_node_id':'ROOT',
              'work':{'id':'trace','plan_node_id':'ROOT','missing_external_evidence':['trace']}}
    assert classify_empty_frontier({'items':[authority]})=={
        'cause':'WAIT_AUTHORITY','reason_code':'ENGINEERING_FRONTIER_WAIT_AUTHORITY',
        'authority_items':[{'id':'restricted','status':'BLOCKED_AUTHORITY','plan_node_id':'ROOT',
                            'missing_inputs':['approval']} ]}
    assert classify_empty_frontier({'items':[external]})=={
        'cause':'WAIT_INPUT','reason_code':'ENGINEERING_FRONTIER_WAIT_INPUT'}
    assert classify_empty_frontier({'items':[{'id':'done','status':'VERIFIED'}]})=={
        'cause':'EXHAUSTED','reason_code':'ENGINEERING_FRONTIER_EXHAUSTED'}


def test_verified_probe_advances_to_independent_agent_work(tmp_path):
    c,items=setup_frontier(tmp_path);counts={'read':0,'execute':0}
    caps=capabilities(c,counts)
    run_task_workflow(c,host_capabilities=caps,invocation_key='probe')
    from tools.node_architect.engineering_work_frontier import project_frontier
    caps['engineering.work_frontier']=lambda ctx:project_frontier(ctx,items,verified_fingerprints=[])
    r=run_task_workflow(c,host_capabilities=caps,invocation_key='continue')
    assert r['work']['id']=='repair'
    assert next(i for i in r['work_frontier']['items'] if i['id']=='trace')['status']=='BLOCKED_EXTERNAL_EVIDENCE'
    assert r['verdict']['reason_code']=='ENGINEERING_HOST_ACTION_REQUIRED'
    assert r['host_action_request']['work_fingerprint']==r['work']['fingerprint']
    assert r['host_action_request']['authority_granted'] is False
    assert counts['execute']==1  # No repeated probe and no pretend source write.


def test_frontier_classifies_real_authority_input_and_verified(tmp_path):
    from tools.node_architect.engineering_work_frontier import project_frontier
    c,items=setup_frontier(tmp_path)
    forbidden={**items[1],'id':'production','action':'deploy_approved_release'}
    waiting={**items[1],'id':'dependent','depends_on':['unknown']}
    r=project_frontier(c,items+[forbidden,waiting],verified_fingerprints=[digest(items[1])])
    assert {i['id']:i['status'] for i in r['items']}=={'trace':'BLOCKED_EXTERNAL_EVIDENCE','repair':'VERIFIED','production':'BLOCKED_AUTHORITY','dependent':'WAIT_INPUT'}
    assert r['selected_work'] is None


def test_frontier_rejects_foreign_plan_node_and_write_escape(tmp_path):
    from tools.node_architect.engineering_work_frontier import project_frontier
    c,items=setup_frontier(tmp_path)
    with pytest.raises(ValueError,match='FRONTIER_PLAN_NODE_UNKNOWN'):
        project_frontier(c,[{**items[1],'plan_node_id':'FOREIGN'}],verified_fingerprints=[])
    r=project_frontier(c,[{**items[1],'write_paths':['production/secrets.env']}],verified_fingerprints=[])
    assert r['items'][0]['status']=='BLOCKED_AUTHORITY'


def test_unbound_frontier_does_not_enter_effect_path(tmp_path):
    from tools.node_architect.engineering_work_frontier import project_frontier
    c,items=setup_frontier(tmp_path);counts={'read':0,'execute':0};caps=capabilities(c,counts)
    run_task_workflow(c,host_capabilities=caps,invocation_key='probe')
    def wrong(ctx):
        r=project_frontier(ctx,items,verified_fingerprints=[]);r['source_head']='foreign';return r
    caps['engineering.work_frontier']=wrong
    with pytest.raises(ValueError,match='ENGINEERING_FRONTIER_BINDING_INVALID'):
        run_task_workflow(c,host_capabilities=caps,invocation_key='continue')
    assert counts['execute']==1


def test_exhausted_frontier_yields_decision_packet_without_mutating_plan():
    from tools.node_architect.engineering_work_frontier import build_recovery_decision_packet,terminal_blocker_identity
    plan={'id':'F0-Q0-QUALIFY','atomic':False,'children':[
        {'id':'F2-INCIDENT-RED','atomic':True,'depends_on':[],'children':[]},
        {'id':'F2-AGENT-INTEGRATION','atomic':True,'depends_on':[],'children':[]}]}
    projection={'source_head':'a'*40,'runtime_plan_digest':'sha256:'+'b'*64,
        'authority_granted':False,'selected_work':None,'items':[
            {'id':'original-dwo-incident-reproduction','status':'BLOCKED_EXTERNAL_EVIDENCE',
             'work':{'id':'original-dwo-incident-reproduction','missing_external_evidence':['original trace']}},
            {'id':'engineering-agent-work-receipt-integration','status':'VERIFIED',
             'work':{'id':'engineering-agent-work-receipt-integration'}}]}
    before=json.loads(json.dumps(plan))
    packet=build_recovery_decision_packet(run_id='run-Q0',goal='qualify original DWO failure',
                                           runtime_plan=plan,frontier=projection)
    assert packet['schema_id']=='gwc.q0.recovery-decision-proposal/v1'
    assert packet['proposal_only'] is True and packet['authority_granted'] is False
    assert packet['plan_root_id']=='F0-Q0-QUALIFY' and packet['plan_root_atomic'] is False
    assert packet['plan_mutated'] is False and plan==before
    assert packet['completed_work_ids']==['engineering-agent-work-receipt-integration']
    assert packet['blocked_dependencies'][0]['id']=='original-dwo-incident-reproduction'
    assert {o['id'] for o in packet['alternatives']}=={'RECOVER_ORIGINAL_TRACE','PROPOSE_G1_ACCEPTANCE_REPLAN'}
    replan=next(o for o in packet['alternatives'] if o['id']=='PROPOSE_G1_ACCEPTANCE_REPLAN')
    assert replan['requires_human_decision'] is True
    assert 'does not reproduce the original DWO incident' in replan['boundary']
    assert packet['recommended_action']=='WAIT_FOR_TRACE_OR_HUMAN_G1_DECISION'
    candidate=packet['g1_revision_candidate']
    assert candidate['status']=='CANDIDATE_ONLY_NOT_ACTIVATED'
    assert candidate['dependencies'] and candidate['acceptance_criteria'] and candidate['evidence_requirements']
    dependency_ids={d['id'] for d in candidate['dependencies']}
    seen=set()
    for dependency in candidate['dependencies']:
        assert set(dependency['depends_on'])<=seen
        assert dependency['evidence'] and dependency['objective']
        seen.add(dependency['id'])
    assert len(dependency_ids)==len(candidate['dependencies'])
    assert len({ac['id'] for ac in candidate['acceptance_criteria']})==len(candidate['acceptance_criteria'])
    assert all(ac['evidence'] and ac['statement'] for ac in candidate['acceptance_criteria'])
    assert candidate['requires_human_decision'] is True
    identity=terminal_blocker_identity(run_id='run-Q0',runtime_plan_digest='sha256:'+('b'*64),
        activity='M3',reason_code='ENGINEERING_FRONTIER_WAIT_INPUT',work=None,frontier=projection)
    changed_source={**projection,'source_head':'c'*40}
    changed_source['items']=[{**projection['items'][0],'fingerprint':'sha256:'+('d'*64)},projection['items'][1]]
    same=terminal_blocker_identity(run_id='run-Q0',runtime_plan_digest='sha256:'+('b'*64),
        activity='M3',reason_code='ENGINEERING_FRONTIER_WAIT_INPUT',work=None,frontier=changed_source)
    assert identity==same
    changed_blocker={**projection,'items':[{'id':'different','status':'BLOCKED_EXTERNAL_EVIDENCE',
        'work':{'id':'different','missing_external_evidence':['different trace']}},projection['items'][1]]}
    different=terminal_blocker_identity(run_id='run-Q0',runtime_plan_digest='sha256:'+('b'*64),
        activity='M3',reason_code='ENGINEERING_FRONTIER_WAIT_INPUT',work=None,frontier=changed_blocker)
    assert identity!=different


def test_only_material_blockers_request_a_controller_decision():
    """ACK #69: a routine firing is telemetry, not a Controller decision request."""
    from tools.node_architect.engineering_work_frontier import controller_dispatch_required
    for activity,reason in (('M2','ENGINEERING_NEW_INTENT_RECONCILIATION_REQUIRED'),
                            ('M3','ENGINEERING_FRONTIER_WAIT_INPUT'),
                            ('M4','ENGINEERING_EXTERNAL_DEPENDENCY'),
                            ('M5','ENGINEERING_EFFECT_AUTHORITY_REQUIRED')):
        assert controller_dispatch_required(activity,reason) is True
    for activity,reason in (('M5','ENGINEERING_HOST_ACTION_REQUIRED'),
                            ('M5','ENGINEERING_GENUINE_FIRING_REQUIRED'),
                            ('M6','ENGINEERING_EXECUTION_RESULT_NOT_VERIFIED'),
                            ('M6','NO_MATERIAL_CHANGE')):
        assert controller_dispatch_required(activity,reason) is False
