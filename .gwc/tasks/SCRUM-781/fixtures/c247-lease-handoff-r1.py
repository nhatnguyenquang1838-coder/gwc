"""Standalone sandbox delivery-runtime candidate, NOT native CF/load qualification."""
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

source, directory = map(lambda s: Path(s).resolve(), sys.argv[1:3])
scratch = (Path.home() / '.hermes/cache/scratch').resolve()
assert directory.is_relative_to(scratch) and not directory.exists()
directory.mkdir(parents=True)
raw = source.read_bytes()
spec = importlib.util.spec_from_file_location('isolated_delivery_runtime', source)
assert spec is not None and spec.loader is not None
module: Any = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
clock = [1000.0]
module._now = lambda: clock[0]
path = directory / 'outbox.sqlite'
record = dict(projection_target='external-audit-projection',
              event_source='gwc.node-architect.external-audit-projection.v1.0',
              event_id='sandbox-controlled-handoff', canonical_state_digest='sha256:'+'a'*64,
              event_payload_digest='sha256:'+'b'*64, destination_policy_digest='sha256:'+'c'*64,
              destination_id='sandbox-no-network', delivery_generation=1)
key = {k: record[k] for k in ('projection_target','event_source','event_id','canonical_state_digest','delivery_generation')}
module.init_store(path)
module.enqueue(path, **record)
module.acquire_lease(path, **key, worker_id='sandbox-worker-A', lease_ttl_s=1)
def state():
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        return dict(db.execute('SELECT * FROM delivery_outbox').fetchone())
trace = []
verify = module._verify_lease
def handoff(*args, **kwargs):
    row = verify(*args, **kwargs)
    trace.append({'event':'A_checked_lease','state':state()})
    clock[0] = 1002.0
    module.acquire_lease(path, **key, worker_id='sandbox-worker-B', lease_ttl_s=60)
    trace.append({'event':'B_reclaimed_after_A_check','state':state()})
    return row
module._verify_lease = handoff
error = None
try:
    module.transition(path, **key, worker_id='sandbox-worker-A', to_state=module.ACK_CONFIRMED)
except module.OutboxConflict as exc:
    error = str(exc)
final = state()
passed = error == module.OUTBOX_LEASE_LOST and final['lease_holder'] == 'sandbox-worker-B' and final['state'] == module.IN_FLIGHT
result = {'evidence_class':'SANDBOX_DELIVERY_RUNTIME_CANDIDATE_NOT_NATIVE_CF_QUALIFICATION',
          'source_sha256':hashlib.sha256(raw).hexdigest(), 'scenario':'lease-handoff-between-check-and-update',
          'clock_class':'DETERMINISTIC_SANDBOX_CLOCK', 'trace':trace, 'final_state':final,
          'stale_worker_error':error, 'expected':'stale A refused; current B lease and IN_FLIGHT state preserved',
          'contract_satisfied':passed, 'native_load_proof':False, 'original_dwo_failure_not_reproduced':True,
          'authority_granted':False, 'external_network_calls':0}
encoded = json.dumps(result, sort_keys=True, indent=2)
(directory/'observation.json').write_text(encoded+'\n')
print(encoded)
sys.exit(0 if passed else 1)
