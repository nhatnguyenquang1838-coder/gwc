"""CR-02: reject delivery regression and stale concurrent writer evidence."""
import pytest
from test_task_context_binding import context
from tools.node_architect.controller_exchange_adapter import ExchangeOutbox, make_exchange_request


def sent(req):
    return {'status':'MESSAGE_SENT_VERIFIED', **{k:req[k] for k in ['conversation_url','request_digest','marker','task_id','run_id','session_id']},
            'user_turn_ref':'fixture-user-turn', 'evidence_class':'BROWSER_EXCHANGE_VERIFIED'}


def test_verified_delivery_cannot_be_overwritten_by_transport_failure(tmp_path):
    r=make_exchange_request(context(),'report',lane='HOST_COORDINATION');b=ExchangeOutbox(tmp_path/'box');b.reserve(r)
    b.record(r,sent(r))
    with pytest.raises(ValueError,match='OUTBOX_TRANSITION_FORBIDDEN'):
        b.record(r,{'status':'TRANSPORT_BLOCKED','reason':'stale reader'})
    assert b.read(r)['status']=='MESSAGE_SENT_VERIFIED'


def test_stale_writer_cannot_replace_newer_evidence(tmp_path):
    r=make_exchange_request(context(),'report',lane='HOST_COORDINATION');b=ExchangeOutbox(tmp_path/'box');b.reserve(r)
    snapshot=b.read(r);b.record(r,sent(r))
    with pytest.raises(ValueError,match='OUTBOX_CAS_CONFLICT'):
        b.record(r,{'status':'TRANSPORT_BLOCKED'},expected_status=snapshot['status'])


def test_concurrent_stale_writers_have_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    r=make_exchange_request(context(),'report',lane='HOST_COORDINATION');b=ExchangeOutbox(tmp_path/'box');b.reserve(r)
    barrier=Barrier(2)
    def writer(index):
        payload=sent(r);payload['user_turn_ref']=f'fixture-{index}'
        barrier.wait()
        try:
            b.record(r,payload,expected_status='EXCHANGE_REQUESTED')
            return 'won'
        except ValueError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(writer,range(2)))
    assert sorted(outcomes)==['OUTBOX_CAS_CONFLICT','won']
    assert b.read(r)['status']=='MESSAGE_SENT_VERIFIED'


def test_blocked_recovery_requires_exact_reconciliation(tmp_path):
    r=make_exchange_request(context(),'report',lane='HOST_COORDINATION');b=ExchangeOutbox(tmp_path/'box');b.reserve(r)
    b.record(r,{'status':'TRANSPORT_BLOCKED'})
    with pytest.raises(ValueError,match='OUTBOX_RECOVERY_RECONCILIATION_REQUIRED'):
        b.record(r,sent(r))
