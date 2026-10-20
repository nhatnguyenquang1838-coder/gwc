"""Host-owned browser capability outbox. Never polls typed C/E or settles Loop.

A durable reservation precedes any browser effect. Ambiguous sends stay locked;
restarting the runner is not permission to resend. The trusted host performs
actual UI observation through its installed skill; this module does no browser I/O.
"""
from __future__ import annotations
import datetime
import json
import sqlite3
from pathlib import Path
from .task_context_binding import validate_task_context, digest, require
from .exchange_deadlock import detect_exchange_stall, DEFAULT_THRESHOLD

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


def reconcile_controller_response(request, exchange_state):
    """Validate a response receipt against its exact outbox request identity.

    Rendered-text correlation is retained as advisory evidence only. This
    helper never emits typed NEXT, grants authority or permits graph resume.
    M7 and M8 share this validator so neither path can accept a response using
    only a boolean `response_complete_observed` flag.
    """
    require(isinstance(exchange_state,dict),'CONTROLLER_RESPONSE_STATE_INVALID')
    status=exchange_state.get('status');receipt=exchange_state.get('receipt')
    require(status in {'CONTROLLER_ACTION_REQUIRED','CONTROLLER_RESPONSE_VERIFIED'} and
            isinstance(receipt,dict),'CONTROLLER_RESPONSE_NOT_COMPLETE')
    require(receipt.get('status')==status,'CONTROLLER_RESPONSE_STATUS_MISMATCH')
    for key in ['request_digest','conversation_url','marker','task_id','run_id','session_id']:
        require(receipt.get(key)==request.get(key),'CONTROLLER_RESPONSE_IDENTITY_MISMATCH')
    require(receipt.get('response_to_marker')==request.get('marker') and
            isinstance(receipt.get('response_text'),str) and bool(receipt['response_text'].strip()) and
            isinstance(receipt.get('user_turn_ref'),str) and bool(receipt['user_turn_ref']) and
            isinstance(receipt.get('assistant_turn_ref'),str) and bool(receipt['assistant_turn_ref']) and
            receipt.get('response_complete_observed') is True and
            receipt.get('evidence_class')=='BROWSER_EXCHANGE_VERIFIED',
            'CONTROLLER_RESPONSE_CORRELATION_INCOMPLETE')
    require(receipt.get('authority_granted') is False and receipt.get('typed_ce_admitted') is False and
            receipt.get('workflow_resume_allowed') is False,'CONTROLLER_RESPONSE_AUTHORITY_WIDENING')
    if status=='CONTROLLER_ACTION_REQUIRED':
        require(receipt.get('receipt_strength')=='RENDERED_TEXT_CORRELATION_ONLY' and
                receipt.get('strong_receipt_verified') is False,
                'CONTROLLER_RESPONSE_WEAK_RECEIPT_INVALID')
        classification='RENDERED_TEXT_CORRELATED_WEAK'
    else:
        require(receipt.get('strong_receipt_verified') is True,
                'CONTROLLER_RESPONSE_STRONG_RECEIPT_REQUIRED')
        classification='STRONG_CONTROLLER_RESPONSE_VERIFIED'
    return {'classification':classification,'request_digest':request['request_digest'],
            'response_to_marker':request['marker'],'response_sha256':digest(receipt['response_text']),
            'receipt_strength':receipt.get('receipt_strength'),
            'user_turn_ref':receipt['user_turn_ref'],'assistant_turn_ref':receipt['assistant_turn_ref'],
            'evidence_class':'HUMAN_COORDINATION_OBSERVATION_NOT_TYPED_NEXT',
            'authority_granted':False,'typed_ce_admitted':False,
            'workflow_resume_allowed':False}


def reconcile_exchange_request_context(request, old_context, new_context, outbox, *, reason,
                                       repository_root=None, route_ref=None):
    """Rebind a reserved exchange request after a worktree-only context move.

    The request payload, ``request_digest`` and ``marker`` stay immutable — only
    a separate reconciliation row records that the same reservation now belongs
    to the relocated context. Allowed deltas: ``repository.worktree``, an
    ancestor-only head advance, and an additive route-metadata change proven
    against ``route_ref`` at both heads. Anything else fails closed.
    """
    import copy,subprocess
    old=validate_task_context(old_context);new=validate_task_context(new_context)
    require(isinstance(reason,str) and bool(reason.strip()),'EXCHANGE_CONTEXT_REBIND_REASON_REQUIRED')
    require(request.get('task_context_digest')==digest(old),'EXCHANGE_CONTEXT_REBIND_PRIOR_MISMATCH')
    old_wt=str(old['repository']['worktree']);new_wt=str(new['repository']['worktree'])
    require(old_wt!=new_wt,'EXCHANGE_CONTEXT_REBIND_UNCHANGED_WORKTREE')
    old_route=(old.get('engineering') or {}).get('route_policy_digest')
    new_route=(new.get('engineering') or {}).get('route_policy_digest')
    equivalent=copy.deepcopy(new)
    equivalent['repository']['worktree']=old_wt
    equivalent['repository']['head_sha']=old['repository']['head_sha']
    if old.get('engineering') is not None and new.get('engineering') is not None:
        equivalent['engineering']['route_policy_digest']=old_route
    require(equivalent==old,'EXCHANGE_CONTEXT_REBIND_DRIFT')
    if old_route!=new_route:
        require(repository_root is not None and route_ref,'EXCHANGE_CONTEXT_REBIND_ROUTE_EVIDENCE_REQUIRED')
        root=Path(repository_root).resolve()
        def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
        def route_at(sha):return json.loads(git('show',sha+':'+route_ref))
        old_r=route_at(old['repository']['head_sha']);new_r=route_at(new['repository']['head_sha'])
        require(old_r.get('work_items')==new_r.get('work_items'),'EXCHANGE_CONTEXT_REBIND_WORK_ITEMS_CHANGED')
        for key in ('workflow_mode','runtime_epoch','communication_issue','intent_ref','intent_body_sha256'):
            require(old_r.get(key)==new_r.get(key),'EXCHANGE_CONTEXT_REBIND_POLICY_KEY_CHANGED')
        for key,value in old_r.items():
            if key=='work_items':continue
            require(key in new_r and new_r[key]==value,'EXCHANGE_CONTEXT_REBIND_ROUTE_NOT_ADDITIVE')
    receipt={'request_digest':request['request_digest'],'marker':request['marker'],
             'old_context_digest':digest(old),'new_context_digest':digest(new),
             'reason':reason,'context_rebound':True,
             'old_worktree':old_wt,'new_worktree':new_wt,
             'route_metadata_additive':old_route!=new_route,
             'single_writer':True,'authority_granted':False,'typed_ce_admitted':False}
    require(outbox.read(request)['request']==request,'EXCHANGE_REQUEST_DRIFT')
    with outbox._db() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS exchange_context_reconciliations '
                   '(key TEXT PRIMARY KEY, request_digest TEXT, old_context_digest TEXT, '
                   'new_context_digest TEXT, receipt TEXT)')
        db.execute('INSERT INTO exchange_context_reconciliations VALUES (?,?,?,?,?)',
                   (digest(receipt),request['request_digest'],digest(old),digest(new),json.dumps(receipt,sort_keys=True)))
        db.commit()
    require(outbox.context_rebound(request,digest(new)),'EXCHANGE_CONTEXT_REBIND_READBACK_FAILED')
    return receipt


class ExchangeOutbox:
    def __init__(self, path):
        self.path = Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS exchange (key TEXT PRIMARY KEY, request TEXT NOT NULL, status TEXT NOT NULL, receipt TEXT)')

    def context_rebound(self, request, new_context_digest):
        """True only when a recorded reconciliation maps this request to the context."""
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS exchange_context_reconciliations '
                       '(key TEXT PRIMARY KEY, request_digest TEXT, old_context_digest TEXT, '
                       'new_context_digest TEXT, receipt TEXT)')
            row=db.execute('SELECT 1 FROM exchange_context_reconciliations WHERE request_digest=? AND new_context_digest=?',
                           (request['request_digest'],new_context_digest)).fetchone()
        return row is not None

    def _db(self):
        return sqlite3.connect(str(self.path), timeout=10)

    def note_attempt(self, request, status=None):
        """Record one host attempt for this request (append-only, no authority)."""
        prior = self.read(request)
        status = status or prior['status']
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS exchange_attempts '
                       '(id INTEGER PRIMARY KEY, key TEXT NOT NULL, marker TEXT NOT NULL, '
                       'status TEXT NOT NULL, context_digest TEXT, at TEXT NOT NULL)')
            db.execute('INSERT INTO exchange_attempts(key,marker,status,context_digest,at) VALUES (?,?,?,?,?)',
                       (request['request_digest'], request['marker'], status,
                        request.get('task_context_digest',''),
                        datetime.datetime.now(datetime.timezone.utc).isoformat()))
        return status

    def stall(self, request, *, threshold=DEFAULT_THRESHOLD):
        """Classify repeated identical unresolved attempts for the same request."""
        with self._db() as db:
            try:
                rows = db.execute('SELECT key,marker,status FROM exchange_attempts '
                                  'WHERE key=? ORDER BY id DESC LIMIT 12',
                                  (request['request_digest'],)).fetchall()
            except sqlite3.Error:
                rows = []
        return detect_exchange_stall(
            [{'request_digest':k,'marker':m,'status':s} for k,m,s in rows], threshold=threshold)

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

    def record(self, request, receipt, *, expected_status=None, expected_receipt_digest=None, reconciliation=None):
        prior = self.read(request)
        expected_status = prior['status'] if expected_status is None else expected_status
        expected_receipt_digest = digest(prior['receipt']) if expected_receipt_digest is None else expected_receipt_digest
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
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT status,receipt FROM exchange WHERE key=?',(request['request_digest'],)).fetchone()
            require(current is not None,'EXCHANGE_NOT_RESERVED')
            old_status, old_json = current
            old_receipt = json.loads(old_json) if old_json else None
            require(old_status == expected_status and digest(old_receipt) == expected_receipt_digest,'OUTBOX_CAS_CONFLICT')
            if old_receipt == receipt:
                return
            if old_status == 'CONTROLLER_RESPONSE_VERIFIED':
                raise ValueError('EXCHANGE_TERMINAL_RECEIPT_IMMUTABLE')
            if old_status == 'TRANSPORT_BLOCKED':
                require(isinstance(reconciliation,dict) and
                        reconciliation.get('request_digest') == request['request_digest'] and
                        reconciliation.get('conversation_url') == request['conversation_url'] and
                        reconciliation.get('marker') == request['marker'] and
                        reconciliation.get('session_id') == request['session_id'] and
                        reconciliation.get('prior_receipt_digest') == digest(old_receipt) and
                        reconciliation.get('outcome') == 'EXACT_RECONCILIATION_VERIFIED' and
                        bool(reconciliation.get('evidence_ref')), 'OUTBOX_RECOVERY_RECONCILIATION_REQUIRED')
                allowed = {'MESSAGE_SENT_VERIFIED','CONTROLLER_ACTION_REQUIRED'}
            else:
                allowed = {
                    'EXCHANGE_REQUESTED':{'MESSAGE_SENT_VERIFIED','TRANSPORT_BLOCKED'},
                    'MESSAGE_SENT_VERIFIED':{'CONTROLLER_RESPONSE_VERIFIED','CONTROLLER_ACTION_REQUIRED'},
                    'CONTROLLER_ACTION_REQUIRED':{'CONTROLLER_RESPONSE_VERIFIED'},
                }.get(old_status,set())
            require(receipt['status'] in allowed,'OUTBOX_TRANSITION_FORBIDDEN')
            db.execute('CREATE TABLE IF NOT EXISTS exchange_history (id INTEGER PRIMARY KEY, key TEXT, old_status TEXT, new_status TEXT, receipt TEXT, reconciliation TEXT)')
            cur = db.execute('UPDATE exchange SET status=?,receipt=? WHERE key=? AND status=? AND receipt IS ?',
                       (receipt['status'],json.dumps(receipt,sort_keys=True),request['request_digest'],old_status,old_json))
            require(cur.rowcount == 1,'OUTBOX_CAS_CONFLICT')
            db.execute('INSERT INTO exchange_history(key,old_status,new_status,receipt,reconciliation) VALUES (?,?,?,?,?)',
                       (request['request_digest'],old_status,receipt['status'],json.dumps(receipt,sort_keys=True),json.dumps(reconciliation)))


def resume_host_exchange(context, request, outbox, capabilities, *, phase='response',
                         inventory=None, dispatch_failure=None, idle_confirmed=False,
                         composer_empty_confirmed=False):
    """Resume an existing exchange: type only a proven uninvoked stage, or read a pending response."""
    c = validate_task_context(context)
    require(request['task_context_digest'] == digest(c), 'EXCHANGE_CONTEXT_DRIFT')
    prior = outbox.read(request)
    if phase == 'stage':
        require(prior['status']=='EXCHANGE_REQUESTED' and prior['receipt'] is None,
                'HOST_SEND_STATE_BLOCKED')
        resume = capabilities.get('controller_exchange.resume_stage')
        require(callable(resume),'HOST_SKILL_STAGE_RESUME_UNAVAILABLE')
        return resume(request,inventory,dispatch_failure=dispatch_failure,
                      idle_confirmed=idle_confirmed,composer_empty_confirmed=composer_empty_confirmed)
    require(phase=='response','HOST_RESUME_PHASE_INVALID')
    if prior['status'] == 'CONTROLLER_RESPONSE_VERIFIED':
        return prior
    reader = capabilities.get('controller_exchange.read') or capabilities.get(c['capabilities']['controller_exchange']['skill_ref']+'.read')
    require(callable(reader),'HOST_SKILL_READ_CAPABILITY_UNAVAILABLE')
    receipt = reader(request)
    if receipt.get('status') == 'HOST_ACTION_REQUIRED':
        return receipt
    outbox.record(request,receipt,expected_status=prior['status'],expected_receipt_digest=digest(prior['receipt']))
    return outbox.read(request)


def execute_host_exchange(context, request, outbox, capabilities):
    """Route to a host-injected installed-skill capability, not a guessed tool.

    send_read_verify must return actual same-page UI evidence. Successful function
    return alone is insufficient; record() enforces exact task/run/marker readback.
    """
    c = validate_task_context(context)
    require(request['task_context_digest'] == digest(c),'EXCHANGE_CONTEXT_DRIFT')
    skill = c['capabilities']['controller_exchange']['skill_ref']
    provider = capabilities.get('controller_exchange.send_read_verify') or capabilities.get(skill)
    require(callable(provider), 'HOST_SKILL_CAPABILITY_UNAVAILABLE')
    # Exchange-mode deadlock guard: the same request left unresolved for
    # `threshold` consecutive attempts must not be re-sent. One escalation per
    # stall_key; the host reports it instead of waking the Controller again.
    exchange_stall = outbox.stall(request) if outbox.read(request)['status'] in {
        'EXCHANGE_REQUESTED','MESSAGE_SENT_VERIFIED','CONTROLLER_ACTION_REQUIRED'} else None
    if exchange_stall and exchange_stall.get('stalled'):
        outbox.note_attempt(request)
        return {'status':'EXCHANGE_STALL_SUPPRESSED','reason_code':'EXCHANGE_STALL_ESCALATION_REQUIRED',
                'stall':exchange_stall,'prior':outbox.read(request),
                'typed_ce_admitted':False,'authority_granted':False}
    outbox.note_attempt(request)
    if not outbox.reserve(request):
        return {'status':'DUPLICATE_SEND_DETECTED','prior':outbox.read(request),'typed_ce_admitted':False}
    try:
        receipt = provider(request)
        if receipt.get('status') == 'HOST_ACTION_REQUIRED':
            return receipt
        outbox.record(request,receipt,expected_status='EXCHANGE_REQUESTED',expected_receipt_digest=digest(None))
    except Exception:
        current = outbox.read(request)
        if current['status'] == 'EXCHANGE_REQUESTED':
            outbox.record(request,{'status':'TRANSPORT_BLOCKED','reason':'HOST_CALL_UNVERIFIED','typed_ce_admitted':False},
                          expected_status='EXCHANGE_REQUESTED', expected_receipt_digest=digest(current['receipt']))
        raise
    return outbox.read(request)
