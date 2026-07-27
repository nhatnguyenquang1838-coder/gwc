#!/usr/bin/env python3
"""Validate the SCRUM-119 BMAD procedure-adapter contract."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "integration"
CONTRACT = ROOT / "core" / "integration" / "bmad-procedure-adapter-contract.json"
EXAMPLES = ROOT / "core" / "integration" / "examples" / "bmad-procedure-adapter-examples.json"
REQUIRED_PROCEDURES = {"architecture-analysis","story-preparation","tdd-implementation","code-review","release-readiness"}
FORBIDDEN_ACTIONS = {"approve_g2","approve_g4","approve_g5","approve_g6","mutate_gwc_state","broaden_scope","merge","deploy","release","production_operation","write_projection","change_credentials","run_migration"}

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def validate_instance(instance, schema_name):
    schema_path = SCHEMA_DIR / schema_name
    schema = load(schema_path)
    store = {}
    for candidate in SCHEMA_DIR.glob("bmad-*.schema.json"):
        loaded = load(candidate)
        store[candidate.as_uri()] = loaded
        if "$id" in loaded:
            store[loaded["$id"]] = loaded
    resolver = RefResolver(base_uri=schema_path.as_uri(), referrer=schema, store=store)
    errors = sorted(Draft202012Validator(schema, resolver=resolver, format_checker=Draft202012Validator.FORMAT_CHECKER).iter_errors(instance), key=lambda e:list(e.path))
    return [f"{schema_name}:{'/'.join(map(str,e.path))}: {e.message}" for e in errors]

def validate(root: Path = ROOT):
    failures=[]; checks=[]
    contract=load(root/CONTRACT.relative_to(ROOT)); examples_doc=load(root/EXAMPLES.relative_to(ROOT))
    registry=contract["registry"]
    e=validate_instance(registry,"bmad-procedure-registry.schema.json")
    checks.append({"name":"registry-schema","status":"PASS" if not e else "FAIL"}); failures.extend(e)
    ids={p["id"] for p in registry["procedures"]}
    if ids != REQUIRED_PROCEDURES: failures.append(f"procedure set mismatch: {sorted(ids)}")
    if contract["authority"]["canonical_gate_owner"] != "gwc": failures.append("GWC must remain canonical gate owner")
    if set(contract["authority"]["cannot_approve"]) != {"G2","G4","G5","G6"}: failures.append("gate denial set mismatch")
    if ".gwc/**" not in contract["authority"]["cannot_write_paths"]: failures.append(".gwc denial missing")
    if registry["provider"]["state"] == "ready-unpublished" and not registry["provider"].get("source_commit"): failures.append("ready-unpublished provider must be pinned")
    seen_keys=set()
    for ex in examples_doc["examples"]:
        if "request" not in ex: continue
        request=ex["request"]; result=ex["result"]
        re=validate_instance(request,"bmad-procedure-request.schema.json")
        rr=validate_instance(result,"bmad-procedure-result.schema.json")
        if ex["expected"] == "ACCEPT": failures.extend(re); failures.extend(rr)
        denied=set(request["permission"]["denied_actions"])
        if not FORBIDDEN_ACTIONS.issubset(denied): failures.append(f"{ex['id']}: forbidden action coverage incomplete")
        paths=request["permission"]["allowed_paths"]
        violation=any(p == ".gwc/**" or p.startswith(".gwc/") for p in paths + request["expected_outputs"])
        if ex["expected"] == "REJECT":
            if not violation: failures.append(f"{ex['id']}: rejection example is not a real path violation")
            if result.get("failure_code") != "SCOPE_VIOLATION" or result["changed_paths"]: failures.append(f"{ex['id']}: scope violation must reject before side effects")
        if result["recommendation"]["scope_change_required"] and result["recommendation"]["type"] != "PROPOSE_SCOPE_CHANGE": failures.append(f"{ex['id']}: scope change must remain proposal")
        if result["provenance"]["procedure_id"] != request["procedure"]["id"] or result["provenance"]["procedure_version"] != request["procedure"]["version"]: failures.append(f"{ex['id']}: result provenance procedure binding mismatch")
        key=request["idempotency_key"]
        if key in seen_keys: failures.append(f"duplicate key in primary examples: {key}")
        seen_keys.add(key)
    duplicate=next(x for x in examples_doc["examples"] if x["id"]=="duplicate-idempotency")
    if duplicate["side_effects_repeated"] or duplicate["failure_code"]!="DUPLICATE_IDEMPOTENCY_KEY": failures.append("duplicate idempotency behavior invalid")
    checks.append({"name":"authority-boundaries","status":"PASS" if not failures else "FAIL"})
    return {"task_id":"SCRUM-119","status":"PASS" if not failures else "FAIL","checks":checks,"failures":failures}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--json",action="store_true"); args=parser.parse_args()
    report=validate()
    print(json.dumps(report,indent=2) if args.json else f"BMAD procedure adapter validation: {report['status']}")
    return 0 if report["status"]=="PASS" else 1
if __name__=="__main__": raise SystemExit(main())
