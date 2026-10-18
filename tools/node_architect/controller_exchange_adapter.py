"""Host-owned browser capability outbox. Never polls typed C/E or settles Loop.

A durable reservation precedes any browser effect. Ambiguous sends stay locked;
restarting the runner is not permission to resend. The trusted host performs
actual UI observation through its installed skill; this module does no browser I/O.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from .task_context_binding import validate_task_context, digest, require

OUTCOMES = {'MESSAGE_SENT_VERIFIED','CONTROLLER_RESPONSE_VERIFIED','TRANSPORT_BLOCKED',
            'DUPLICATE_SEND_DETECTED','CONTROLLER_ACTION_REQUIRED'}
EXCHANGE_REQUEST_SCHEMA = {
    'type':'object', 'additionalProperties':False,
    'required':['schema_version','request_type','task_id','run_id','session_id','task_context_digest',
                'conversation_url','capability','lane','report','authority_granted','typed_ce_admitted','request_digest','marker'],
    'properties':{
        **{key:{'type':'string','minLength':1} for key in
           ['task_id','run_id','session_id','task_context_digest','conversation_url','report','request_digest','marker']},
        'schema_version':{'const':1}, 'request_type':{'const':'CONTROLLER_EXCHANGE_REQUEST'},
        'capability':{'type':'object'}, 'lane':{'enum':['M7','HOST_COORDINATION']},
        'authority_granted':{'const':False}, 'typed_ce_admitted':{'const':False},
    },
}


def make_exchange_request(context, report, *, lane):
    c = validate_task_context(context)
    require(isinstance(report,str) and bool(report.strip()), 'EXCHANGE_REPORT_REQUIRED')
    require(lane in {'M7','HOST_COORDINATION'}, 'EXCHANGE_LANE_INVALID')
    body = {'schema_version':1,'request_type':'CONTROLLER_EXCHANGE_REQUEST',
            'task_id':c['task']['id'],'run_id':c['run']['id'],
            'session_id':c['executor']['session_id'], 'task_context_digest':digest(c),
            'conversation_url':c['controller']['conversation_url'],
            'capability':c['capabilities']['controller_exchange'], 'lane':lane,
            'report':report,'authority_granted':False,'typed_ce_admitted':False}
    body['request_digest'] = digest(body)
    body['marker'] = 'DWA-REVIEW-'+body['request_digest'][7:23]
    return body


class ExchangeOutbox:
    def __init__(self, path):
        self.path = Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS exchange (key TEXT PRIMARY KEY, request TEXT NOT NULL, status TEXT NOT NULL, receipt TEXT)')

    def _db(self):
        return sqlite3.connect(str(self.path), timeout=10)

    def reserve(self, request):
        from jsonschema import Draft202012Validator
        require(Draft202012Validator(EXCHANGE_REQUEST_SCHEMA).is_valid(request),'EXCHANGE_REQUEST_SCHEMA_INVALID')
        require(request.get('request_type') == 'CONTROLLER_EXCHANGE_REQUEST'
                and request.get('authority_granted') is False and request.get('typed_ce_admitted') is False,
                'EXCHANGE_REQUEST_INVALID')
        require(request.get('request_digest') == digest({k:v for k,v in request.items() if k not in {'request_digest','marker'}})
                and request.get('marker') == 'DWA-REVIEW-'+request['request_digest'][7:23], 'EXCHANGE_REQUEST_DIGEST_INVALID')
        with self._db() as db:
            cur = db.execute('INSERT OR IGNORE INTO exchange VALUES (?,?,?,NULL)',
                (request['request_digest'],json.dumps(request,sort_keys=True),'EXCHANGE_REQUESTED'))
            return cur.rowcount == 1

    def read(self, request):
        with self._db() as db:
            row = db.execute('SELECT request,status,receipt FROM exchange WHERE key=?',(request['request_digest'],)).fetchone()
        require(row is not None,'EXCHANGE_NOT_RESERVED')
        require(json.loads(row[0]) == request,'EXCHANGE_REQUEST_DRIFT')
        return {'request':json.loads(row[0]),'status':row[1], 'receipt':json.loads(row[2]) if row[2] else None}

    def record(self, request, receipt):
        prior = self.read(request)
        require(receipt.get('status') in OUTCOMES,'EXCHANGE_OUTCOME_INVALID')
        require(receipt.get('typed_ce_admitted',False) is False and receipt.get('authority_granted',False) is False,'BROWSER_NOT_AUTHORITY')
        if receipt['status'] in {'MESSAGE_SENT_VERIFIED','CONTROLLER_RESPONSE_VERIFIED'}:
            require(receipt.get('request_digest') == request['request_digest'] and
                    receipt.get('conversation_url') == request['conversation_url'] and
                    receipt.get('marker') == request['marker'] and
                    receipt.get('task_id') == request['task_id'] and
                    receipt.get('run_id') == request['run_id'], 'EXCHANGE_RECEIPT_BINDING_MISMATCH')
            require(isinstance(receipt.get('user_turn_ref'),str) and bool(receipt['user_turn_ref'])
                    and receipt.get('evidence_class') == 'BROWSER_EXCHANGE_VERIFIED','EXCHANGE_READBACK_REQUIRED')
        if receipt['status'] == 'CONTROLLER_RESPONSE_VERIFIED':
            require(receipt.get('response_to_marker') == request['marker'] and
                    isinstance(receipt.get('response_text'),str) and bool(receipt['response_text'].strip())
                    and isinstance(receipt.get('assistant_turn_ref'),str) and bool(receipt['assistant_turn_ref']), 'CONTROLLER_RESPONSE_READBACK_REQUIRED')
        if prior['status'] == 'CONTROLLER_RESPONSE_VERIFIED':
            require(prior['receipt'] == receipt, 'EXCHANGE_TERMINAL_RECEIPT_IMMUTABLE')
            return
        with self._db() as db:
            db.execute('UPDATE exchange SET status=?,receipt=? WHERE key=?',
                       (receipt['status'],json.dumps(receipt,sort_keys=True),request['request_digest']))


def resume_host_exchange(context, request, outbox, capabilities):
    """Read/verify a pending response without invoking send again."""
    c = validate_task_context(context)
    require(request['task_context_digest'] == digest(c), 'EXCHANGE_CONTEXT_DRIFT')
    prior = outbox.read(request)
    if prior['status'] == 'CONTROLLER_RESPONSE_VERIFIED':
        return prior
    reader = capabilities.get(c['capabilities']['controller_exchange']['skill_ref']+'.read')
    require(callable(reader),'HOST_SKILL_READ_CAPABILITY_UNAVAILABLE')
    outbox.record(request,reader(request))
    return outbox.read(request)


def execute_host_exchange(context, request, outbox, capabilities):
    """Route to a host-injected installed-skill capability, not a guessed tool.

    send_read_verify must return actual same-page UI evidence. Successful function
    return alone is insufficient; record() enforces exact task/run/marker readback.
    """
    c = validate_task_context(context)
    require(request['task_context_digest'] == digest(c),'EXCHANGE_CONTEXT_DRIFT')
    skill = c['capabilities']['controller_exchange']['skill_ref']
    provider = capabilities.get(skill)
    require(callable(provider), 'HOST_SKILL_CAPABILITY_UNAVAILABLE')
    if not outbox.reserve(request):
        return {'status':'DUPLICATE_SEND_DETECTED','prior':outbox.read(request),'typed_ce_admitted':False}
    try:
        receipt = provider(request)
        outbox.record(request,receipt)
    except Exception:
        outbox.record(request,{'status':'TRANSPORT_BLOCKED','reason':'HOST_CALL_UNVERIFIED','typed_ce_admitted':False})
        raise
    return outbox.read(request)
