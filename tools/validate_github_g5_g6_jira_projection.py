#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
HEX=set("0123456789abcdef")
def issue(c,m,l="<root>"): return {"code":c,"message":m,"location":l}
def is_sha(v): return isinstance(v,str) and len(v)==40 and set(v)<=HEX
def validate_jira_projection(r,embedded=False):
    out=[]
    if r.get("authority")!="projection": out.append(issue("PROJECTION_AUTHORITY_LEAKAGE","projection authority must stay projection","authority"))
    if r.get("grants_gate_authority") is True: out.append(issue("PROJECTION_AUTHORITY_LEAKAGE","projection cannot grant gate authority","grants_gate_authority"))
    if not embedded and r.get("status")=="FAILED" and not r.get("failure_code"): out.append(issue("PROJECTION_WRITE_FAILED","failed projection needs failure_code","failure_code"))
    return out
def validate_g5_verification(r):
    out=[]
    if r.get("g6_excluded") is not True: out.append(issue("G6_REQUIRED","G5 must exclude G6 operations","g6_excluded"))
    if any(t in str(r.get("action_class","verification")).lower() for t in ("deploy","release","production","secret","migration","destructive","database")): out.append(issue("G6_REQUIRED","operation requires G6","action_class"))
    if r.get("merge_sha")!=r.get("current_main_sha"): out.append(issue("MERGE_SHA_MISMATCH","merge SHA must match current main SHA","current_main_sha"))
    return out
def validate_github_evidence(r):
    out=[]; exp=r.get("expected",{}) or {}; obs=r.get("observed",{}) or {}; typ=r.get("evidence_type")
    if typ=="pr_head" and exp.get("head_sha")!=obs.get("head_sha"): out.append(issue("PR_HEAD_DRIFT","PR head changed","observed.head_sha"))
    elif typ in ("post_merge","main"):
        if exp.get("main_sha")!=obs.get("main_sha"): out.append(issue("STALE_MAIN_SHA","main SHA changed","observed.main_sha"))
        if exp.get("merge_sha") is not None and exp.get("merge_sha")!=obs.get("merge_sha"): out.append(issue("MERGE_SHA_MISMATCH","merge SHA mismatch","observed.merge_sha"))
    else: out.append(issue("REPOSITORY_EVIDENCE_MISSING","unsupported evidence_type","evidence_type"))
    for side_name,side in (("expected",exp),("observed",obs)):
        for key,val in side.items():
            if key.endswith("sha") and not is_sha(val): out.append(issue("REPOSITORY_EVIDENCE_MISSING",f"{side_name}.{key} must be 40-char sha",f"{side_name}.{key}"))
    runs=(r.get("ci",{}) or {}).get("workflow_runs") or []
    if (r.get("ci",{}) or {}).get("required",True) and not runs: out.append(issue("CI_UNAVAILABLE_AT_CHECK","CI evidence absent","ci.workflow_runs"))
    for i,run in enumerate(runs):
        if run.get("status")!="completed" or run.get("conclusion")!="success": out.append(issue("VALIDATION_FAILED","workflow run failed",f"ci.workflow_runs[{i}]"))
        for j,job in enumerate(run.get("jobs",[]) or []):
            if job.get("status")!="completed" or job.get("conclusion")!="success": out.append(issue("VALIDATION_FAILED","workflow job failed",f"ci.workflow_runs[{i}].jobs[{j}]"))
    out.extend(validate_jira_projection(r.get("projection") or {},embedded=True) if r.get("projection") else [])
    return out
def validate_any(r):
    if "evidence_type" in r: return validate_github_evidence(r)
    if "g6_excluded" in r: return validate_g5_verification(r)
    return validate_jira_projection(r)
def run_suite(root):
    exp={"rejected-pr-head-drift.json":"PR_HEAD_DRIFT","rejected-ci-unavailable.json":"CI_UNAVAILABLE_AT_CHECK","rejected-projection-authority-leakage.json":"PROJECTION_AUTHORITY_LEAKAGE"}; issues=[]; cases=[]
    for p in sorted((root/"examples/integrations/github-g5-g6-jira").glob("*.json")):
        got=validate_any(json.loads(p.read_text())); codes={i["code"] for i in got}; need=exp.get(p.name); ok=(need in codes) if need else not got
        if not ok: issues.append(issue("VALIDATION_FAILED",f"{p.name} expectation failed",str(p)))
        cases.append({"file":str(p.relative_to(root)),"expected_failure":need,"issues":got,"passed":ok})
    return {"outcome":"PASS" if cases and not issues else "FAIL","valid":bool(cases and not issues),"cases":cases,"issues":issues}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="."); ap.add_argument("--json",action="store_true"); a=ap.parse_args(); r=run_suite(Path(a.root)); print(json.dumps(r,indent=2,sort_keys=True) if a.json else r["outcome"]); return 0 if r["valid"] else 1
if __name__=="__main__": raise SystemExit(main())
