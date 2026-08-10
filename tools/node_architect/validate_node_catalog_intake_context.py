#!/usr/bin/env python3
"""Validate the intake_context node family and runtime contract bindings."""
from __future__ import annotations
import argparse, importlib.util, json, re
from pathlib import Path
from typing import Any

EXPECTED_FAMILY="intake_context"
EXPECTED_COUNT=9
EXPECTED_GATE="G0_CONTEXT"
ALLOWED_AUTHORITY={"read_only","none"}
ALLOWED_NODE_TYPES={"actor","workflow","gate","tool","schema","state","projection","connector"}
ALLOWED_CANONICAL={"canonical","delivery_evidence","audit_projection","resume_hint"}
REQUIRED_KEYS={"node_id","node_type","title","canonical","authority_boundary","gates"}
SHA40=re.compile(r"^[0-9a-f]{40}$")
RUNTIME_CONTRACTS={
 "intake_context.intake-card-render":{"schema":"schemas/intake-card.schema.json","evaluator":"tools/node_architect/intake_card_render.py","entrypoint":"render_intake_card","artifact_type":"intake-card"},
 "intake_context.context-gap-escalation":{"schema":"schemas/context-gap-decision.schema.json","evaluator":"tools/node_architect/context_gap_escalation.py","entrypoint":"decide_context_gap_escalation","artifact_type":"context-gap-decision"},
 "intake_context.request-intake":{"schema":"schemas/intake-request.schema.json","evaluator":"tools/node_architect/request_intake.py","entrypoint":"render_request_intake","artifact_type":"intake-request"},
 "intake_context.source-resolution":{"schema":"schemas/source-resolution.schema.json","evaluator":"tools/node_architect/source_resolution.py","entrypoint":"render_source_resolution","artifact_type":"source-resolution"},
 "intake_context.protected-base-capture":{"schema":"schemas/protected-base-capture.schema.json","evaluator":"tools/node_architect/protected_base_capture.py","entrypoint":"render_protected_base_capture","artifact_type":"protected-base-capture"},
 "intake_context.repo-identity-check":{"schema":"schemas/repo-identity.schema.json","evaluator":"tools/node_architect/repo_identity_check.py","entrypoint":"render_repo_identity_check","artifact_type":"repo-identity"},
 "intake_context.risk-classification":{"schema":"schemas/risk-classification.schema.json","evaluator":"tools/node_architect/risk_classification.py","entrypoint":"render_risk_classification","artifact_type":"risk-profile"},
 "intake_context.files-read-scope":{"schema":"schemas/bounded-read-scope.schema.json","evaluator":"tools/node_architect/files_read_scope.py","entrypoint":"render_files_read_scope","artifact_type":"bounded-read-scope"},
}
TYPED={
 "intake_context.request-intake":{"intent","outcome","constraints","exclusions","entry_guards","reason_codes","source_resolution"},
 "intake_context.source-resolution":{"intent","outcome","constraints","exclusions","entry_guards","reason_codes"},
 "intake_context.repo-identity-check":{"intent","outcome","constraints","exclusions","entry_guards","reason_codes"},
 "intake_context.risk-classification":{"intent","outcome","constraints","exclusions","entry_guards","reason_codes","risk_profile"},
 "intake_context.files-read-scope":{"intent","outcome","constraints","exclusions","entry_guards","reason_codes"},
 "intake_context.files-write-scope":{"intent","outcome","constraints","exclusions","entry_guards","reason_codes"},
 "intake_context.protected-base-capture":{"protected_base_sha","evidence_source","readback_status","drift_state","reason_codes","captured_at"},
}
RISK_CODES={"RISK_PRODUCTION_OPERATION","RISK_SECRET_CHANGE","RISK_DESTRUCTIVE_OPERATION","RISK_MIGRATION","RISK_RELEASE_DEPLOYMENT","RISK_SCOPE_AMBIGUOUS","RISK_SOURCE_STALE","RISK_UNCLASSIFIED"}

def _repo_root()->Path: return Path(__file__).resolve().parents[2]
def _family_dir()->Path: return _repo_root()/"core/node-architect/node-catalog"/EXPECTED_FAMILY

def _load(path:Path)->dict[str,Any]:
 data=json.loads(path.read_text(encoding="utf-8"))
 if not isinstance(data,dict): raise ValueError("node file must contain object")
 return data

def _string_list(path:Path, name:str, value:Any)->list[str]:
 if value is None: return []
 if not isinstance(value,list) or not all(isinstance(x,str) for x in value): return [f"{path}: {name} must be a list of strings"]
 if len(value)!=len(set(value)): return [f"{path}: {name} must not contain duplicates"]
 return []

def _reason_codes(path:Path, value:Any)->list[str]:
 if value is None: return []
 if isinstance(value,str): return []
 if isinstance(value,dict) and all(isinstance(k,str) and isinstance(v,(str,int,float,bool,type(None))) for k,v in value.items()): return []
 return [f"{path}: reason_codes must be a string or object with primitive values"]

def _risk_profile(path:Path, value:Any)->list[str]:
 if not isinstance(value,dict): return [f"{path}: risk_profile must be a JSON object"]
 req={"risk_level","risk_flags","required_gate","approval_requirements","reason_codes","source_bindings","classified_at"}
 err=[]
 if missing:=sorted(req-set(value)): err.append(f"{path}: risk_profile missing required keys: {', '.join(missing)}")
 if value.get("risk_level") not in {"R0","R1","R2","R3"}: err.append(f"{path}: risk_profile.risk_level invalid")
 err+=_string_list(path,"risk_profile.risk_flags",value.get("risk_flags"))
 err+=_string_list(path,"risk_profile.approval_requirements",value.get("approval_requirements"))
 codes=value.get("reason_codes")
 if not isinstance(codes,list) or not codes or not set(codes).issubset(RISK_CODES): err.append(f"{path}: risk_profile.reason_codes unsupported")
 bindings=value.get("source_bindings")
 if not isinstance(bindings,dict): err.append(f"{path}: risk_profile.source_bindings must be an object")
 return err

def _validate_node(path:Path,node:dict[str,Any])->list[str]:
 err=[]; node_id=node.get("node_id")
 allowed=REQUIRED_KEYS|TYPED.get(node_id,set())|{"description"}
 if missing:=sorted(REQUIRED_KEYS-set(node)): err.append(f"{path}: missing required keys: {', '.join(missing)}")
 if extra:=sorted(set(node)-allowed): err.append(f"{path}: unexpected keys: {', '.join(extra)}")
 if not isinstance(node_id,str) or not node_id.startswith(EXPECTED_FAMILY+"."): err.append(f"{path}: node_id must start with {EXPECTED_FAMILY}.")
 if node.get("node_type") not in ALLOWED_NODE_TYPES: err.append(f"{path}: invalid node_type {node.get('node_type')!r}")
 if node.get("canonical") not in ALLOWED_CANONICAL: err.append(f"{path}: invalid canonical {node.get('canonical')!r}")
 if not isinstance(node.get("title"),str) or not node.get("title"," ").strip(): err.append(f"{path}: title must be a non-empty string")
 if node.get("authority_boundary") not in ALLOWED_AUTHORITY: err.append(f"{path}: intake_context nodes must be read-only/none authority")
 if node.get("gates") != [EXPECTED_GATE]: err.append(f"{path}: gates must be exactly ['{EXPECTED_GATE}']")
 for name in ("constraints","exclusions","entry_guards"): err+=_string_list(path,name,node.get(name))
 if "reason_codes" in node: err+=_reason_codes(path,node.get("reason_codes"))
 if node_id=="intake_context.protected-base-capture":
  if not isinstance(node.get("protected_base_sha"),str) or not SHA40.fullmatch(node.get("protected_base_sha","")): err.append(f"{path}: protected_base_sha must be a 40-character lowercase hex string")
  if node.get("readback_status") not in {"VERIFIED","MISMATCH","STALE","UNKNOWN"}: err.append(f"{path}: readback_status unsupported")
  if node.get("drift_state") not in {"NONE","STALE","DRIFTED"}: err.append(f"{path}: drift_state unsupported")
 if node_id=="intake_context.risk-classification":
  if not isinstance(node.get("reason_codes"),dict) or set(node.get("reason_codes",{}))!=RISK_CODES: err.append(f"{path}: reason_codes missing required risk keys")
  err+=_risk_profile(path,node.get("risk_profile"))
 return err

def validate_family(family_dir:Path)->list[str]:
 err=[]; files=sorted(family_dir.glob("*.node.json"))
 if len(files)!=EXPECTED_COUNT: err.append(f"{family_dir}: expected exactly {EXPECTED_COUNT} .node.json files, found {len(files)}")
 seen=set()
 for path in files:
  try: node=_load(path)
  except Exception as exc: err.append(f"{path}: failed to load JSON: {exc}"); continue
  if isinstance(node.get("node_id"),str):
   if node["node_id"] in seen: err.append(f"{path}: duplicate node_id {node['node_id']}")
   seen.add(node["node_id"])
  err+=_validate_node(path,node)
 return err

def validate_runtime_contracts(repo_root:Path)->list[str]:
 err=[]
 for node_id,c in sorted(RUNTIME_CONTRACTS.items()):
  schema_path=repo_root/c["schema"]; evaluator_path=repo_root/c["evaluator"]
  if not schema_path.is_file(): err.append(f"{node_id}: runtime schema missing: {c['schema']}")
  else:
   try:
    schema=json.loads(schema_path.read_text(encoding="utf-8"))
    from jsonschema import Draft202012Validator
    Draft202012Validator.check_schema(schema)
    artifact_type=schema.get("properties",{}).get("artifact_type",{}).get("const")
    if artifact_type!=c["artifact_type"]: err.append(f"{node_id}: runtime schema artifact_type must be {c['artifact_type']!r}, got {artifact_type!r}")
   except Exception as exc: err.append(f"{node_id}: runtime schema is invalid: {exc}")
  if not evaluator_path.is_file(): err.append(f"{node_id}: runtime evaluator missing: {c['evaluator']}")
  else:
   try:
    spec=importlib.util.spec_from_file_location(node_id.replace(".","_"), evaluator_path); module=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(module)
    if not callable(getattr(module,c["entrypoint"],None)): err.append(f"{node_id}: runtime evaluator missing callable {c['entrypoint']}")
   except Exception as exc: err.append(f"{node_id}: runtime evaluator import failed: {exc}")
 return err

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--family-dir",type=Path,default=_family_dir()); args=p.parse_args()
 errors=validate_family(args.family_dir)+validate_runtime_contracts(_repo_root())
 if errors:
  for e in errors: print("ERROR:",e)
  return 1
 print(f"PASS: {EXPECTED_FAMILY} node family has {EXPECTED_COUNT} valid nodes and {len(RUNTIME_CONTRACTS)} valid runtime contract binding(s)")
 return 0
if __name__=="__main__": raise SystemExit(main())
