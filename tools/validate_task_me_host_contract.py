#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from jsonschema import Draft202012Validator
EXPECTED='sha256:ad349050bd2424ee45082657c3afab6a3245b4cbd8ed277d47fb896b16162cc7'
def load(p): return json.loads(Path(p).read_text())
def validate(root: Path):
    issues=[]
    pairs=[('schemas/integrations/task-me-host-request.schema.json','examples/integrations/task-me-host/complete-request.json'),('schemas/integrations/task-me-host-result.schema.json','examples/integrations/task-me-host/complete-result.json'),('schemas/integrations/task-me-host-result.schema.json','examples/integrations/task-me-host/partial-result.json'),('schemas/integrations/task-me-host-result.schema.json','examples/integrations/task-me-host/stale-ua-result.json'),('schemas/integrations/task-me-host-result.schema.json','examples/integrations/task-me-host/cyclic-dag-result.json'),('schemas/integrations/task-me-task-package.schema.json','examples/integrations/task-me-host/task-package.json')]
    for s,e in pairs:
        for err in Draft202012Validator(load(root/s)).iter_errors(load(root/e)): issues.append({'path':e,'message':err.message})
    binding=load(root/'.ua/analysis/SCRUM-118/accepted-snapshot-reference.json')
    if binding.get('source_contract_digest')!=EXPECTED: issues.append({'path':'binding','message':'SCRUM-117 digest mismatch'})
    package=load(root/'examples/integrations/task-me-host/task-package.json')
    if not package['output_folder'].startswith('.task-me/'): issues.append({'path':'task-package','message':'path escape'})
    return {'valid':not issues,'outcome':'PASS' if not issues else 'FAIL','issues':issues}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--json',action='store_true'); ns=ap.parse_args(); r=validate(Path(ns.root)); print(json.dumps(r,indent=2)); return 0 if r['valid'] else 1
if __name__=='__main__': raise SystemExit(main())
