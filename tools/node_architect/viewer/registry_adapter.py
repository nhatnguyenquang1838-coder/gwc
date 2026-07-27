#!/usr/bin/env python3
"""Data-only Cytoscape v3 adapter for canonical registries and history."""
from __future__ import annotations
import argparse,json
from collections import defaultdict
from pathlib import Path
from typing import Any,Iterable,Mapping
from tools.node_architect.viewer.run_history_adapter import build_run_history_elements,overlay_run_history
REGISTRY_FILES={"nodes":"core/node-architect/node-registry.json","scenarios":"core/node-architect/scenario-registry.json","profiles":"core/node-architect/profile-registry.json","graph":"core/node-architect/runtime-graph-registry.json"}
def load_registry_bundle(root):
    return {n:json.loads((root/p).read_text()) for n,p in REGISTRY_FILES.items()}
def _edge_classes(edge):
    c=[edge["edge_type"]]
    if edge["edge_type"] in {"visualization","suggested_sequence","audit"}:c.append("visual-only")
    if edge["runtime_executable"]:c.append("runtime-executable")
    return c
def build_scenario_decision_elements(decision):
    did=str(decision.get("decision_id") or decision.get("decision_digest") or "unknown")
    sid=str(decision.get("scenario_id") or "unknown"); scenario_id=f"scenario:{sid}"
    nodes=[{"data":{"id":scenario_id,"kind":"scenario","scenario_id":sid,"scenario_version":decision.get("scenario_version"),"classification":decision.get("classification"),"decision_id":did,"graph_revision":decision.get("graph_revision"),"provenance":"scenario-decision-history"},"classes":f"scenario-decision {str(decision.get('classification','unknown')).lower()}"}]
    edges=[]; selected=decision.get("selected_route") or {}
    for route in decision.get("candidate_routes") or []:
        rid=f"route:{did}:{route.get('rank')}"; chosen=route.get("path")==selected.get("path")
        nodes.append({"data":{"id":rid,"kind":"candidate-route","decision_id":did,"rank":route.get("rank"),"classification":route.get("class"),"path":route.get("path",[])},"classes":("selected-route" if chosen else "candidate-route")+" "+str(route.get("class","")).lower()})
        edges.append({"data":{"id":f"scenario-route:{did}:{route.get('rank')}","source":scenario_id,"target":rid,"edge_type":"scenario-route-history","runtime_executable":False,"provenance":"scenario-decision-history"},"classes":"scenario-route-history visual-only"})
        for idx,node_id in enumerate(route.get("path",[])):
            edges.append({"data":{"id":f"route-node:{did}:{route.get('rank')}:{idx}","source":rid,"target":node_id,"edge_type":"scenario-route-node","runtime_executable":False,"provenance":"scenario-decision-history"},"classes":"scenario-route-node visual-only"})
    return {"nodes":nodes,"edges":edges}
def build_cytoscape_elements(bundle,active_node_ids=None,run_history=None,scenario_decision=None):
    active=set(active_node_ids or ()); nodes=[]
    for node in bundle["nodes"]["nodes"]:
        i=node["id"]; classes=["runtime-node","active" if not active or i in active else "inactive"]
        nodes.append({"data":{"id":i,"label":i,"family":node["family"],"maturity":node["maturity"],"source_status":node["source_status"],"provenance":node["provenance"]},"classes":" ".join(classes)})
    edges=[]
    for idx,e in enumerate(bundle["graph"]["edges"]):
        edges.append({"data":{"id":f"edge-{idx}",**e},"classes":" ".join(_edge_classes(e))})
    elements={"nodes":nodes,"edges":edges}
    if run_history is not None: elements=overlay_run_history(elements,build_run_history_elements(run_history))
    if scenario_decision is not None: elements=overlay_run_history(elements,build_scenario_decision_elements(scenario_decision))
    return elements
def enumerate_routes_to_green(bundle,start_node_ids,green_targets,max_routes=256):
    green=set(green_targets); adjacency=defaultdict(list)
    for e in bundle["graph"]["edges"]:
        if e["runtime_executable"] and e["edge_type"] in {"runtime","dependency"}:adjacency[e["source"]].append(e["target"])
    routes=[]
    def visit(path):
        if len(routes)>=max_routes:return
        if path[-1] in green:routes.append(path.copy());return
        for target in adjacency.get(path[-1],[]):
            if target not in path:visit(path+[target])
    for s in start_node_ids:visit([s])
    return routes
def classify_route(route,green_targets,human_boundaries=()):
    if any(b in route for b in human_boundaries):return "HUMAN_REQUIRED"
    return "VALID_AUTO" if route and route[-1] in set(green_targets) else "CONDITIONAL"
