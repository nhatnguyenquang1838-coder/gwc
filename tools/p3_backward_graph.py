#!/usr/bin/env python3
"""Deterministic P3 backward graph compiler and scenario routing engine."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, MutableSequence, Sequence

class CompileError(ValueError): pass
class RouteClass(str, Enum):
    VALID_AUTO="VALID_AUTO"; VALID_HUMAN="VALID_HUMAN"; CONDITIONAL="CONDITIONAL"; BLOCKED="BLOCKED"; UNSAFE="UNSAFE"
@dataclass(frozen=True)
class GuardResult:
    passed: bool
    conditional: bool=False
    reason: str=""

def _stable(value: Any)->str: return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True)
def _digest(value: Any)->str: return "sha256:"+sha256(_stable(value).encode()).hexdigest()
def _graph_revision(nodes: Sequence[Mapping[str,Any]])->str:
    return _digest([{k:n[k] for k in sorted(n)} for n in sorted(nodes,key=lambda n:str(n["id"]))])
def _index(nodes):
    out={}
    for node in nodes:
        i=str(node.get("id",""))
        if not i or i in out: raise CompileError("MISSING_DEPENDENCY: node ids must be unique and non-empty")
        out[i]=node
    return out
def _dependencies(node): return tuple(sorted(str(i) for i in node.get("dependencies",[])))

def compile_backward_graph(nodes,desired_outcome,safe_failure_outcome,*,profile="standard",allowed_authorities=()):
    indexed=_index(nodes)
    if desired_outcome not in indexed or safe_failure_outcome not in indexed: raise CompileError("MISSING_TERMINAL: desired or safe-failure outcome is absent")
    authorities=set(allowed_authorities); state={}; order=[]; rejected=[]
    def visit(i):
        if i not in indexed: raise CompileError(f"MISSING_DEPENDENCY: {i}")
        if state.get(i)==1: raise CompileError(f"CYCLE_UNSAFE: {i}")
        if state.get(i)==2:return
        state[i]=1; node=indexed[i]; overlay=(node.get("profiles") or {}).get(profile,{})
        if overlay.get("enabled") is False: raise CompileError(f"PROFILE_MISMATCH: {i} disabled for {profile}")
        if node.get("required_profile") and node["required_profile"]!=profile: raise CompileError(f"PROFILE_MISMATCH: {i} requires {node['required_profile']}")
        authority=str(node.get("authority","AUTO"))
        if authority not in {"AUTO","READ_ONLY"} and authority not in authorities:
            rejected.append({"id":i,"reason":"AUTHORITY_MISMATCH"}); raise CompileError(f"AUTHORITY_MISMATCH: {i} requires {authority}")
        if node.get("unsafe") is True: raise CompileError(f"UNSAFE_TERMINAL: {i}")
        for dep in _dependencies(node): visit(dep)
        state[i]=2; order.append(i)
    visit(desired_outcome)
    return {"graph_revision":_graph_revision(nodes),"profile":profile,"desired_outcome":desired_outcome,"safe_failure_outcome":safe_failure_outcome,"selected_nodes":order,"rejected_nodes":rejected,"status":"COMPILED"}

def evaluate_guard(guard,context):
    kind=guard.get("type"); field=guard.get("field"); actual=context.get(field); expected=guard.get("value")
    if kind=="exists": passed=field in context
    elif kind=="equals":
        if isinstance(expected,str) and expected in context and field!=expected: expected=context[expected]
        passed=type(actual) is type(expected) and actual==expected
    elif kind=="in": passed=any(type(actual) is type(i) and actual==i for i in guard.get("values",[]))
    elif kind=="gte": passed=isinstance(actual,(int,float)) and not isinstance(actual,bool) and isinstance(expected,(int,float)) and not isinstance(expected,bool) and actual>=expected
    elif kind=="lte": passed=isinstance(actual,(int,float)) and not isinstance(actual,bool) and isinstance(expected,(int,float)) and not isinstance(expected,bool) and actual<=expected
    else:return GuardResult(False,False,f"UNKNOWN_GUARD_TYPE:{kind}")
    return GuardResult(True) if passed else GuardResult(False,bool(guard.get("conditional")),str(guard.get("reason","GUARD_FAILED")))

def enumerate_routes(nodes,start,green,context,*,max_depth=32):
    indexed=_index(nodes)
    if start not in indexed or green not in indexed: raise CompileError("MISSING_TERMINAL: route endpoint absent")
    routes=[]
    def walk(i,path,conditional,human,blocked,unsafe):
        if len(path)>max_depth:return
        node=indexed[i]; results=[evaluate_guard(x,context) for x in node.get("guards",[])]
        conditional=conditional or any(r.conditional and not r.passed for r in results)
        blocked=blocked or any(not r.passed and not r.conditional for r in results)
        human=human or str(node.get("authority","AUTO")) not in {"AUTO","READ_ONLY"}
        unsafe=unsafe or node.get("unsafe") is True
        if i==green:
            cls=RouteClass.UNSAFE if unsafe else RouteClass.BLOCKED if blocked else RouteClass.CONDITIONAL if conditional else RouteClass.VALID_HUMAN if human else RouteClass.VALID_AUTO
            routes.append({"path":path,"class":cls.value,"length":len(path)}); return
        for nxt in sorted(str(x) for x in node.get("successors",[])):
            if nxt not in indexed: raise CompileError(f"MISSING_DEPENDENCY: {nxt}")
            if nxt not in path: walk(nxt,path+[nxt],conditional,human,blocked,unsafe)
    walk(start,[start],False,False,False,False)
    rank={c.value:i for i,c in enumerate(RouteClass)}
    routes.sort(key=lambda r:(rank[r["class"]],r["length"],tuple(r["path"])))
    for i,r in enumerate(routes,1):r["rank"]=i
    return routes

def route_decision(nodes,start,green,context):
    routes=enumerate_routes(nodes,start,green,context); selected=routes[0] if routes else None
    return {"graph_revision":_graph_revision(nodes),"routes":routes,"selected_route":selected,"status":"ROUTED" if selected else "NO_ROUTE"}

def scenario_nodes(scenario, node_metadata=()):
    meta={str(n["id"]):dict(n) for n in node_metadata}; out={i:{"id":i,"successors":[]} for i in scenario.get("route_nodes",[])}
    for i,m in meta.items():
        if i in out:out[i].update(m);out[i].setdefault("successors",[])
    for e in scenario.get("edges",[]):
        if e.get("runtime_executable") and e.get("edge_type") in {"runtime","dependency"}:
            out.setdefault(e["source"],{"id":e["source"],"successors":[]})["successors"].append(e["target"])
            out.setdefault(e["target"],{"id":e["target"],"successors":[]})
    return [out[i] for i in sorted(out)]

def append_scenario_decision(history: MutableSequence[Mapping[str,Any]], decision: Mapping[str,Any]):
    for existing in history:
        if existing.get("decision_id")==decision.get("decision_id"):
            if _stable(existing)!=_stable(decision): raise CompileError("IMMUTABILITY_VIOLATION: decision id rebound")
            return existing
    history.append(dict(decision)); return decision

def decide_scenario(scenario,facts,*,node_metadata=(),history=None):
    missing=[f for f in scenario.get("activation_facts",[]) if f not in facts]
    guard_results=[]
    for guard in scenario.get("guards",[]):
        result=evaluate_guard(guard,facts); guard_results.append({"id":guard.get("id"),"passed":result.passed,"conditional":result.conditional,"reason":result.reason})
    policy=scenario["route_policy"]; nodes=scenario_nodes(scenario,node_metadata)
    routes=[]
    for green in policy.get("green_targets",[]): routes.extend(enumerate_routes(nodes,policy["start_node"],green,facts,max_depth=policy.get("max_depth",32)))
    routes.sort(key=lambda r:(r["rank"],r["length"],tuple(r["path"])))
    for i,r in enumerate(routes,1):r["rank"]=i
    blocked=any(not r["passed"] and not r["conditional"] for r in guard_results)
    conditional=bool(missing) or any(not r["passed"] and r["conditional"] for r in guard_results)
    selected=routes[0] if routes else None
    classification="BLOCKED" if blocked or not selected else "CONDITIONAL" if conditional else selected["class"]
    record={"scenario_id":scenario["id"],"scenario_version":scenario["version"],"graph_revision":_graph_revision(nodes),"facts_digest":_digest(facts),"missing_activation_facts":missing,"guard_results":guard_results,"candidate_routes":routes,"selected_route":selected,"classification":classification,"auto_execute":classification=="VALID_AUTO"}
    record["decision_id"]=_digest(record); record["decision_digest"]=record["decision_id"]
    if history is not None: append_scenario_decision(history,record)
    return record
