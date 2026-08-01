import json, unittest
from pathlib import Path
from jsonschema import Draft202012Validator
from tools.node_architect.checkpoint_store import empty_store
from tools.node_architect.ci_evidence_capture import *
from tools.node_architect.client_runtime import run_client_runtime, VERTICAL_SLICE_ROUTE
HEAD='a'*40; OTHER='b'*40; SCOPE='sha256:'+'c'*64

def base(**overrides):
    p={'task_id':'SCRUM-214','run_id':'run-214','repository':'nhatnguyenquang1838-coder/gwc','branch':'codex/scrum-214','base_sha':HEAD,'head_sha':HEAD,'scope_hash':SCOPE,'graph_revision':'graph-v1','idempotency_key':'SCRUM-214:run-214:ci','provider_payload':{'workflow_runs':[{'id':1,'name':'Validate instructions','head_sha':HEAD,'status':'completed','conclusion':'success','html_url':'https://example.invalid/run/1'}]}}
    p.update(overrides); return p
class CiEvidenceCaptureM5Tests(unittest.TestCase):
    def validate_schema(self,result):
        schema=json.loads(Path('schemas/ci-evidence-capture-decision.schema.json').read_text()); Draft202012Validator.check_schema(schema); Draft202012Validator(schema).validate(result)
    def test_terminal_success(self):
        r=capture_ci_evidence(base(),observed_at='2026-08-01T19:00:00Z'); self.assertEqual((r['status'],r['reason_code']),('PASS','CI_SUCCESS')); self.validate_schema(r)
    def test_terminal_failure_and_cancelled(self):
        for conclusion,reason in [('failure','CI_FAILURE'),('cancelled','CI_CANCELLED')]:
            p=base(idempotency_key='x-'+conclusion); p['provider_payload']['workflow_runs'][0]['conclusion']=conclusion
            r=capture_ci_evidence(p,observed_at='2026-08-01T19:00:00Z'); self.assertEqual((r['status'],r['reason_code']),('BLOCKED',reason)); self.validate_schema(r)
    def test_pending_checkpoint_then_replay_without_duplicate(self):
        p=base(); p['provider_payload']['workflow_runs'][0].update(status='in_progress',conclusion=None); store=empty_store(); cache={}
        first=capture_ci_evidence(p,checkpoint_store=store,replay_cache=cache,observed_at='2026-08-01T19:00:00Z'); second=capture_ci_evidence(p,checkpoint_store=store,replay_cache=cache,observed_at='2026-08-01T19:05:00Z')
        self.assertEqual(first['reason_code'],'CI_PENDING'); self.assertEqual(first['evidence_digest'],second['evidence_digest']); self.assertTrue(second['replayed']); self.assertEqual(store['revision'],1); self.assertEqual(len(store['events']),1); self.validate_schema(first); self.validate_schema(second)
    def test_empty_unavailable_and_timeout(self):
        for timed_out,reason in [(False,'CI_UNAVAILABLE_AT_CHECK'),(True,'CI_TIMEOUT')]:
            store=empty_store(); r=capture_ci_evidence(base(provider_payload={},timed_out=timed_out,idempotency_key='empty-'+str(timed_out)),checkpoint_store=store,observed_at='2026-08-01T19:00:00Z')
            self.assertEqual((r['status'],r['reason_code']),('WAIT',reason)); self.assertEqual(store['revision'],1); self.validate_schema(r)
    def test_head_drift_and_sha_mismatch(self):
        stale=capture_ci_evidence(base(prior_evidence={'head_sha':OTHER}),observed_at='2026-08-01T19:00:00Z'); self.assertEqual(stale['reason_code'],'STALE_HEAD')
        p=base(idempotency_key='mismatch'); p['provider_payload']['workflow_runs'][0]['head_sha']=OTHER
        mismatch=capture_ci_evidence(p,observed_at='2026-08-01T19:00:00Z'); self.assertEqual(mismatch['reason_code'],'CI_SHA_MISMATCH'); self.validate_schema(stale); self.validate_schema(mismatch)
    def test_crash_after_checkpoint_replays_from_store(self):
        p=base(); p['provider_payload']['workflow_runs'][0].update(status='in_progress',conclusion=None); store=empty_store()
        with self.assertRaisesRegex(RuntimeError,'SIMULATED_CRASH'):
            capture_ci_evidence(p,checkpoint_store=store,observed_at='2026-08-01T19:00:00Z',crash_after_checkpoint=True)
        replay=capture_ci_evidence(p,checkpoint_store=store,observed_at='2026-08-01T19:05:00Z'); self.assertTrue(replay['replayed']); self.assertEqual(store['revision'],1); self.assertEqual(len(store['events']),1); self.validate_schema(replay)
    def test_pending_and_timeout_readback_reconcile_to_success(self):
        for timed_out,initial_reason in [(False,'CI_PENDING'),(True,'CI_TIMEOUT')]:
            p=base(idempotency_key='reconcile-'+str(timed_out)); p['provider_payload']['workflow_runs'][0].update(status='in_progress',conclusion=None); p['timed_out']=timed_out
            store=empty_store(); cache={}; first=capture_ci_evidence(p,checkpoint_store=store,replay_cache=cache,observed_at='2026-08-01T19:00:00Z')
            p['provider_payload']['workflow_runs'][0].update(status='completed',conclusion='success'); p['timed_out']=False
            second=capture_ci_evidence(p,checkpoint_store=store,replay_cache=cache,observed_at='2026-08-01T19:05:00Z')
            self.assertEqual((first['status'],first['reason_code']),('WAIT',initial_reason)); self.assertEqual((second['status'],second['reason_code']),('PASS','CI_SUCCESS')); self.assertFalse(second['replayed']); self.assertEqual(store['revision'],1); self.validate_schema(second)
    def test_duplicate_identity_conflict_fails_closed(self):
        cache={}; first=capture_ci_evidence(base(),replay_cache=cache,observed_at='2026-08-01T19:00:00Z'); p=base(head_sha=OTHER)
        second=capture_ci_evidence(p,replay_cache=cache,observed_at='2026-08-01T19:01:00Z'); self.assertEqual(first['reason_code'],'CI_SUCCESS'); self.assertEqual(second['reason_code'],'CI_FAILURE'); self.assertEqual(second['detail_code'],'IDEMPOTENCY_CONFLICT'); self.validate_schema(second)
    def test_client_runtime_uses_handler_and_fails_closed(self):
        req={'task_id':'SCRUM-214','repository':'nhatnguyenquang1838-coder/gwc','protected_base_sha':HEAD,'scenario_id':'client-runtime-node-architect-vertical-slice','route_intent':'client-runtime-node-architect-vertical-slice','route_nodes':list(VERTICAL_SLICE_ROUTE),'evidence':{'ci':{'head_sha':HEAD,'branch':'codex/scrum-214','scope_hash':SCOPE,'graph_revision':'graph-v1','provider_payload':{}}}}
        r=run_client_runtime(req); self.assertEqual(r.status,'BLOCKED'); self.assertEqual(r.terminal_code,'CI_UNAVAILABLE_AT_CHECK'); self.assertEqual(r.blocked_node,'validation_quality.ci-evidence-capture')
if __name__=='__main__': unittest.main()
