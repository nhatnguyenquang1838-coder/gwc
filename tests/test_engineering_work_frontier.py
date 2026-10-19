"""Plan-bound frontier continuation without protected admission or fake evidence."""
import pytest
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
