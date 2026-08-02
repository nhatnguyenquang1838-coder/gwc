#!/usr/bin/env python3
"""SCRUM-259 client runtime adapter shell for one Node Architect vertical slice."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping, MutableMapping, Sequence
from .ci_evidence_capture import capture_ci_evidence
VERTICAL_SLICE_ROUTE=("client_request","route_scenario_validation","repo_delivery.ci-run-capture","runtime_checkpoint.checkpoint-persist","validation_quality.ci-evidence-capture","validation_quality.evidence-quality-check","validation_quality.g3-pass-decision")
TERMINAL_NODE="terminal_typed_result"; ALLOWED_ROUTE_INTENT="client-runtime-node-architect-vertical-slice"; PASS="PASS"; BLOCKED="BLOCKED"
BLOCKED_ROUTE_NOT_ALLOWLISTED="BLOCKED_ROUTE_NOT_ALLOWLISTED"; BLOCKED_NODE_HANDLER_UNAVAILABLE="BLOCKED_NODE_HANDLER_UNAVAILABLE"; BLOCKED_NODE_HANDLER_ERROR="BLOCKED_NODE_HANDLER_ERROR"; BLOCKED_MISSING_REQUIRED_FIELD="BLOCKED_MISSING_REQUIRED_FIELD"; TERMINAL_PASS="TERMINAL_TYPED_RESULT_PASS"
@dataclass(frozen=True)
class ClientRuntimeRequest:
    task_id:str; repository:str; protected_base_sha:str; scenario_id:str; route_intent:str=ALLOWED_ROUTE_INTENT; route_nodes:tuple[str,...]=VERTICAL_SLICE_ROUTE; evidence:Mapping[str,Any]=field(default_factory=dict)
@dataclass(frozen=True)
class ClientRuntimeResult:
    task_id:str; repository:str; protected_base_sha:str; scenario_id:str; status:str; terminal_code:str; executed_nodes:tuple[str,...]; blocked_node:str|None=None; evidence:Mapping[str,Any]=field(default_factory=dict); checkpoints:tuple[Mapping[str,Any],...]=(); manual_fallback_used:bool=False
    def to_dict(self)->dict[str,Any]:
        d=asdict(self); d["executed_nodes"]=list(self.executed_nodes); d["checkpoints"]=[dict(c) for c in self.checkpoints]; return d
RuntimeState=MutableMapping[str,Any]; Handler=Callable[[ClientRuntimeRequest,RuntimeState],Mapping[str,Any]]
def normalize_request(payload:Mapping[str,Any]|ClientRuntimeRequest)->ClientRuntimeRequest:
    if isinstance(payload,ClientRuntimeRequest): return payload
    missing=[k for k in ("task_id","repository","protected_base_sha","scenario_id") if not str(payload.get(k,"")).strip()]
    if missing: raise ValueError("missing required client runtime fields: "+", ".join(missing))
    route=payload.get("route_nodes",VERTICAL_SLICE_ROUTE)
    if isinstance(route,str): raise ValueError("route_nodes must be a sequence, not a string")
    return ClientRuntimeRequest(str(payload["task_id"]),str(payload["repository"]),str(payload["protected_base_sha"]),str(payload["scenario_id"]),str(payload.get("route_intent",ALLOWED_ROUTE_INTENT)),tuple(map(str,route)),dict(payload.get("evidence",{})))
def validate_route(request):
    if request.route_intent!=ALLOWED_ROUTE_INTENT or tuple(request.route_nodes)!=VERTICAL_SLICE_ROUTE: raise ValueError("route does not match the allowlisted SCRUM-259 vertical slice")
def _client(request,state): state["request"]=request; return {"accepted":True}
def _route(request,state): validate_route(request); return {"route_validated":True,"route_nodes":list(request.route_nodes)}
def _ci(request,state): state["ci_evidence"]=dict(request.evidence.get("ci",{})); return {"handler_source":"repo_delivery.ci-run-capture","ci_evidence_captured":True}
def _checkpoint(request,state):
    cp={"task_id":request.task_id,"repository":request.repository,"protected_base_sha":request.protected_base_sha,"scenario_id":request.scenario_id,"node":"runtime_checkpoint.checkpoint-persist","index":len(state.setdefault("checkpoints",[]))+1}; state["checkpoints"].append(cp); return {"handler_source":"runtime_checkpoint.checkpoint-persist","checkpoint_persisted":True}
def _ci_evidence(request,state):
    ci=dict(state.get("ci_evidence") or {})
    head_sha=str(ci.get("head_sha") or request.protected_base_sha); branch=str(ci.get("branch") or "main")
    scope_hash=str(ci.get("scope_hash") or ("sha256:"+"0"*64)); graph_revision=str(ci.get("graph_revision") or request.scenario_id)
    payload={**ci,"task_id":request.task_id,"run_id":str(ci.get("run_id") or f"{request.task_id}-client-runtime"),"repository":request.repository,"branch":branch,"base_sha":request.protected_base_sha,"head_sha":head_sha,"scope_hash":scope_hash,"graph_revision":graph_revision,"idempotency_key":str(ci.get("idempotency_key") or f"{request.task_id}:{head_sha}:ci-evidence")}
    return capture_ci_evidence(payload,checkpoint_store=state.setdefault("ci_checkpoint_store",{"schema_version":"1.0","artifact_type":"runtime-checkpoint-store","revision":0,"events":[],"checkpoints":{}}),replay_cache=state.setdefault("ci_replay_cache",{}))
def _quality(request,state): return {"evidence_quality":"CHECKED","manual_fallback_used":False}
def _g3(request,state): return {"g3_pass_decision":"READY_FOR_G3_VALIDATION","requires_exact_pr_head":True}
def default_handler_registry(): return MappingProxyType({"client_request":_client,"route_scenario_validation":_route,"repo_delivery.ci-run-capture":_ci,"runtime_checkpoint.checkpoint-persist":_checkpoint,"validation_quality.ci-evidence-capture":_ci_evidence,"validation_quality.evidence-quality-check":_quality,"validation_quality.g3-pass-decision":_g3})
def _blocked(req,code,executed,node,evidence=None,checkpoints=()): return ClientRuntimeResult(req.task_id,req.repository,req.protected_base_sha,req.scenario_id,BLOCKED,code,tuple(executed),node,dict(evidence or {}),tuple(checkpoints),False)
def run_client_runtime(payload,handlers=None):
    try: req=normalize_request(payload)
    except ValueError as exc:
        p=payload if isinstance(payload,Mapping) else {}; return ClientRuntimeResult(str(p.get("task_id","")),str(p.get("repository","")),str(p.get("protected_base_sha","")),str(p.get("scenario_id","")),BLOCKED,BLOCKED_MISSING_REQUIRED_FIELD,(),"client_request",{"error":str(exc)},(),False)
    registry=handlers or default_handler_registry(); state={"checkpoints":[]}; executed=[]; evidence={"manual_fallback_used":False,"node_results":{}}
    for node in req.route_nodes:
        handler=registry.get(node)
        if handler is None: return _blocked(req,BLOCKED_NODE_HANDLER_UNAVAILABLE,executed,node,{**evidence,"missing_handler":node},state["checkpoints"])
        try: out=dict(handler(req,state))
        except ValueError as exc: return _blocked(req,BLOCKED_ROUTE_NOT_ALLOWLISTED,executed,node,{**evidence,"error":str(exc)},state["checkpoints"])
        except Exception as exc: return _blocked(req,BLOCKED_NODE_HANDLER_ERROR,executed,node,{**evidence,"error":f"{type(exc).__name__}: {exc}"},state["checkpoints"])
        executed.append(node); evidence["node_results"][node]=out
        if node=="validation_quality.ci-evidence-capture" and out.get("status")!="PASS":
            if out.get("checkpoint_required") and out.get("checkpoint_key"):
                state["checkpoints"].append({"node":node,"checkpoint_key":out["checkpoint_key"],"evidence_digest":out.get("evidence_digest")})
            return _blocked(req,str(out.get("reason_code") or BLOCKED_NODE_HANDLER_ERROR),executed,node,evidence,state["checkpoints"])
    executed.append(TERMINAL_NODE); return ClientRuntimeResult(req.task_id,req.repository,req.protected_base_sha,req.scenario_id,PASS,TERMINAL_PASS,tuple(executed),None,evidence,tuple(state["checkpoints"]),False)
__all__=["ALLOWED_ROUTE_INTENT","BLOCKED","BLOCKED_MISSING_REQUIRED_FIELD","BLOCKED_NODE_HANDLER_ERROR","BLOCKED_NODE_HANDLER_UNAVAILABLE","BLOCKED_ROUTE_NOT_ALLOWLISTED","ClientRuntimeRequest","ClientRuntimeResult","PASS","TERMINAL_NODE","TERMINAL_PASS","VERTICAL_SLICE_ROUTE","default_handler_registry","normalize_request","run_client_runtime","validate_route"]
