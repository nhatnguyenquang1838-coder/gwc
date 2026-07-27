#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from jsonschema import Draft202012Validator

def load(p): return json.loads(Path(p).read_text())
def validate(root: Path):
    issues=[]
    pairs=[('schemas/integrations/ua-host-request.schema.json','examples/integrations/ua-host/fresh-request.json'),('schemas/integrations/ua-snapshot.schema.json','examples/integrations/ua-host/fresh-snapshot.json'),('schemas/integrations/ua-host-result.schema.json','examples/integrations/ua-host/complete-result.json'),('schemas/integrations/ua-host-result.schema.json','examples/integrations/ua-host/stale-result.json'),('schemas/integrations/ua-host-result.schema.json','examples/integrations/ua-host/tool-unavailable-result.json')]
    for s,e in pairs:
        schema=load(root/s); inst=load(root/e)
        for err in Draft202012Validator(schema).iter_errors(inst): issues.append({'path':e,'message':err.message})
    snap=load(root/'examples/integrations/ua-host/fresh-snapshot.json')
    for out in snap['outputs']:
        if not out['path'].startswith('.ua/'): issues.append({'path':'outputs','message':'path escape'})
    return {'valid':not issues,'outcome':'PASS' if not issues else 'FAIL','issues':issues}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--json',action='store_true'); ns=ap.parse_args(); r=validate(Path(ns.root)); print(json.dumps(r,indent=2)); return 0 if r['valid'] else 1
if __name__=='__main__': raise SystemExit(main())
