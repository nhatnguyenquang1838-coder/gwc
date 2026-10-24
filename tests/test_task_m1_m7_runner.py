"""Generic graph invokes frozen M1-M7 activities without task-ID rebinding hacks."""
import pytest
from test_task_context_binding import context
from tools.node_architect.task_m1_m7_runner import run_task_workflow


@pytest.mark.parametrize('task',['TASK-A','TASK-B'])
def test_unqualified_graph_holds_but_explicit_coordination_is_separate(tmp_path, task):
    c = context(task);c['workflow']['checkpoint_ref'] = str(tmp_path/'state.sqlite')
    out = run_task_workflow(c, host_capabilities={}, report='Please review', coordination_authorized=True)
    assert out['verdict']['current_activity'] == 'M1'
    assert out['verdict']['reason_code'] == 'OBSERVER_UNQUALIFIED'
    assert out['coordination_request']['lane'] == 'HOST_COORDINATION'
    assert out['coordination_request']['task_id'] == task
    assert out['checkpoint_readback'] == 'PASS'
    assert out['typed_ce_admitted'] is False
    assert out['graph_requests'] == []
    again = run_task_workflow(c, host_capabilities={}, report='Please review', coordination_authorized=True)
    assert again['coordination_request']['request_digest'] == out['coordination_request']['request_digest']
    first_tick = run_task_workflow(c,host_capabilities={},invocation_key='fixture-native-1')
    repeated_tick = run_task_workflow(c,host_capabilities={},invocation_key='fixture-native-1')
    assert first_tick['invocation_replayed'] is False
    assert repeated_tick['invocation_replayed'] is True


def test_timer_alone_cannot_request_gpt_exchange(tmp_path):
    c = context();c['workflow']['checkpoint_ref'] = str(tmp_path/'state.sqlite')
    out = run_task_workflow(c, host_capabilities={}, report='Review', coordination_authorized=False)
    assert out['coordination_request'] is None
