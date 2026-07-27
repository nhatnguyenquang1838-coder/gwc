#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def issue(code,msg,loc='<root>'):
    return {'code':code,'message':msg,'location':loc}

def validate_run(r):
    out=[]
    if r.get('task_id')!='SCRUM-121': out.append(issue('TASK_MISMATCH','task_id must be SCRUM-121','task_id'))
    if r.get('pilot_id')!='PILOT-121-A': out.append(issue('PILOT_MISMATCH','pilot_id must be PILOT-121-A','pilot_id'))
    g6=r.get('g6') or {}
    if g6.get('applicable') is not False:
        out.append(issue('G6_REQUIRED','pilot must keep G6 not_applicable','g6.applicable'))
    for i,n in enumerate(r.get('nodes') or []):
        if not n.get('version') or str(n.get('version')).lower() in {'stale','latest','unbound'}:
            out.append(issue('STALE_ARTIFACT','node version must be fresh and bound',f'nodes[{i}].version'))
        allowed=set(n.get('allowed_actions') or [])
        attempted=set(n.get('attempted_actions') or [])
        if attempted and allowed and not attempted <= allowed:
            out.append(issue('BMAD_SCOPE_VIOLATION','attempted action outside allowed procedure scope',f'nodes[{i}].attempted_actions'))
    seen=set()
    for i,s in enumerate(r.get('side_effects') or []):
        key=s.get('idempotency_key')
        if not key: out.append(issue('DUPLICATE_SIDE_EFFECT','side effect needs idempotency key',f'side_effects[{i}].idempotency_key'))
        elif key in seen: out.append(issue('DUPLICATE_SIDE_EFFECT','duplicate side-effect idempotency key',f'side_effects[{i}].idempotency_key'))
        seen.add(key)
    replay=r.get('replay') or {}
    if replay.get('route_matches') is not True or replay.get('decision_matches') is not True:
        if not replay.get('live_state_divergence'):
            out.append(issue('REPLAY_DIVERGENCE','replay mismatch needs typed live-state divergence','replay'))
    for i,p in enumerate(r.get('projections') or []):
        if p.get('authority')!='projection' or p.get('grants_gate_authority') is True:
            out.append(issue('PROJECTION_AUTHORITY_LEAKAGE','projection cannot grant authority',f'projections[{i}]'))
    return out

def run_suite(root):
    expected={
        'rejected-production-action.json':'G6_REQUIRED',
        'rejected-duplicate-side-effect.json':'DUPLICATE_SIDE_EFFECT',
        'rejected-nondeterministic-replay.json':'REPLAY_DIVERGENCE',
        'rejected-stale-artifact.json':'STALE_ARTIFACT',
        'rejected-projection-authority-leakage.json':'PROJECTION_AUTHORITY_LEAKAGE',
        'rejected-bmad-scope-violation.json':'BMAD_SCOPE_VIOLATION',
    }
    cases=[]; problems=[]
    for p in sorted((root/'examples/integrations/e2e-pilot').glob('*.json')):
        issues=validate_run(json.loads(p.read_text()))
        codes={i['code'] for i in issues}
        need=expected.get(p.name)
        ok=(need in codes) if need else not issues
        cases.append({'file':str(p.relative_to(root)),'expected_failure':need,'codes':sorted(codes),'passed':ok})
        if not ok: problems.append(issue('VALIDATION_FAILED',f'{p.name} expectation failed',str(p)))
    return {'outcome':'PASS' if cases and not problems else 'FAIL','valid':bool(cases and not problems),'cases':cases,'issues':problems}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--json',action='store_true')
    a=ap.parse_args(); result=run_suite(Path(a.root))
    print(json.dumps(result,indent=2,sort_keys=True) if a.json else result['outcome'])
    return 0 if result['valid'] else 1
if __name__=='__main__': raise SystemExit(main())
