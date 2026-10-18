"""Host bridge emits real Desktop-tool actions; these are synthetic fixtures."""
from pathlib import Path
import pytest
from test_task_context_binding import context
from tools.node_architect.controller_exchange_adapter import ExchangeOutbox,make_exchange_request
from tools.node_architect.hermes_skill_capability_bridge import resolve_hermes_skills


def test_bridge_resolves_installed_skill_but_never_registers_typed_observer(tmp_path):
    p=tmp_path/'SKILL.md';p.write_text('---\nname: dwa-gpt-exchange\nversion: 1.0.0\n---\n')
    c=context();b=ExchangeOutbox(tmp_path/'outbox');r=make_exchange_request(c,'review',lane='HOST_COORDINATION');b.reserve(r)
    registry=resolve_hermes_skills(c,skill_path=p,host_session_id='session',preview={'url':c['controller']['conversation_url']},outbox=b)
    assert 'typed_observer.read_verified' not in registry
    action=registry['controller_exchange.read'](r)
    assert action['tool']=='desktop_preview' and action['arguments']['action']=='read'
    bridge=registry['bridge']
    result=bridge.accept_readback(r,{'url':r['conversation_url'],'text':'You said:\n'+r['marker']+'\nChatGPT said:\nReviewed '+r['task_id']}, response_complete=True)
    assert result['status']=='CONTROLLER_ACTION_REQUIRED'
    assert b.read(r)['status']=='CONTROLLER_ACTION_REQUIRED'
    assert result['receipt']['strong_receipt_verified'] is False


def test_execute_yields_agent_tool_action_without_claiming_delivery(tmp_path):
    from tools.node_architect.controller_exchange_adapter import execute_host_exchange
    p=tmp_path/'SKILL.md';p.write_text('---\nname: dwa-gpt-exchange\n---\n')
    c=context();b=ExchangeOutbox(tmp_path/'outbox');r=make_exchange_request(c,'review',lane='HOST_COORDINATION')
    registry=resolve_hermes_skills(c,skill_path=p,host_session_id='session',preview={'url':c['controller']['conversation_url']},outbox=b)
    action=execute_host_exchange(c,r,b,registry)
    assert action['status']=='HOST_ACTION_REQUIRED'
    assert b.read(r)['status']=='EXCHANGE_REQUESTED'


def test_bridge_stage_is_durably_at_most_once(tmp_path):
    p=tmp_path/'SKILL.md';p.write_text('---\nname: dwa-gpt-exchange\n---\n')
    c=context();b=ExchangeOutbox(tmp_path/'outbox');r=make_exchange_request(c,'review',lane='HOST_COORDINATION');b.reserve(r)
    registry=resolve_hermes_skills(c,skill_path=p,host_session_id='session',preview={'url':c['controller']['conversation_url']},outbox=b)
    inventory={'url':r['conversation_url'],'elements':[{'role':'textbox','label':'Ask ChatGPT','ref':'fixture-composer'}]}
    registry['bridge'].stage(r,inventory,composer_empty_confirmed=True,idle_confirmed=True)
    with pytest.raises(ValueError,match='HOST_ACTION_ALREADY_CLAIMED'):
        registry['bridge'].stage(r,inventory,composer_empty_confirmed=True,idle_confirmed=True)


def test_m7_hold_cannot_emit_browser_exchange():
    from tools.node_architect.task_m1_m7_runner import build_task_graph
    graph,_=build_task_graph(context())
    result=graph.builder.nodes['M7'].runnable.invoke({'inputs':{'controller_report':'report'}})
    assert result['status']=='HOLD'
    assert not result.get('controller_exchange_requests')


def test_text_only_response_remains_a_weak_receipt(tmp_path):
    p=tmp_path/'SKILL.md';p.write_text('---\nname: dwa-gpt-exchange\n---\n')
    c=context();b=ExchangeOutbox(tmp_path/'outbox');r=make_exchange_request(c,'review',lane='HOST_COORDINATION');b.reserve(r)
    registry=resolve_hermes_skills(c,skill_path=p,host_session_id='session',preview={'url':c['controller']['conversation_url']},outbox=b)
    result=registry['bridge'].accept_readback(r,{'url':r['conversation_url'],'text':'You said:\n'+r['marker']+'\nChatGPT said:\nReviewed '+r['task_id']},response_complete=True)
    assert result['status']=='CONTROLLER_ACTION_REQUIRED'
    assert result['receipt']['reason']=='HOST_UI_TURN_IDENTITY_UNAVAILABLE'


def test_wrong_session_is_not_registered(tmp_path):
    p=tmp_path/'SKILL.md';p.write_text('---\nname: dwa-gpt-exchange\n---\n')
    with pytest.raises(ValueError,match='HOST_SESSION_MISMATCH'):
        resolve_hermes_skills(context(),skill_path=p,host_session_id='other',preview={},outbox=None)
