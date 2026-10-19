"""Outbox concurrency, uncertainty and receipt binding; synthetic host fixtures."""
import pytest
from test_task_context_binding import context
from tools.node_architect.controller_exchange_adapter import ExchangeOutbox, make_exchange_request, resume_host_exchange, reconcile_controller_response


def test_pending_survives_restart_and_does_not_send_twice(tmp_path):
    req = make_exchange_request(context(), 'Review the implementation', lane='HOST_COORDINATION')
    p = tmp_path/'outbox.sqlite'
    first = ExchangeOutbox(p); assert first.reserve(req) is True
    assert ExchangeOutbox(p).reserve(req) is False
    assert ExchangeOutbox(p).read(req)['status'] == 'EXCHANGE_REQUESTED'
    calls = []
    def read_only(request):
        calls.append(request['marker'])
        return {'status':'TRANSPORT_BLOCKED','reason':'RESPONSE_NOT_YET_VERIFIED'}
    result = resume_host_exchange(context(), req, ExchangeOutbox(p),
                                  {'dwa-gpt-exchange.read':read_only})
    assert result['status'] == 'TRANSPORT_BLOCKED'
    assert calls == [req['marker']]
    assert first.reserve(req) is False


def test_unknown_delivery_is_never_automatically_retried(tmp_path):
    req = make_exchange_request(context(), 'Report', lane='M7')
    box = ExchangeOutbox(tmp_path/'box.sqlite');box.reserve(req)
    box.record(req, {'status':'TRANSPORT_BLOCKED','reason':'UI_UNKNOWN'})
    assert box.reserve(req) is False


def test_response_cannot_bind_other_conversation(tmp_path):
    req = make_exchange_request(context(), 'Review', lane='M7')
    box = ExchangeOutbox(tmp_path/'box.sqlite');box.reserve(req)
    with pytest.raises(ValueError, match='EXCHANGE_RECEIPT_BINDING_MISMATCH'):
        box.record(req, {'status':'CONTROLLER_RESPONSE_VERIFIED','conversation_url':'https://chatgpt.com/c/other',
                         'request_digest':req['request_digest']})


def test_native_admission_is_not_a_browser_outcome(tmp_path):
    req = make_exchange_request(context(), 'Review', lane='HOST_COORDINATION')
    box = ExchangeOutbox(tmp_path/'box.sqlite');box.reserve(req)
    with pytest.raises(ValueError, match='EXCHANGE_OUTCOME_INVALID'):
        box.record(req, {'status':'TYPED_CE_ADMITTED'})


def test_shared_response_reconciliation_binds_weak_receipt_to_exact_request():
    req=make_exchange_request(context(),'Review exact run result',lane='HOST_COORDINATION')
    receipt={'status':'CONTROLLER_ACTION_REQUIRED','request_digest':req['request_digest'],
        'conversation_url':req['conversation_url'],'marker':req['marker'],'task_id':req['task_id'],
        'run_id':req['run_id'],'session_id':req['session_id'],'user_turn_ref':'user-turn-1',
        'assistant_turn_ref':'assistant-turn-1','response_to_marker':req['marker'],
        'response_text':'ACK: SEARCH_EXHAUSTED / WAIT_EXTERNAL_EVIDENCE.',
        'response_complete_observed':True,'receipt_strength':'RENDERED_TEXT_CORRELATION_ONLY',
        'strong_receipt_verified':False,'workflow_resume_allowed':False,
        'evidence_class':'BROWSER_EXCHANGE_VERIFIED','authority_granted':False,'typed_ce_admitted':False}
    state={'status':'CONTROLLER_ACTION_REQUIRED','receipt':receipt}
    observation=reconcile_controller_response(req,state)
    assert observation['classification']=='RENDERED_TEXT_CORRELATED_WEAK'
    assert observation['request_digest']==req['request_digest']
    assert observation['response_to_marker']==req['marker']
    assert observation['authority_granted'] is False and observation['typed_ce_admitted'] is False
    assert observation['workflow_resume_allowed'] is False


def test_resume_host_exchange_recovers_stage_after_pre_invocation_tool_rejection(tmp_path):
    from tools.node_architect.hermes_skill_capability_bridge import resolve_hermes_skills
    c=context();req=make_exchange_request(c,'Exact reserved report',lane='HOST_COORDINATION')
    box=ExchangeOutbox(tmp_path/'box.sqlite');assert box.reserve(req)
    skill=tmp_path/'SKILL.md';skill.write_text('---\nname: dwa-gpt-exchange\n---\n')
    registry=resolve_hermes_skills(c,skill_path=skill,host_session_id='session',
        preview={'url':c['controller']['conversation_url']},outbox=box)
    inventory={'url':req['conversation_url'],'elements':[{'role':'textbox','label':'Ask ChatGPT','ref':'fresh-composer','value':'','disabled':False}]}
    registry['bridge'].stage(req,inventory,composer_empty_confirmed=True,idle_confirmed=True)
    failure={'request_digest':req['request_digest'],'tool':'functions.tool_call','action':'type',
        'error_code':'CALL_ITEM_NAME_REQUIRED','browser_action_invoked':False}
    action=resume_host_exchange(c,req,box,registry,phase='stage',inventory=inventory,
        dispatch_failure=failure,idle_confirmed=True)
    assert action['tool']=='drive_preview'
    assert action['arguments']=={'action':'type','ref':'fresh-composer','text':req['marker']+'\n'+req['report'],'submit':False}
    assert box.read(req)['status']=='EXCHANGE_REQUESTED'
    with box._db() as db:
        phases=db.execute('SELECT phase FROM host_actions WHERE key=? ORDER BY phase',(req['request_digest'],)).fetchall()
    assert phases==[('STAGE',),('TYPE_REPLAY',)]


def test_resume_host_exchange_requires_matching_pre_invocation_failure_and_is_one_shot(tmp_path):
    from tools.node_architect.hermes_skill_capability_bridge import resolve_hermes_skills
    c=context();req=make_exchange_request(c,'Exact reserved report',lane='HOST_COORDINATION')
    box=ExchangeOutbox(tmp_path/'box.sqlite');assert box.reserve(req)
    skill=tmp_path/'SKILL.md';skill.write_text('---\nname: dwa-gpt-exchange\n---\n')
    registry=resolve_hermes_skills(c,skill_path=skill,host_session_id='session',
        preview={'url':c['controller']['conversation_url']},outbox=box)
    inventory={'url':req['conversation_url'],'elements':[{'role':'textbox','label':'Ask ChatGPT','ref':'composer','value':'','disabled':False}]}
    registry['bridge'].stage(req,inventory,composer_empty_confirmed=True,idle_confirmed=True)
    failure={'request_digest':req['request_digest'],'tool':'functions.tool_call','action':'type',
        'error_code':'CALL_ITEM_NAME_REQUIRED','browser_action_invoked':True}
    with pytest.raises(ValueError,match='HOST_STAGE_RECOVERY_EVIDENCE_INVALID'):
        resume_host_exchange(c,req,box,registry,phase='stage',inventory=inventory,
            dispatch_failure=failure,idle_confirmed=True)
    failure['browser_action_invoked']=False
    action=resume_host_exchange(c,req,box,registry,phase='stage',inventory=inventory,
        dispatch_failure=failure,idle_confirmed=True)
    assert action['arguments']['text']==req['marker']+'\n'+req['report']
    with pytest.raises(ValueError,match='HOST_TYPE_REPLAY_ALREADY_CLAIMED'):
        resume_host_exchange(c,req,box,registry,phase='stage',inventory=inventory,
            dispatch_failure=failure,idle_confirmed=True)


def test_resume_host_exchange_fails_closed_when_composer_value_is_unknown(tmp_path):
    from tools.node_architect.hermes_skill_capability_bridge import resolve_hermes_skills
    c=context();req=make_exchange_request(c,'Exact reserved report',lane='HOST_COORDINATION')
    box=ExchangeOutbox(tmp_path/'box.sqlite');assert box.reserve(req)
    skill=tmp_path/'SKILL.md';skill.write_text('---\nname: dwa-gpt-exchange\n---\n')
    registry=resolve_hermes_skills(c,skill_path=skill,host_session_id='session',
        preview={'url':c['controller']['conversation_url']},outbox=box)
    empty={'url':req['conversation_url'],'elements':[{'role':'textbox','label':'Ask ChatGPT','ref':'composer','value':'','disabled':False}]}
    registry['bridge'].stage(req,empty,composer_empty_confirmed=True,idle_confirmed=True)
    unknown={'url':req['conversation_url'],'elements':[{'role':'textbox','label':'Ask ChatGPT','ref':'fresh-composer','disabled':False}]}
    failure={'request_digest':req['request_digest'],'tool':'functions.tool_call','action':'type',
        'error_code':'CALL_ITEM_NAME_REQUIRED','browser_action_invoked':False}
    with pytest.raises(ValueError,match='HOST_COMPOSER_VALUE_UNKNOWN'):
        resume_host_exchange(c,req,box,registry,phase='stage',inventory=unknown,
            dispatch_failure=failure,idle_confirmed=True)
    with box._db() as db:
        assert db.execute('SELECT 1 FROM host_actions WHERE key=? AND phase=?',(req['request_digest'],'TYPE_REPLAY')).fetchone() is None


@pytest.mark.parametrize('field,value',[
    ('session_id','other-session'),('run_id','other-run'),('conversation_url','https://chatgpt.com/c/other'),
    ('response_to_marker','DWA-REVIEW-OTHER'),('assistant_turn_ref',''),('evidence_class','UNVERIFIED'),
    ('workflow_resume_allowed',True),('authority_granted',True),('typed_ce_admitted',True),
    ('response_complete_observed',False),('response_text','')])
def test_shared_response_reconciliation_rejects_misbound_or_unsafe_receipt(field,value):
    req=make_exchange_request(context(),'Review exact run result',lane='HOST_COORDINATION')
    receipt={'status':'CONTROLLER_ACTION_REQUIRED','request_digest':req['request_digest'],
        'conversation_url':req['conversation_url'],'marker':req['marker'],'task_id':req['task_id'],
        'run_id':req['run_id'],'session_id':req['session_id'],'user_turn_ref':'user-turn-1',
        'assistant_turn_ref':'assistant-turn-1','response_to_marker':req['marker'],
        'response_text':'response','response_complete_observed':True,
        'receipt_strength':'RENDERED_TEXT_CORRELATION_ONLY','strong_receipt_verified':False,
        'workflow_resume_allowed':False,'evidence_class':'BROWSER_EXCHANGE_VERIFIED',
        'authority_granted':False,'typed_ce_admitted':False}
    receipt[field]=value
    with pytest.raises(ValueError,match='CONTROLLER_RESPONSE_'):
        reconcile_controller_response(req,{'status':'CONTROLLER_ACTION_REQUIRED','receipt':receipt})
