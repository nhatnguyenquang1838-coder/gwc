"""Outbox concurrency, uncertainty and receipt binding; synthetic host fixtures."""
import pytest
from test_task_context_binding import context
from tools.node_architect.controller_exchange_adapter import ExchangeOutbox, make_exchange_request, resume_host_exchange


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
