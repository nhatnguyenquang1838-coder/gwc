#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
from jsonschema import Draft202012Validator,RefResolver
FAMILIES={"intake_context","gate_authority","repo_delivery","runtime_checkpoint","validation_quality","sync_projection","package_export","failure_recovery","scale_control"}
EXPLICIT_NODES={"repo_delivery.ci-run-capture","runtime_checkpoint.checkpoint-persist","validation_quality.ci-evidence-capture","failure_recovery.timeout-recovery"}
VISUAL_EDGE_TYPES={"visualization","suggested_sequence","audit","human_authority","blocked"}; RUNTIME_EDGE_TYPES={"runtime","dependency"}; GUARD_TYPES={"exists","equals","in","gte","lte"}
def load(p):return json.loads(p.read_text())
def validate_schema(payload,schema_path,schema_dir):
 s=load(schema_path);store={};Draft202012Validator.check_schema(s)
 for c in schema_dir.glob('*.schema.json'):
  x=load(c)
  if x.get('$id'):store[x['$id']]=x
 return [e.message for e in Draft202012Validator(s,resolver=RefResolver(s.get('$id',schema_path.as_uri()),s,store)).iter_errors(payload)]
def source_hash(root,relative):
 p=root/relative
 return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def validate_registry(root):
 runtime=root/'schemas/runtime'; rr=root/'core/node-architect'; paths={'nodes':rr/'node-registry.json','scenarios':rr/'scenario-registry.json','profiles':rr/'profile-registry.json','rules':rr/'decision-rule-registry.json','graph':rr/'runtime-graph-registry.json'}; payloads={n:load(p) for n,p in paths.items()}; issues=[]
 for n,sn in {'nodes':'node-registry.schema.json','scenarios':'scenario-registry.schema.json','profiles':'profile-registry.schema.json','rules':'decision-rule-registry.schema.json','graph':'runtime-graph.schema.json'}.items():issues += [f'{n}: {e}' for e in validate_schema(payloads[n],runtime/sn,runtime)]
 nodes=payloads['nodes'].get('nodes',[]); node_ids=[n.get('id') for n in nodes]; node_set=set(node_ids); families={f:0 for f in FAMILIES}
 if len(nodes)!=81:issues.append(f'node registry must materialize exactly 81 slots, got {len(nodes)}')
 if len(node_set)!=len(node_ids):issues.append('node registry contains duplicate stable IDs')
 for n in nodes:
  f=n.get('family'); families[f]=families.get(f,0)+1
  actual=source_hash(root,n.get('provenance',{}).get('source_path',''))
  if actual is None:issues.append(f"node {n.get('id')} provenance source is missing")
  elif actual!=n.get('provenance',{}).get('source_sha'):issues.append(f"node {n.get('id')} provenance SHA does not match source")
 if {f for f,c in families.items() if c}!=FAMILIES:issues.append(f'node registry families are incomplete: {families}')
 if {n.get('id') for n in nodes if n.get('source_status')=='canonical_explicit'}!=EXPLICIT_NODES:issues.append('canonical explicit node set does not match the four source-backed KG nodes')
 if sum(n.get('source_status')=='proposed_registry_slot' for n in nodes)!=77:issues.append('node registry must classify exactly 77 proposed registry slots')
 rules=payloads['rules'].get('rules',[]); rule_ids={r.get('id') for r in rules}; scenarios=payloads['scenarios'].get('scenarios',[]); ids=[s.get('id') for s in scenarios]
 if len(ids)!=len(set(ids)):issues.append('scenario registry contains duplicate stable IDs')
 if payloads['scenarios'].get('materialized_scenario_count')!=len(scenarios):issues.append('materialized scenario count does not match scenario entries')
 if len(scenarios)!=14:issues.append(f'scenario registry must materialize exactly 14 scenarios, got {len(scenarios)}')
 if payloads['scenarios'].get('declared_scenario_count')!=116:issues.append('declared scenario count must remain 116 and separate from materialized entries')
 for s in scenarios:
  sid=s.get('id'); missing_rules=set(s.get('rules',[]))-rule_ids; missing_nodes=set(s.get('route_nodes',[]))-node_set
  if missing_rules:issues.append(f'scenario {sid} has unresolved rules {sorted(missing_rules)}')
  if missing_nodes:issues.append(f'scenario {sid} has unresolved route nodes {sorted(missing_nodes)}')
  guards=s.get('guards',[]); gids=[g.get('id') for g in guards]
  if len(gids)!=len(set(gids)):issues.append(f'scenario {sid} has duplicate guard ids')
  for g in guards:
   if g.get('type') not in GUARD_TYPES:issues.append(f'scenario {sid} has unsupported guard type {g.get("type")}')
   if g.get('type')=='in' and 'values' not in g:issues.append(f'scenario {sid} in guard requires values')
   if g.get('type') in {'equals','gte','lte'} and 'value' not in g:issues.append(f'scenario {sid} guard {g.get("id")} requires value')
  policy=s.get('route_policy',{}); start=policy.get('start_node'); targets=set(policy.get('green_targets',[]))
  if start not in node_set or start not in set(s.get('route_nodes',[])):issues.append(f'scenario {sid} has unresolved route-policy start node')
  if not targets or not targets <= node_set or targets!=set(s.get('green_targets',[])):issues.append(f'scenario {sid} has invalid route-policy green targets')
  actual=source_hash(root,s.get('provenance',{}).get('source_path',''))
  if actual is None:issues.append(f'scenario {sid} provenance source is missing')
  elif actual!=s.get('provenance',{}).get('source_sha'):issues.append(f'scenario {sid} provenance SHA does not match source')
  for e in s.get('edges',[]):
   if e.get('source') not in node_set or e.get('target') not in node_set:issues.append(f'scenario {sid} has an unresolved edge endpoint')
   if e.get('edge_type') in VISUAL_EDGE_TYPES and e.get('runtime_executable'):issues.append(f'scenario {sid} marks a visual edge executable')
 graph=payloads['graph']; graph_nodes=set(graph.get('nodes',[]))
 if graph_nodes!=node_set:issues.append('runtime graph node set must equal the canonical node registry')
 for e in graph.get('edges',[]):
  if e.get('source') not in graph_nodes or e.get('target') not in graph_nodes:issues.append('runtime graph contains an unresolved edge endpoint')
  if e.get('edge_type') in VISUAL_EDGE_TYPES and e.get('runtime_executable'):issues.append('visual-only runtime graph edge is executable')
  if e.get('edge_type') in RUNTIME_EDGE_TYPES and not e.get('runtime_executable'):issues.append('runtime graph edge is not executable')
 profiles=payloads['profiles'].get('profiles',[]); reg_ids={payloads['nodes'].get('registry_id'),payloads['scenarios'].get('registry_id'),payloads['graph'].get('graph_id')}
 return {'outcome':'PASS' if not issues else 'FAIL','valid':not issues,'issues':issues,'counts':{'nodes':len(nodes),'proposed_nodes':sum(n.get('source_status')=='proposed_registry_slot' for n in nodes),'explicit_nodes':sum(n.get('source_status')=='canonical_explicit' for n in nodes),'materialized_scenarios':len(scenarios),'declared_scenarios':payloads['scenarios'].get('declared_scenario_count'),'graph_edges':len(graph.get('edges',[])),'profiles':len(profiles)},'registry_ids':sorted(reg_ids),'scenario_ids':sorted(ids)}
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);a=p.parse_args()
 try:r=validate_registry(a.root.resolve())
 except Exception as e:r={'outcome':'FAIL','valid':False,'issues':[str(e)]}
 print(json.dumps(r,indent=2,sort_keys=True));return 0 if r['valid'] else 1
if __name__=='__main__':raise SystemExit(main())
