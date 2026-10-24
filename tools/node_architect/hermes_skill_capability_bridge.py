"""Hermes agent-owned skill bridge. No core edits and no alternate browser I/O.

Desktop preview read is an agent callback (tools/preview_tool.py), not a callable
shell API. This bridge returns exact deferred-tool actions to the CURRENT Hermes
agent. The agent executes them, returns the actual result to this bridge, and the
bridge verifies/persists the receipt. Tool actions are not receipt evidence.
"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from .task_context_binding import validate_task_context,digest,require


class HermesSkillBridge:
    def __init__(self,context,outbox,metadata):
        self.context=context;self.outbox=outbox;self.metadata=metadata

    def _bound(self,request):
        current=digest(self.context)
        require(request['task_context_digest']==current or
                self.outbox.context_rebound(request,current),'EXCHANGE_CONTEXT_DRIFT')
        require(request['session_id']==self.context['executor']['session_id'],'HOST_SESSION_MISMATCH')
        require(request['conversation_url']==self.context['controller']['conversation_url'],'HOST_URL_MISMATCH')
        require(self.outbox.read(request)['request']==request,'EXCHANGE_RESERVATION_BINDING_MISMATCH')
        require(hashlib.sha256(Path(self.metadata['skill_path']).read_bytes()).hexdigest()==self.metadata['skill_sha256'],'HOST_SKILL_SOURCE_DRIFT')

    def _claim_action(self,request,phase):
        with self.outbox._db() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT status FROM exchange WHERE key=?',(request['request_digest'],)).fetchone()
            require(current is not None and current[0]=='EXCHANGE_REQUESTED','HOST_SEND_STATE_BLOCKED')
            db.execute('CREATE TABLE IF NOT EXISTS host_actions (key TEXT, phase TEXT, PRIMARY KEY(key,phase))')
            if phase=='SEND':
                require(db.execute('SELECT 1 FROM host_actions WHERE key=? AND phase=?',(request['request_digest'],'STAGE')).fetchone() is not None,'HOST_STAGE_CLAIM_REQUIRED')
            cur=db.execute('INSERT OR IGNORE INTO host_actions VALUES (?,?)',(request['request_digest'],phase))
            require(cur.rowcount==1,'HOST_ACTION_ALREADY_CLAIMED')

    def read(self,request):
        self._bound(request)
        return {'status':'HOST_ACTION_REQUIRED','tool':'desktop_preview',
                'arguments':{'action':'read','start':0,'count':50000},
                'request_digest':request['request_digest'],'session_id':request['session_id'],
                'expected_url':request['conversation_url']}

    def send_read_verify(self,request):
        self._bound(request)
        state=self.outbox.read(request)
        require(state['status']=='EXCHANGE_REQUESTED','HOST_SEND_ALREADY_RESERVED_OR_DELIVERED')
        return self.read(request)

    def stage(self,request,inventory,*,composer_empty_confirmed=False,idle_confirmed=False):
        self._bound(request)
        require(self.outbox.read(request)['status']=='EXCHANGE_REQUESTED','HOST_SEND_STATE_BLOCKED')
        require(inventory.get('url')==request['conversation_url'],'HOST_URL_MISMATCH')
        require('elements' in inventory,'HOST_FRESH_INVENTORY_REQUIRED')
        require(idle_confirmed,'HOST_GPT_NOT_IDLE')
        boxes=[e for e in inventory['elements'] if e.get('role')=='textbox' and e.get('label')=='Ask ChatGPT']
        require(len(boxes)==1 and not boxes[0].get('disabled',False),'HOST_COMPOSER_UNAVAILABLE')
        if 'value' in boxes[0]:
            require(boxes[0]['value']=='','HOST_COMPOSER_NOT_EMPTY')
        else:
            require(composer_empty_confirmed,'HOST_COMPOSER_VALUE_UNKNOWN')
        self._claim_action(request,'STAGE')
        return {'status':'HOST_ACTION_REQUIRED','tool':'drive_preview',
                'arguments':{'action':'type','ref':boxes[0]['ref'],'text':request['marker']+'\n'+request['report'],'submit':False}}

    def resume_stage(self,request,inventory,*,dispatch_failure=None,idle_confirmed=False,
                     composer_empty_confirmed=False):
        """Resume a claimed but uninvoked type action after an explicit tool-schema rejection."""
        self._bound(request)
        state=self.outbox.read(request)
        require(state['status']=='EXCHANGE_REQUESTED' and state['receipt'] is None,'HOST_SEND_STATE_BLOCKED')
        require(isinstance(dispatch_failure,dict) and
                dispatch_failure.get('request_digest')==request['request_digest'] and
                dispatch_failure.get('tool')=='functions.tool_call' and
                dispatch_failure.get('action')=='type' and
                dispatch_failure.get('error_code')=='CALL_ITEM_NAME_REQUIRED' and
                dispatch_failure.get('browser_action_invoked') is False,
                'HOST_STAGE_RECOVERY_EVIDENCE_INVALID')
        require(inventory.get('url')==request['conversation_url'],'HOST_URL_MISMATCH')
        require('elements' in inventory,'HOST_FRESH_INVENTORY_REQUIRED')
        require(idle_confirmed,'HOST_GPT_NOT_IDLE')
        boxes=[e for e in inventory['elements'] if e.get('role')=='textbox' and e.get('label')=='Ask ChatGPT']
        require(len(boxes)==1 and not boxes[0].get('disabled',False),'HOST_COMPOSER_UNAVAILABLE')
        if 'value' in boxes[0]:
            require(boxes[0]['value']=='','HOST_COMPOSER_NOT_EMPTY')
        else:
            require(composer_empty_confirmed,'HOST_COMPOSER_VALUE_UNKNOWN')
        with self.outbox._db() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT status FROM exchange WHERE key=?',(request['request_digest'],)).fetchone()
            require(current is not None and current[0]=='EXCHANGE_REQUESTED','HOST_SEND_STATE_BLOCKED')
            require(db.execute('SELECT 1 FROM host_actions WHERE key=? AND phase=?',(request['request_digest'],'STAGE')).fetchone() is not None,'HOST_STAGE_CLAIM_REQUIRED')
            require(db.execute('SELECT 1 FROM host_actions WHERE key=? AND phase=?',(request['request_digest'],'SEND')).fetchone() is None,'HOST_SEND_ALREADY_CLAIMED')
            db.execute('CREATE TABLE IF NOT EXISTS host_actions (key TEXT, phase TEXT, PRIMARY KEY(key,phase))')
            cur=db.execute('INSERT OR IGNORE INTO host_actions VALUES (?,?)',(request['request_digest'],'TYPE_REPLAY'))
            require(cur.rowcount==1,'HOST_TYPE_REPLAY_ALREADY_CLAIMED')
        return {'status':'HOST_ACTION_REQUIRED','tool':'drive_preview',
                'arguments':{'action':'type','ref':boxes[0]['ref'],'text':request['marker']+'\n'+request['report'],'submit':False}}

    def send_action(self,request,type_result):
        self._bound(request)
        require(self.outbox.read(request)['status']=='EXCHANGE_REQUESTED','HOST_SEND_STATE_BLOCKED')
        require(type_result.get('url')==request['conversation_url'] and type_result.get('success') is True,'HOST_STAGE_UNVERIFIED')
        elements=type_result.get('delta',{}).get('added',[]) + type_result.get('elements',[])
        send=[e for e in elements if e.get('label')=='Send' and e.get('role')=='button' and not e.get('disabled',False)]
        require(len(send)==1,'HOST_FRESH_SEND_REQUIRED')
        self._claim_action(request,'SEND')
        return {'status':'HOST_ACTION_REQUIRED','tool':'drive_preview','arguments':{'action':'click','ref':send[0]['ref']}}

    def accept_readback(self,request,readback,*,response_complete=False):
        self._bound(request)
        require(readback.get('url')==request['conversation_url'],'HOST_URL_MISMATCH')
        text=readback.get('text','')
        # Only an actual user-turn boundary plus this unique request marker can
        # prove delivery; a composer value, cleared field or tool success cannot.
        user_turns=text.split('You said:')[1:]
        matches=[turn for turn in user_turns if turn.lstrip().startswith(request['marker'])]
        require(len(matches)==1,'HOST_USER_TURN_NOT_VERIFIED')
        turn=matches[0]
        base={k:request[k] for k in ['conversation_url','request_digest','marker','task_id','run_id','session_id']}
        base.update(user_turn_ref='same-page-user-turn:'+request['marker'],evidence_class='BROWSER_EXCHANGE_VERIFIED',
                    authority_granted=False,typed_ce_admitted=False,skill_binding=self.metadata,
                    raw_readback_sha256=digest(readback))
        before=self.outbox.read(request)
        if before['status']=='EXCHANGE_REQUESTED':
            self.outbox.record(request,{**base,'status':'MESSAGE_SENT_VERIFIED'},expected_status=before['status'],expected_receipt_digest=digest(before['receipt']))
        if response_complete:
            require('ChatGPT said:' in turn,'HOST_RESPONSE_NOT_VERIFIED')
            response=turn.split('ChatGPT said:',1)[1].strip()
            require(response and request['task_id'] in response,'HOST_RESPONSE_CONTEXT_MISMATCH')
            before=self.outbox.read(request)
            if before['status']=='CONTROLLER_RESPONSE_VERIFIED':
                return before
            # Desktop preview currently exposes rendered text, not stable UI
            # turn identities. Preserve the correlation as observational data,
            # never upgrade that fallback into a strong terminal receipt or a
            # graph-resume permission. No invented UI-turn schema is accepted.
            self.outbox.record(request,{**base,'status':'CONTROLLER_ACTION_REQUIRED',
                'reason':'HOST_UI_TURN_IDENTITY_UNAVAILABLE',
                'receipt_strength':'RENDERED_TEXT_CORRELATION_ONLY',
                'response_complete_observed':True,
                'response_to_marker':request['marker'],'response_text':response,
                'assistant_turn_ref':'rendered-assistant-after:'+request['marker'],
                'strong_receipt_verified':False,'workflow_resume_allowed':False},
                expected_status=before['status'],expected_receipt_digest=digest(before['receipt']))
        return self.outbox.read(request)


def resolve_installed_hermes_skills(context,*,home,host_session_id,preview=None,outbox=None):
    c=validate_task_context(context)
    require(host_session_id==c['executor']['session_id'],'HOST_SESSION_MISMATCH')
    name=c['capabilities']['controller_exchange']['skill_ref']
    paths=[p for p in (Path(home)/'skills').rglob('SKILL.md') if p.parent.name==name]
    require(len(paths)<=1,'HOST_SKILL_INSTALLATION_AMBIGUOUS')
    if not paths:
        return {'capability_binding':{'status':'HOST_SKILL_NOT_INSTALLED','skill_ref':name,'typed_observer_registered':False}}
    return resolve_hermes_skills(c,skill_path=paths[0],host_session_id=host_session_id,preview=preview,outbox=outbox)


def resolve_hermes_skills(context,*,skill_path,host_session_id,preview,outbox):
    c=validate_task_context(context)
    require(host_session_id==c['executor']['session_id'],'HOST_SESSION_MISMATCH')
    p=Path(skill_path).resolve();source=p.read_text()
    name=re.search(r'^name:\s*[\"\']?([^\"\'\n]+)',source,re.M)
    if name is None:
        raise ValueError('HOST_SKILL_IDENTITY_MISMATCH')
    require(name.group(1).strip()==c['capabilities']['controller_exchange']['skill_ref'],'HOST_SKILL_IDENTITY_MISMATCH')
    metadata={'skill_ref':name.group(1).strip(),'skill_path':str(p),
              'skill_sha256':hashlib.sha256(source.encode()).hexdigest(),'session_id':host_session_id,
              'dispatch_owner':'current_hermes_agent','evidence_class':'BROWSER_CAPABILITY_ONLY',
              'typed_observer_registered':False,'controller_url':c['controller']['conversation_url']}
    if preview is None:
        return {'capability_binding':{**metadata,'status':'HOST_PREVIEW_CALLBACK_REQUIRED'}}
    require(preview.get('url')==c['controller']['conversation_url'],'HOST_URL_MISMATCH')
    metadata.update(status='HOST_BROWSER_BOUND',preview_readback_digest=digest(preview))
    bridge=HermesSkillBridge(c,outbox,metadata)
    return {'bridge':bridge,'capability_binding':metadata,
            'controller_exchange.send_read_verify':bridge.send_read_verify,
            'controller_exchange.read':bridge.read,
            'controller_exchange.resume_stage':bridge.resume_stage,
            name.group(1).strip():bridge.send_read_verify,
            name.group(1).strip()+'.read':bridge.read}
