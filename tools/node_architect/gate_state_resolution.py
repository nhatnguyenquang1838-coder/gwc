"""Deterministic, replay-safe GWC gate-state resolution."""
from __future__ import annotations
import hashlib,json,re
from collections.abc import Mapping,Sequence
from typing import Any
from tools.node_architect.evidence_artifact_map import _GATE_REQUIREMENTS
from tools.node_architect.scope_hash_calculation import BINDING_KEYS,CANONICAL_ACTIONS,calculate_gate_scope_identity

GATE_ORDER=("G0_CONTEXT","G1_ALIGNMENT","G2_EXECUTION","G3_PR","G4_MERGE","G5_DEPLOY","G6_PRODUCTION_DATA")
FLAGS="authority_granted write_authority_granted pr_authority_granted merge_authority_granted deployment_authority_granted production_authority_granted".split()
CLASSES={"CANONICAL_AUTHORITY","CANONICAL_GATE_EVIDENCE","DELIVERY_EVIDENCE"}
READ_ONLY=set("read_repository inspect_connector inspect_task materialize_g1_artifacts run_read_only_validation run_independent_review verify_post_merge_ci readback_branch_pr_diff_ci".split())
PRODUCTION=set("production_data_read production_data_write production_config_change credential_rotation migration".split())
EB=set("EVIDENCE_INPUT_INVALID EVIDENCE_BINDING_MISMATCH EVIDENCE_CONFLICT EVIDENCE_PROJECTION_ONLY EVIDENCE_STALE EVIDENCE_REQUIRED_MISSING EVIDENCE_OBSERVABILITY_INCOMPLETE EVIDENCE_CI_BINDING_MISMATCH".split())
ER=EB|{"EVIDENCE_MAP_READY","EVIDENCE_G6_NOT_APPLICABLE"}
ORDER="GATE_STATE_INPUT_INVALID GATE_STATE_REPLAY_CONFLICT GATE_STATE_BINDING_MISMATCH GATE_STATE_EVIDENCE_CONFLICT GATE_STATE_GATE_FAILED GATE_STATE_DRIFT GATE_STATE_EVIDENCE_STALE GATE_STATE_REQUIRED_EVIDENCE_MISSING GATE_STATE_LATER_GATE_INHERITANCE_REJECTED GATE_STATE_RESOLVED GATE_STATE_PROJECTION_MISMATCH GATE_STATE_G6_NOT_APPLICABLE".split()
TD="3246896730efb267cd61e377ae9a1ab8365733ab4ddd532b80fd1ce2d82be62f"
SHA=re.compile(r"^[0-9a-f]{40}$"); DIG=re.compile(r"^sha256:[0-9a-f]{64}$"); REPO=re.compile(r"^[^/\s]+/[^/\s]+$")
OBS=set("observed_at mapped_at calculated_at generated_at updated_at created_at decision_digest resolution_digest map_digest".split())
SF=set("schema_version artifact_type task_id repository base_ref base_sha working_branch head_sha risk_class authorized_paths authorized_actions excluded_actions additional_bindings outcome reason_codes calculated_at scope_hash approval_request_digest authority_granted".split())
MF=set("schema_version artifact_type task_id repository base_sha head_sha policy_revision mapped_at outcome reason_codes entries requirements missing_required stale_required projection_only map_digest authority_granted".split())
EF=set("evidence_key gate artifact_role artifact_type classification required source_type target ref revision digest binding_status freshness_status materialization_status source_of_truth reason_codes".split())
ERQ=set("evidence_key gate artifact_role artifact_type classification required source_type target binding_status freshness_status materialization_status source_of_truth reason_codes".split())

def _cj(x): return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def _dg(x): return "sha256:"+hashlib.sha256(_cj(x).encode()).hexdigest()
def _strip(x):
    if isinstance(x,Mapping): return {str(k):_strip(v) for k,v in x.items() if str(k) not in OBS}
    if isinstance(x,list): return [_strip(v) for v in x]
    return x
def _sl(x,nonempty=False): return isinstance(x,list) and (not nonempty or bool(x)) and len(x)==len(set(x)) and all(isinstance(v,str) and v for v in x)
def _ss(x): return sorted({v for v in x if isinstance(v,str) and v}) if isinstance(x,list) else []
def _sr(x): return sorted(set(x),key=lambda v:(ORDER.index(v) if v in ORDER else 99,v))

def _scope(s):
    req=set("schema_version artifact_type task_id repository base_ref base_sha risk_class authorized_paths authorized_actions excluded_actions outcome scope_hash authority_granted".split())
    if not isinstance(s,Mapping) or set(s)-SF or not req<=set(s): return False
    if s.get("schema_version")!="1.0" or s.get("artifact_type")!="gate-scope-identity" or s.get("outcome")!="READY" or s.get("authority_granted") is not False:return False
    if not isinstance(s.get("task_id"),str) or not s["task_id"] or not isinstance(s.get("repository"),str) or not REPO.match(s["repository"]):return False
    if not isinstance(s.get("base_ref"),str) or not s["base_ref"] or not isinstance(s.get("base_sha"),str) or not SHA.match(s["base_sha"]):return False
    if s.get("head_sha") is not None and (not isinstance(s["head_sha"],str) or not SHA.match(s["head_sha"])):return False
    if s.get("risk_class") not in {"R0","R1","R2","R3"} or not _sl(s.get("authorized_paths")) or not _sl(s.get("authorized_actions"),True) or not _sl(s.get("excluded_actions")):return False
    acts=set(s["authorized_actions"])
    if not acts<=CANONICAL_ACTIONS or acts&set(s["excluded_actions"]) or (not s["authorized_paths"] and not acts<=READ_ONLY):return False
    bs=s.get("additional_bindings",[])
    if not isinstance(bs,list) or any(not isinstance(b,Mapping) or set(b)!={"key","value"} or b.get("key") not in BINDING_KEYS or not isinstance(b.get("value"),str) or not b["value"] for b in bs):return False
    if not isinstance(s.get("scope_hash"),str) or not DIG.match(s["scope_hash"]):return False
    try:r=calculate_gate_scope_identity(task_id=s["task_id"],repository=s["repository"],base_ref=s["base_ref"],base_sha=s["base_sha"],working_branch=s.get("working_branch"),head_sha=s.get("head_sha"),risk_class=s["risk_class"],authorized_paths=s["authorized_paths"],authorized_actions=s["authorized_actions"],excluded_actions=s["excluded_actions"],additional_bindings=bs,calculated_at=s.get("calculated_at"))
    except Exception:return False
    keys="task_id repository base_ref base_sha working_branch head_sha risk_class authorized_paths authorized_actions excluded_actions additional_bindings outcome reason_codes scope_hash authority_granted".split()
    return all(s.get(k)==r.get(k) for k in keys)

def _reqs(task): return [{"gate":x["gate"],"artifact_role":x["artifact_role"],"target":x["target"].replace("<task-id>",task),"required":x.get("required","true")=="true"} for x in _GATE_REQUIREMENTS]
def _entry(e):
    if not isinstance(e,Mapping) or set(e)-EF or not ERQ<=set(e) or e.get("gate") not in GATE_ORDER or e.get("classification") not in CLASSES|{"AUDIT_PROJECTION","RESUME_HINT"}:return False
    if any(not isinstance(e.get(k),str) or not e[k] for k in "evidence_key artifact_role artifact_type source_type".split()):return False
    if not isinstance(e.get("required"),bool) or not isinstance(e.get("source_of_truth"),bool):return False
    if any(v is not None and (not isinstance(v,str) or not v) for v in (e.get(k) for k in "target ref revision digest".split())):return False
    return e.get("binding_status") in {"BOUND","MISMATCHED","UNOBSERVED","NOT_APPLICABLE"} and e.get("freshness_status") in {"FRESH","STALE","UNOBSERVED"} and e.get("materialization_status") in {"MATERIALIZED","MISSING","UNOBSERVED"} and isinstance(e.get("reason_codes"),list) and all(isinstance(c,str) and c for c in e["reason_codes"])
def _map(m,task):
    req=set("schema_version artifact_type task_id repository base_sha policy_revision outcome entries requirements missing_required stale_required projection_only map_digest authority_granted".split())
    if not isinstance(m,Mapping) or set(m)-MF or not req<=set(m):return False
    if m.get("schema_version")!="1.0" or m.get("artifact_type")!="gate-evidence-artifact-map" or m.get("task_id")!=task or m.get("authority_granted") is not False:return False
    if not isinstance(m.get("repository"),str) or not REPO.match(m["repository"]) or not isinstance(m.get("base_sha"),str) or not SHA.match(m["base_sha"]):return False
    if m.get("head_sha") is not None and (not isinstance(m["head_sha"],str) or not SHA.match(m["head_sha"])):return False
    if not isinstance(m.get("policy_revision"),str) or not m["policy_revision"]:return False
    rs=m.get("reason_codes")
    if not isinstance(rs,list) or not rs or len(rs)!=len(set(rs)) or any(r not in ER for r in rs):return False
    if not isinstance(m.get("requirements"),list) or sorted(m["requirements"],key=lambda x:(x.get("gate"),x.get("artifact_role")))!=sorted(_reqs(task),key=lambda x:(x["gate"],x["artifact_role"])):return False
    if not isinstance(m.get("entries"),list) or not all(_entry(e) for e in m["entries"]):return False
    if any(not _sl(m.get(k)) for k in "missing_required stale_required projection_only".split()):return False
    blocking=set(rs)&EB; listed=any(m[k] for k in "missing_required stale_required projection_only".split())
    if m.get("outcome")=="READY" and (blocking or listed):return False
    if m.get("outcome")!="READY" and (m.get("outcome")!="BLOCKED" or not(blocking or listed)):return False
    sem={"task_id":m["task_id"],"repository":m["repository"],"base_sha":m["base_sha"],"policy_revision":m["policy_revision"],"requirements":m["requirements"],"entries":sorted(m["entries"],key=lambda e:(str(e.get("gate")),str(e.get("evidence_key")))),"missing_required":m["missing_required"],"stale_required":m["stale_required"],"projection_only":m["projection_only"]}
    return isinstance(m.get("map_digest"),str) and m["map_digest"]==_dg(sem)
def _transition(t):
    keys="contract_version authority rules terminal_states verification".split()
    return isinstance(t,Mapping) and all(k in t for k in keys) and hashlib.sha256(_cj({k:t[k] for k in keys}).encode()).hexdigest()==TD

def _ref(e): return next((e[k] for k in ("ref","target","evidence_key") if isinstance(e.get(k),str) and e[k]),None)
def _status(e): return next((str(e[k]).upper() for k in ("gate_status","status","outcome") if e.get(k) is not None),None)
def _valid(e):return _entry(e) and e.get("classification") in CLASSES and e.get("source_of_truth") is True and e.get("materialization_status")=="MATERIALIZED" and e.get("binding_status")=="BOUND" and e.get("freshness_status")=="FRESH" and not set(e.get("reason_codes",[]))&EB and _status(e) in {None,"PASS","READY","SUCCESS","VALID","COMPLETED"}
def _analyze(m,prod):
    es=m["entries"]; reqs=m["requirements"]; missing=set(_ss(m["missing_required"]))|set(_ss(m["projection_only"])); stale=set(_ss(m["stale_required"])); conflicts=set(); refs=set(); seen={}
    for e in es:
        r=_ref(e); codes=set(e.get("reason_codes",[]))
        if r and _valid(e):refs.add(r)
        if r and (e.get("freshness_status")=="STALE" or "EVIDENCE_STALE" in codes):stale.add(r)
        if r and ({"EVIDENCE_CONFLICT","EVIDENCE_BINDING_MISMATCH"}&codes):conflicts.add(r)
        k=str(e.get("evidence_key",r or "")); d=str(e.get("digest",""))
        if k in seen and seen[k]!=d:conflicts.add(k)
        if k:seen[k]=d
    top=set(m["reason_codes"])
    if "EVIDENCE_CONFLICT" in top:conflicts.add("evidence_map")
    if "EVIDENCE_STALE" in top and not stale:stale.add("evidence_map")
    if top&{"EVIDENCE_REQUIRED_MISSING","EVIDENCE_PROJECTION_ONLY","EVIDENCE_OBSERVABILITY_INCOMPLETE"} and not missing:missing.add("evidence_map")
    out=[]; first={"gate":None,"status":None,"failed":False}; last=None
    for gate in GATE_ORDER:
        if gate=="G6_PRODUCTION_DATA" and not prod:out.append({"gate":gate,"status":"NOT_APPLICABLE","reason_codes":["GATE_STATE_G6_NOT_APPLICABLE"]});continue
        rr=sorted({r["target"] for r in reqs if r["gate"]==gate and (r["required"] or(prod and gate=="G6_PRODUCTION_DATA"))}); ge=[e for e in es if e["gate"]==gate]
        valid=sorted({_ref(e) for e in ge if _valid(e) and _ref(e)}); run=sorted({_ref(e) for e in ge if _status(e) in {"RUNNING","PENDING","IN_PROGRESS"} and _ref(e)}); fail=sorted({_ref(e) for e in ge if _status(e) in {"FAILED","FAIL","ERROR","BLOCKED"} and _ref(e)})
        gs=sorted({r for r in stale if r in rr or any(_ref(e)==r for e in ge)}); gc=sorted({r for r in conflicts if r in rr or any(_ref(e)==r for e in ge)}); gm=sorted(set(rr)-set(valid)-set(run)-set(fail))
        if gate=="G5_DEPLOY" and not rr and not(valid or run or fail):gm=["G5_STATUS_VERIFY"]
        if gate=="G6_PRODUCTION_DATA" and prod and not rr and not(valid or run or fail):gm=["G6_PRODUCTION_SCOPE_EVIDENCE"]
        st="FAILED" if fail else "BLOCKED" if gc or gs or gm else "RUNNING" if run else "PASS"; out.append({"gate":gate,"status":st,"reason_codes":[]})
        if first["gate"] is None and st!="PASS":first={"gate":gate,"status":st,"failed":bool(fail)}
        if first["gate"] is None:last=gate
    later=bool(first["gate"] and any(x["status"] in {"PASS","RUNNING"} for x in out[GATE_ORDER.index(first["gate"])+1:] if x["gate"]!="G6_PRODUCTION_DATA"))
    return {"evaluations":out,"refs":sorted(refs),"missing":sorted(missing),"stale":sorted(stale),"conflicts":sorted(conflicts),"first":first,"last":last,"later":later}
def _drift(base,s,m):
    r=[]
    if s.get("base_sha")!=base:r.append("BASE_SHA_DRIFT")
    if m.get("base_sha")!=base:r.append("EVIDENCE_BASE_SHA_DRIFT")
    if s.get("head_sha") and m.get("head_sha") and s.get("head_sha")!=m.get("head_sha"):r.append("HEAD_SHA_DRIFT")
    if any(e.get("binding_status")=="MISMATCHED" and any("DRIFT" in c or "CI_BINDING" in c for c in e.get("reason_codes",[])) for e in m["entries"]):r.append("ENTRY_DRIFT")
    return sorted(set(r))
def _warnings(p,task,repo,gate,status,t):
    if p is None:return []
    if not isinstance(p,Mapping):return ["PROJECTION_INVALID"]
    w=[]
    if p.get("task_id") not in {None,task}:w.append("TASK_ID_MISMATCH")
    if p.get("repository") not in {None,repo}:w.append("REPOSITORY_MISMATCH")
    if p.get("current_gate") not in {None,gate}:w.append("CURRENT_GATE_MISMATCH")
    if p.get("status") not in {None,status}:w.append("STATUS_MISMATCH")
    states={"completed","cancelled"}|{r["from_state"] for r in t["rules"]}|{r["expected_state"] for r in t["rules"]}
    if p.get("state") not in states|{None}:w.append("PROJECTION_STATE_UNKNOWN")
    if p.get("state")=="cancelled":w.append("CANCELLED_PROJECTION_WITHOUT_CANONICAL_EVIDENCE")
    return sorted(set(w))
def _action(rs,status,nxt):
    for code,act in (("GATE_STATE_INPUT_INVALID","FIX_INPUT"),("GATE_STATE_REPLAY_CONFLICT","STOP_AND_RECONCILE_REPLAY"),("GATE_STATE_BINDING_MISMATCH","REBUILD_BINDINGS"),("GATE_STATE_EVIDENCE_CONFLICT","RESOLVE_EVIDENCE_CONFLICT"),("GATE_STATE_GATE_FAILED","RECOVER_FAILED_GATE"),("GATE_STATE_DRIFT","REVALIDATE_OR_REAPPROVE"),("GATE_STATE_EVIDENCE_STALE","REFRESH_EVIDENCE"),("GATE_STATE_REQUIRED_EVIDENCE_MISSING","MATERIALIZE_REQUIRED_EVIDENCE")):
        if code in rs:return act
    return "WAIT_FOR_GATE_COMPLETION" if status=="RUNNING" else "COMPLETE" if nxt is None else "ADVANCE_GATE"
def _empty(task,repo,base,scope,event,observed,digest):
    o={"schema_version":"1.0","artifact_type":"gate-state-resolution","task_id":task,"repository":repo,"current_base_sha":base,"scope_hash":scope,"head_sha":None,"current_gate":"G0_CONTEXT","gate_status":"BLOCKED","last_passed_gate":None,"next_gate":"G0_CONTEXT","next_action_class":"FIX_INPUT","canonical_evidence_refs":[],"projection_warnings":[],"missing_evidence":[],"stale_evidence":[],"conflicting_evidence":[],"drift_decision":{"status":"NO_DRIFT","reason_codes":[]},"primary_reason_code":"GATE_STATE_INPUT_INVALID","reason_codes":["GATE_STATE_INPUT_INVALID"],"event_id_or_idempotency_key":event,"replay_status":"FIRST_SEEN","resolution_digest":digest,"observed_at":observed,"gate_evaluations":[]};o.update({f:False for f in FLAGS});return o

def resolve_gate_state(*,task_id:str,repository:str,current_base_sha:str,scope_identity:dict[str,object],evidence_map:dict[str,object],transition_map:dict[str,object],task_projection:dict[str,object]|None,event_id_or_idempotency_key:str,prior_resolution:dict[str,object]|None=None,observed_at:str|None=None)->dict[str,object]:
    sem={"task_id":task_id,"repository":repository,"current_base_sha":current_base_sha,"scope_identity":_strip(scope_identity),"evidence_map":_strip(evidence_map),"transition_map":_strip(transition_map),"task_projection":_strip(task_projection),"event_id_or_idempotency_key":event_id_or_idempotency_key}; digest=_dg(sem); sh=scope_identity.get("scope_hash") if isinstance(scope_identity,Mapping) else None
    o=_empty(task_id if isinstance(task_id,str) else "",repository if isinstance(repository,str) else "",current_base_sha if isinstance(current_base_sha,str) else "",sh if isinstance(sh,str) else None,event_id_or_idempotency_key if isinstance(event_id_or_idempotency_key,str) else "",observed_at,digest)
    if not isinstance(task_id,str) or not task_id or not isinstance(repository,str) or not REPO.match(repository) or not isinstance(current_base_sha,str) or not SHA.match(current_base_sha) or not _scope(scope_identity) or not _map(evidence_map,task_id) or not _transition(transition_map) or not isinstance(event_id_or_idempotency_key,str) or not event_id_or_idempotency_key or prior_resolution is not None and not isinstance(prior_resolution,Mapping):return o
    bind=[]
    if scope_identity.get("task_id")!=task_id or scope_identity.get("repository")!=repository:bind.append("scope")
    if evidence_map.get("task_id")!=task_id or evidence_map.get("repository")!=repository:bind.append("evidence")
    if "EVIDENCE_BINDING_MISMATCH" in evidence_map.get("reason_codes",[]):bind.append("evidence_binding")
    if prior_resolution and (prior_resolution.get("task_id")!=task_id or prior_resolution.get("repository")!=repository or prior_resolution.get("scope_hash")!=scope_identity.get("scope_hash")):bind.append("prior")
    prod=bool(set(scope_identity["authorized_actions"])&PRODUCTION); a=_analyze(evidence_map,prod); o.update({"gate_evaluations":a["evaluations"],"canonical_evidence_refs":a["refs"],"missing_evidence":a["missing"],"stale_evidence":a["stale"],"conflicting_evidence":a["conflicts"],"last_passed_gate":a["last"],"head_sha":scope_identity.get("head_sha")}); first=a["first"]
    if first["gate"] is None:gate="G6_PRODUCTION_DATA";status="PASS" if prod else "NOT_APPLICABLE";nxt=None;o["last_passed_gate"]=gate if prod else o["last_passed_gate"]
    else:gate,status,nxt=first["gate"],first["status"],first["gate"]
    same=bool(prior_resolution and prior_resolution.get("event_id_or_idempotency_key")==event_id_or_idempotency_key); conflict=bool(same and prior_resolution.get("resolution_digest")!=digest); idem=bool(same and prior_resolution.get("resolution_digest")==digest); drift=_drift(current_base_sha,scope_identity,evidence_map); rs=[]
    if conflict:rs.append("GATE_STATE_REPLAY_CONFLICT")
    if bind:rs.append("GATE_STATE_BINDING_MISMATCH")
    if a["conflicts"]:rs.append("GATE_STATE_EVIDENCE_CONFLICT")
    if first["failed"]:rs.append("GATE_STATE_GATE_FAILED")
    if drift:rs.append("GATE_STATE_DRIFT")
    if a["stale"]:rs.append("GATE_STATE_EVIDENCE_STALE")
    if a["missing"]:rs.append("GATE_STATE_REQUIRED_EVIDENCE_MISSING")
    if a["later"]:rs.append("GATE_STATE_LATER_GATE_INHERITANCE_REJECTED")
    if not rs:rs=["GATE_STATE_RESOLVED"]+([] if prod else ["GATE_STATE_G6_NOT_APPLICABLE"])
    if set(rs)&set("GATE_STATE_REPLAY_CONFLICT GATE_STATE_BINDING_MISMATCH GATE_STATE_EVIDENCE_CONFLICT GATE_STATE_GATE_FAILED GATE_STATE_DRIFT GATE_STATE_EVIDENCE_STALE GATE_STATE_REQUIRED_EVIDENCE_MISSING".split()):
        status="FAILED" if first["failed"] else "BLOCKED"
        if bind:gate="G0_CONTEXT";o["last_passed_gate"]=None
        elif drift and set(drift)&{"BASE_SHA_DRIFT","EVIDENCE_BASE_SHA_DRIFT"}:gate="G0_CONTEXT";o["last_passed_gate"]=None
        elif drift:gate="G2_EXECUTION";o["last_passed_gate"]="G1_ALIGNMENT"
        nxt=gate
    w=_warnings(task_projection,task_id,repository,gate,status,transition_map)
    if w:rs.append("GATE_STATE_PROJECTION_MISMATCH")
    rs=_sr(rs);o.update({"current_gate":gate,"gate_status":status,"next_gate":nxt,"projection_warnings":w,"drift_decision":{"status":"REAPPROVE" if drift else "NO_DRIFT","reason_codes":drift},"primary_reason_code":rs[0],"reason_codes":rs,"replay_status":"REPLAY_CONFLICT" if conflict else "IDEMPOTENT_REPLAY" if idem else "FIRST_SEEN"});o["next_action_class"]=_action(rs,status,nxt);return o
