"""Deterministic context-gap escalation evaluator for SCRUM-183."""
from __future__ import annotations
import hashlib, json, re
from typing import Any, Mapping

SCHEMA_VERSION="1.0"; ARTIFACT_TYPE="context-gap-decision"
SHA40=re.compile(r"^[0-9a-f]{40}$"); SHA256=re.compile(r"^(?:sha256:)?([0-9a-f]{64})$"); REPO=re.compile(r"^[^/\s]+/[^/\s]+$")
AUTH=("write_authority_granted","commit_authority_granted","push_authority_granted","pr_authority_granted","merge_authority_granted","deployment_authority_granted","production_authority_granted")
CONNECTOR={"CONFIRMED","EMPTY","ERROR","UNSUPPORTED"}; READBACK={"CONFIRMED","NOT_ATTEMPTED","ERROR","UNSUPPORTED"}; CI={"SUCCESS","FAILED","PENDING","EMPTY","ERROR","UNSUPPORTED","NOT_APPLICABLE"}; VALIDATOR={"PASS","FAILED","NOT_RUN",None}
REASONS={"CONTEXT_READY","CONTEXT_INPUT_INVALID","CONTEXT_CARD_INVALID","CONTEXT_REQUIRED_FIELD_MISSING","CONTEXT_SOURCE_UNRESOLVED","CONTEXT_SOURCE_CONFLICT","CONTEXT_REPO_IDENTITY_UNCONFIRMED","CONTEXT_BASE_STALE","CONTEXT_EVIDENCE_MISSING","CONTEXT_AGENT_PREPARATION_BLOCKED","CONTEXT_REPOSITORY_EVIDENCE_MISSING","CONTEXT_CI_UNAVAILABLE","CONTEXT_VALIDATION_FAILED","CONTEXT_SCOPE_DRIFT","CONTEXT_HUMAN_INPUT_REQUIRED","CONTEXT_REMEDIATION_TARGET_UNKNOWN"}
PRECEDENCE={"CONTEXT_INPUT_INVALID":10,"CONTEXT_CARD_INVALID":20,"CONTEXT_REQUIRED_FIELD_MISSING":25,"CONTEXT_BASE_STALE":30,"CONTEXT_SOURCE_CONFLICT":40,"CONTEXT_HUMAN_INPUT_REQUIRED":45,"CONTEXT_SOURCE_UNRESOLVED":50,"CONTEXT_AGENT_PREPARATION_BLOCKED":60,"CONTEXT_REPOSITORY_EVIDENCE_MISSING":70,"CONTEXT_SCOPE_DRIFT":80,"CONTEXT_CI_UNAVAILABLE":90,"CONTEXT_EVIDENCE_MISSING":100,"CONTEXT_VALIDATION_FAILED":110,"CONTEXT_REMEDIATION_TARGET_UNKNOWN":120,"CONTEXT_READY":999}

def _canon(v:Any)->Any:
    if isinstance(v,Mapping): return {str(k):_canon(v[k]) for k in sorted(v,key=str)}
    if isinstance(v,list):
        items=[_canon(x) for x in v]
        keyed={json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False):x for x in items}
        return [keyed[k] for k in sorted(keyed)]
    return v

def canonical_json(payload:Any)->str:
    return json.dumps(_canon(payload),sort_keys=True,separators=(",",":"),ensure_ascii=False)

def digest_payload(payload:Any)->str:
    return "sha256:"+hashlib.sha256(canonical_json(payload).encode()).hexdigest()

def _hex(v:Any)->str|None:
    if not isinstance(v,str): return None
    m=SHA256.fullmatch(v); return m.group(1) if m else None

def _valid_digest(v:Any)->bool: return _hex(v) is not None

def _bindings(card:Mapping[str,Any])->list[Mapping[str,Any]]:
    b=card.get("source_bindings",[]); return b if isinstance(b,list) else []

def _card_hash(card:Mapping[str,Any])->str:
    return digest_payload({k:v for k,v in card.items() if k not in {"created_at","snapshot_hash"}})

def _base_key(card:Mapping[str,Any])->str: return f"repository:{card.get('repository','')}@{card.get('base_sha','')}"

def _source_key(row:Mapping[str,Any])->str|None:
    s=row.get("source") or row.get("source_type"); b=row.get("binding") or row.get("ref"); r=row.get("revision")
    return f"source:{s}:{b}:{r}" if all(isinstance(x,str) and x for x in (s,b,r)) else None

def _artifact_key(row:Mapping[str,Any])->str|None:
    t=row.get("artifact_type"); d=row.get("digest")
    return f"artifact:{t}:{d}" if isinstance(t,str) and t and _valid_digest(d) else None

def collect_required_evidence(card:Mapping[str,Any])->list[str]:
    ev=set()
    if not isinstance(card,Mapping): return []
    ev.add(_base_key(card))
    for row in _bindings(card):
        if isinstance(row,Mapping) and (k:=_source_key(row)): ev.add(k)
    ups=card.get("upstream_artifacts",[])
    if isinstance(ups,list):
        for row in ups:
            if isinstance(row,Mapping) and (k:=_artifact_key(row)): ev.add(k)
    read=card.get("read_scope_projection",{})
    if isinstance(read,Mapping):
        for field in ("files_read","files_missing","include_paths","missing_required_files"):
            vals=read.get(field,[])
            if isinstance(vals,list): ev.update(f"path:{x}" for x in vals if isinstance(x,str) and x)
    return sorted(ev)

def validate_intake_card(card:Any, task_id:str, repository:str, base_sha:str)->list[str]:
    if not isinstance(card,Mapping): return ["CONTEXT_INPUT_INVALID"]
    req=("schema_version","artifact_type","task_id","repository","base_sha","source_bindings","repository_context","read_scope_projection","write_scope_projection","upstream_artifacts","context_status","outcome","snapshot_hash","reason_codes","read_only_projection")
    if any(k not in card for k in req): return ["CONTEXT_REQUIRED_FIELD_MISSING"]
    if card.get("artifact_type")!="intake-card" or card.get("schema_version")!="1.0": return ["CONTEXT_CARD_INVALID"]
    if card.get("task_id")!=task_id or card.get("repository")!=repository or card.get("base_sha")!=base_sha: return ["CONTEXT_CARD_INVALID"]
    if card.get("outcome") not in {"READY","BLOCKED"} or card.get("context_status") not in {"READY","BLOCKED"}: return ["CONTEXT_CARD_INVALID"]
    if not isinstance(card.get("reason_codes"),list): return ["CONTEXT_CARD_INVALID"]
    snap=card.get("snapshot_hash")
    if not _valid_digest(snap) or _hex(snap)!=_hex(_card_hash(card)): return ["CONTEXT_CARD_INVALID"]
    return []

def _input_issues(**kw:Any)->list[str]:
    if not isinstance(kw.get("task_id"),str) or not kw["task_id"]: return ["CONTEXT_INPUT_INVALID"]
    if not isinstance(kw.get("repository"),str) or not REPO.fullmatch(kw["repository"]): return ["CONTEXT_INPUT_INVALID"]
    for k in ("base_sha","current_base_sha"):
        if not isinstance(kw.get(k),str) or not SHA40.fullmatch(kw[k]): return ["CONTEXT_INPUT_INVALID"]
    if not isinstance(kw.get("available_evidence_keys"),list) or not all(isinstance(x,str) and x for x in kw["available_evidence_keys"]): return ["CONTEXT_INPUT_INVALID"]
    if not isinstance(kw.get("confirmed_missing_evidence_keys"),list) or not all(isinstance(x,str) and x for x in kw["confirmed_missing_evidence_keys"]): return ["CONTEXT_INPUT_INVALID"]
    if kw.get("connector_status") not in CONNECTOR or kw.get("repository_readback_status") not in READBACK or kw.get("ci_status") not in CI or kw.get("validator_status") not in VALIDATOR: return ["CONTEXT_INPUT_INVALID"]
    if not isinstance(kw.get("ci_required"),bool): return ["CONTEXT_INPUT_INVALID"]
    return []

def _known_key_issues(card:Mapping[str,Any], available:list[str], missing:list[str])->list[str]:
    known=set(collect_required_evidence(card)); unknown=(set(available)|set(missing))-known
    return ["CONTEXT_INPUT_INVALID"] if unknown else []

def _source_conflict(card:Mapping[str,Any])->bool:
    for row in _bindings(card):
        if isinstance(row,Mapping) and (str(row.get("status","")).upper() in {"AMBIGUOUS","CONFLICT"} or str(row.get("mode","")).upper() in {"AMBIGUOUS","CONFLICT"}): return True
    codes=set(card.get("reason_codes",[]) if isinstance(card.get("reason_codes"),list) else [])
    return bool({"CARD_SOURCE_CONFLICT","CONTEXT_SOURCE_CONFLICT","CONTEXT_HUMAN_INPUT_REQUIRED"}&codes)

def _source_unresolved(card:Mapping[str,Any])->bool:
    if any(isinstance(r,Mapping) and str(r.get("status","")).upper()=="MISSING" for r in _bindings(card)): return True
    codes=set(card.get("reason_codes",[]) if isinstance(card.get("reason_codes"),list) else [])
    return bool({"CARD_SOURCE_UNRESOLVED","CONTEXT_SOURCE_UNRESOLVED"}&codes)

def _scope_drift(card:Mapping[str,Any])->bool:
    codes=set(card.get("reason_codes",[]) if isinstance(card.get("reason_codes"),list) else [])
    return bool({"CARD_SCOPE_HASH_MISMATCH","CARD_UPSTREAM_DIGEST_MISMATCH","CARD_SNAPSHOT_HASH_MISMATCH","CONTEXT_SCOPE_DRIFT"}&codes)

def _missing_required(card:Mapping[str,Any], available:list[str])->list[str]:
    read=card.get("read_scope_projection",{})
    missing=[]
    if isinstance(read,Mapping):
        for item in read.get("files_missing",[]) or read.get("missing_required_files",[]):
            if isinstance(item,str) and item: missing.append(f"path:{item}")
    return sorted(set(missing)-set(available))

def _read_for_key(card:Mapping[str,Any], key:str, reason:str)->dict[str,str]|None:
    repo=str(card.get("repository","")); base=str(card.get("base_sha",""))
    if key.startswith("path:"):
        target=key[5:]; return {"evidence_key":key,"source_type":"REPOSITORY_FILE","target":target,"ref":base,"connector_route":f"GitHub.fetch_file:{target}@{base}","fallback_route":"manual exact repository readback","reason_code":reason,"stop_condition":"Exact repository evidence is materialized or absence is confirmed."}
    if key.startswith("repository:"):
        return {"evidence_key":key,"source_type":"PROTECTED_BASE_REF","target":repo,"ref":base,"connector_route":f"GitHub.compare_commits:{repo}@{base}","fallback_route":"manual protected-base readback","reason_code":reason,"stop_condition":"Protected base is recaptured and rebound."}
    if key.startswith("source:"):
        return {"evidence_key":key,"source_type":"SOURCE_BINDING","target":key,"connector_route":"source readback","fallback_route":"ask human for source authority","reason_code":reason,"stop_condition":"Source binding is verified or denied."}
    if key.startswith("artifact:"):
        return {"evidence_key":key,"source_type":"UPSTREAM_ARTIFACT","target":key,"connector_route":"upstream artifact readback","fallback_route":"rerender upstream artifact","reason_code":reason,"stop_condition":"Upstream digest is recomputed at exact binding."}
    if key.startswith("ci:"):
        return {"evidence_key":key,"source_type":"CI_RUN_LOOKUP","target":repo,"ref":base,"connector_route":f"GitHub.fetch_commit_workflow_runs:{base}","fallback_route":"manual CI run lookup","reason_code":reason,"stop_condition":"Exact CI is terminal or observability gap is recorded."}
    return None

def build_remediation_readset(card:Mapping[str,Any]|None, missing:list[str], route:str, reason:str)->dict[str,Any]:
    reads=[]
    if card is not None:
        for key in missing:
            r=_read_for_key(card,key,reason)
            if r: reads.append(r)
    if card is not None and route=="RETRY_CI_OBSERVABILITY":
        r=_read_for_key(card,f"ci:{card.get('repository','')}@{card.get('base_sha','')}",reason)
        if r: reads.append(r)
    uniq={json.dumps(r,sort_keys=True):r for r in reads}
    reads=sorted(uniq.values(),key=lambda r:(PRECEDENCE.get(r.get("reason_code",""),999),r.get("source_type",""),r.get("target",""),r.get("ref",""),r.get("revision","")))
    payload={"schema_version":"1.0","required_reads":reads,"connector_route":route if reads else "NONE","fallback_route":"manual readback" if reads else "NONE","stop_condition":"Required reads complete or exact blocker recorded." if reads else "No exact remediation target available."}
    payload["readset_hash"]=digest_payload(payload)
    return payload

def _decision_digest(decision:Mapping[str,Any])->str:
    return digest_payload({k:v for k,v in decision.items() if k not in {"observed_at","decision_digest"}})

def _make_decision(*, task_id:str, repository:str, base_sha:str, current_base_sha:str, card:Mapping[str,Any]|None, outcome:str, classification:str, owner:str, route:str, next_action:str, stop_condition:str, reason_code:str, reason_codes:list[str], missing_evidence:list[str], observed_at:str|None)->dict[str,Any]:
    codes=sorted(set(reason_codes),key=lambda c:(PRECEDENCE.get(c,999),c)); primary=reason_code if reason_code in codes else codes[0]
    if card is None: card_hash=""
    else: card_hash=str(card.get("snapshot_hash",""))
    readset=build_remediation_readset(card,missing_evidence,route,primary)
    block={"schema_version":"1.0","blocked":outcome=="BLOCKED","classification":classification,"blocker_type":classification,"severity":"BLOCKER" if outcome=="BLOCKED" else "INFO","missing_evidence":sorted(set(missing_evidence)),"source_bindings":list(_bindings(card or {})),"owner":owner,"route":route,"next_action":next_action,"stop_condition":stop_condition,"reason_code":primary,"reason_codes":codes}
    decision={"schema_version":"1.0","artifact_type":"context-gap-decision","task_id":task_id,"repository":repository,"base_sha":base_sha,"current_base_sha":current_base_sha,"intake_card_snapshot_hash":card_hash,"outcome":outcome,"preparation_block":block,"remediation_readset":readset,"reason_code":primary,"reason_codes":codes,"observed_at":"" if observed_at is None else str(observed_at),"read_only_projection":True,**{f:False for f in AUTH}}
    decision["decision_digest"]=_decision_digest(decision); return decision

def classify_context_gap(*, task_id:str, repository:str, base_sha:str, intake_card:Mapping[str,Any], current_base_sha:str, available_evidence_keys:list[str], confirmed_missing_evidence_keys:list[str], connector_status:str, repository_readback_status:str, ci_required:bool, ci_status:str, validator_status:str|None=None):
    if current_base_sha!=base_sha: return ("BLOCKED","AGENT_PREPARATION_BLOCKED","AGENT","RECAPTURE_PROTECTED_BASE","Recapture protected base and rerender the intake card.","Do not continue until current protected-base readback is rebound.",["CONTEXT_BASE_STALE"],[_base_key(intake_card)])
    if _source_conflict(intake_card): return ("BLOCKED","HUMAN_INPUT_REQUIRED","HUMAN_REQUESTER","REQUEST_HUMAN_INPUT","Ask the requester to select or clarify the source of authority.","Stop until human source authority is explicit.",["CONTEXT_SOURCE_CONFLICT","CONTEXT_HUMAN_INPUT_REQUIRED"],[])
    if _source_unresolved(intake_card): return ("BLOCKED","AGENT_PREPARATION_BLOCKED","AGENT","RETRY_SOURCE_READBACK","Retry deterministic source readback for the unresolved source binding.","Stop when source binding is verified, denied, or human input is required.",["CONTEXT_SOURCE_UNRESOLVED"],[k for k in collect_required_evidence(intake_card) if k.startswith("source:")])
    req_missing=_missing_required(intake_card,available_evidence_keys)
    if req_missing and connector_status in {"ERROR","UNSUPPORTED"}: return ("BLOCKED","AGENT_PREPARATION_BLOCKED","AGENT","RETRY_SOURCE_READBACK","Recover connector/materialization evidence before classifying repository failure.","Do not report repository failure until exact source readback is confirmed.",["CONTEXT_AGENT_PREPARATION_BLOCKED"],req_missing)
    confirmed=sorted(set(req_missing)&set(confirmed_missing_evidence_keys))
    if confirmed and repository_readback_status=="CONFIRMED": return ("BLOCKED","REPOSITORY_EVIDENCE_MISSING","REPOSITORY_OWNER","READ_REQUIRED_EVIDENCE","Read or restore the missing exact repository evidence.","Stop when the exact missing target is materialized or repository owner confirms absence.",["CONTEXT_REPOSITORY_EVIDENCE_MISSING"],confirmed)
    if _scope_drift(intake_card): return ("BLOCKED","AGENT_PREPARATION_BLOCKED","AGENT","RETRY_SOURCE_READBACK","Reread upstream artifact/source evidence and rerender the card.","Stop until digest drift is resolved against exact upstream bindings.",["CONTEXT_SCOPE_DRIFT"],[k for k in collect_required_evidence(intake_card) if k.startswith("artifact:")])
    if ci_required and ci_status in {"PENDING","EMPTY","ERROR","UNSUPPORTED"}: return ("BLOCKED","CI_UNAVAILABLE_AT_CHECK","CI_PROVIDER","RETRY_CI_OBSERVABILITY","Retry exact-sha CI observability.","Stop when exact CI is terminal or observability denial is recorded.",["CONTEXT_CI_UNAVAILABLE"],[])
    if validator_status=="FAILED" and req_missing: return ("BLOCKED","AGENT_PREPARATION_BLOCKED","AGENT","READ_REQUIRED_EVIDENCE","Materialize all required evidence before treating validator failure as real.","Stop until required evidence is available at exact bindings.",["CONTEXT_EVIDENCE_MISSING"],req_missing)
    if validator_status=="FAILED": return ("BLOCKED","VALIDATION_FAILED","VALIDATION_OWNER","FIX_VALIDATION_FAILURE","Fix the confirmed validation failure inside the governed scope.","Stop when validation passes or a new approval is required.",["CONTEXT_VALIDATION_FAILED"],[])
    if req_missing or intake_card.get("outcome")=="BLOCKED": return ("BLOCKED","AGENT_PREPARATION_BLOCKED","AGENT","READ_REQUIRED_EVIDENCE","Read the unresolved required evidence from the exact card read scope.","Stop until each required evidence key is materialized or exactly classified.",["CONTEXT_EVIDENCE_MISSING"],req_missing)
    return ("READY","NONE","NONE","READY_FOR_FAMILY_VERIFICATION","Continue to separately governed family verification.","No context gap is detected; this result grants no authority.",["CONTEXT_READY"],[])

def decide_context_gap_escalation(*, task_id:str, repository:str, base_sha:str, intake_card:dict[str,object], current_base_sha:str, available_evidence_keys:list[str], confirmed_missing_evidence_keys:list[str], connector_status:str, repository_readback_status:str, ci_required:bool, ci_status:str, validator_status:str|None=None, observed_at:str|None=None)->dict[str,object]:
    issues=_input_issues(task_id=task_id,repository=repository,base_sha=base_sha,current_base_sha=current_base_sha,available_evidence_keys=available_evidence_keys,confirmed_missing_evidence_keys=confirmed_missing_evidence_keys,connector_status=connector_status,repository_readback_status=repository_readback_status,ci_required=ci_required,ci_status=ci_status,validator_status=validator_status)
    if issues:
        safe_task=task_id if isinstance(task_id,str) and task_id else "UNKNOWN"; safe_repo=repository if isinstance(repository,str) and REPO.fullmatch(repository) else "invalid/invalid"; safe_base=base_sha if isinstance(base_sha,str) and SHA40.fullmatch(base_sha) else "0"*40; safe_current=current_base_sha if isinstance(current_base_sha,str) and SHA40.fullmatch(current_base_sha) else safe_base
        return _make_decision(task_id=safe_task,repository=safe_repo,base_sha=safe_base,current_base_sha=safe_current,card=None,outcome="BLOCKED",classification="AGENT_PREPARATION_BLOCKED",owner="AGENT",route="BLOCK_G1_REVIEW",next_action="Repair malformed context-gap evaluator inputs.",stop_condition="Stop until inputs conform to the runtime interface.",reason_code="CONTEXT_INPUT_INVALID",reason_codes=issues,missing_evidence=[],observed_at=observed_at)
    card_issues=validate_intake_card(intake_card,task_id,repository,base_sha) or _known_key_issues(intake_card,available_evidence_keys,confirmed_missing_evidence_keys)
    if card_issues:
        primary="CONTEXT_INPUT_INVALID" if "CONTEXT_INPUT_INVALID" in card_issues else card_issues[0]
        return _make_decision(task_id=task_id,repository=repository,base_sha=base_sha,current_base_sha=current_base_sha,card=intake_card if isinstance(intake_card,Mapping) else None,outcome="BLOCKED",classification="AGENT_PREPARATION_BLOCKED",owner="AGENT",route="BLOCK_G1_REVIEW",next_action="Repair malformed card, hash, binding, or evidence-key input before review.",stop_condition="Stop until a valid intake card and known evidence keys are provided.",reason_code=primary,reason_codes=card_issues,missing_evidence=[],observed_at=observed_at)
    outcome,classification,owner,route,action,stop,codes,missing=classify_context_gap(task_id=task_id,repository=repository,base_sha=base_sha,intake_card=intake_card,current_base_sha=current_base_sha,available_evidence_keys=available_evidence_keys,confirmed_missing_evidence_keys=confirmed_missing_evidence_keys,connector_status=connector_status,repository_readback_status=repository_readback_status,ci_required=ci_required,ci_status=ci_status,validator_status=validator_status)
    return _make_decision(task_id=task_id,repository=repository,base_sha=base_sha,current_base_sha=current_base_sha,card=intake_card,outcome=outcome,classification=classification,owner=owner,route=route,next_action=action,stop_condition=stop,reason_code=codes[0],reason_codes=codes,missing_evidence=missing,observed_at=observed_at)
