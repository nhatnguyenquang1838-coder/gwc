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
