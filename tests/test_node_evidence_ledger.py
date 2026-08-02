from __future__ import annotations
import importlib.util, json, tempfile, unittest
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
ROOT=Path(__file__).resolve().parents[1]
def module():
    p=ROOT/'tools/node_architect/node_evidence_ledger.py'; spec=importlib.util.spec_from_file_location('ledger',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
class TestNodeEvidenceLedger(unittest.TestCase):
    def setUp(self):
        self.m=module(); self.schema=json.loads((ROOT/'schemas/node-architect/node-runtime-evidence.schema.json').read_text())
    def ledger(self,root):
        return self.m.NodeEvidenceLedger(root=Path(root),task_id='SCRUM-263',run_id='run-1',node_id='repo_delivery.scoped-file-write',repository='nhatnguyenquang1838-coder/gwc',branch='feature/scrum-263-node-instruction-evidence-ledger',base_sha='a'*40,head_sha='b'*40,scope_hash='sha256:'+'c'*64,idempotency_key='scrum263-run1-write',occurred_at='2026-08-02T14:00:00Z')
    def test_complete_ledger_paths_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            l=self.ledger(tmp); records=[l.record_start({'status':'START'}),l.record_decision({'status':'ALLOW'}),l.record_result({'status':'PASS'}),l.record_readback({'status':'PASS'}),l.record_checkpoint({'status':'COMMITTED'}),l.record_next_route({'next_node':'repo_delivery.diff-readback'})]
            v=Draft202012Validator(self.schema,format_checker=FormatChecker())
            for r in records: self.assertEqual([],list(v.iter_errors(r)))
            self.assertTrue((Path(tmp)/'.gwc/tasks/SCRUM-263/node-runtime/run-1/repo_delivery.scoped-file-write/node-start.json').is_file())
            events=(Path(tmp)/'.gwc/tasks/SCRUM-263/node-runtime/run-1/runtime-events.jsonl').read_text().splitlines(); self.assertEqual(6,len(events)); self.assertTrue(all(json.loads(x)['event_digest'].startswith('sha256:') for x in events))
    def test_exact_replay_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            l=self.ledger(tmp); p={'status':'START'}; a=l.record_start(p); b=l.record_start(p); self.assertEqual(a,b); self.assertEqual(1,len(l.events_path.read_text().splitlines()))
    def test_conflicting_replay_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            l=self.ledger(tmp); l.record_start({'status':'START'})
            with self.assertRaises(self.m.EvidenceConflict): l.record_start({'status':'OTHER'})
if __name__=='__main__': unittest.main()
