from __future__ import annotations
import copy, importlib.util, json, tempfile, unittest
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
def load(path): return json.loads((ROOT/path).read_text())
def module():
    path=ROOT/'tools/node_architect/resolve_gate_node_route.py'; spec=importlib.util.spec_from_file_location('resolver263',path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def context(action='repository_write',mode='normal'):
    envelope={'task_id':'SCRUM-263','authority_gate':'G2_EXECUTION','repository':'nhatnguyenquang1838-coder/gwc','base_sha':'a'*40,'working_branch':'feature/scrum-263-node-instruction-evidence-ledger','scope_hash':'sha256:'+'b'*64}
    loaded={'g0_context':{'status':'READY'},'g1_decision':{'status':'PASS'},'g2_envelope':envelope,'approval_receipt':{'status':'VALID'},'task_claim':{'agent':'ChatGPT'},'base_sha_readback':{'sha':envelope['base_sha']}}
    if action in {'post_write_readback','resolve_gate_transition'}: loaded['write_result']={'status':'success'}
    if action=='resolve_gate_transition': loaded['diff_readback']={'status':'PASS'}
    return {'task_id':'SCRUM-263','gate':'G2_EXECUTION','requested_action':action,'workflow_mode':mode,'repository':envelope['repository'],'base_sha':envelope['base_sha'],'working_branch':envelope['working_branch'],'scope_hash':envelope['scope_hash'],'expected_profile_revision':'scrum-263-20260802-r1','expected_graph_revision':'scrum-104-20260726','available_connectors':['GitHub.compare_commits'],'context':loaded}
class TestGateNodeRouteResolution(unittest.TestCase):
    def setUp(self):
        self.mod=module(); self.profile=load('core/node-architect/gate-node-route-profile.json'); self.nodes=load('core/node-architect/node-registry.json'); self.graph=load('core/node-architect/runtime-graph-registry.json'); self.decision_schema=load('schemas/node-architect/gate-node-route-decision.schema.json'); self.profile_schema=load('schemas/node-architect/gate-node-route-profile.schema.json')
    def resolve(self,ctx=None,profile=None,nodes=None,graph=None,root=ROOT): return self.mod.resolve_gate_node_route(profile=profile or self.profile,node_registry=nodes or self.nodes,graph_registry=graph or self.graph,context=ctx or context(),root=root)
    def test_profile_schema(self): Draft202012Validator(self.profile_schema).validate(self.profile)
    def test_g2_write_instruction_runtime(self):
        r=self.resolve(); self.assertEqual('ROUTE_SELECTED',r['outcome']); self.assertEqual('repo_delivery.scoped-file-write',r['current_node']); self.assertTrue(r['instruction_validated']); self.assertTrue(r['evidence_contract_valid']); self.assertTrue(r['log_contract_valid']); self.assertTrue(r['next_route_contract_valid']); self.assertTrue(r['mode_runtime_required']); self.assertFalse(r['authority_granted']); Draft202012Validator(self.decision_schema).validate(r)
    def test_g2_full_vertical_route(self):
        r1=self.resolve(context('resolve_execution_node')); self.assertEqual('repo_delivery.scoped-file-write',r1['next_node'])
        r2=self.resolve(context('repository_write')); self.assertEqual('repo_delivery.diff-readback',r2['next_node'])
        r3=self.resolve(context('post_write_readback')); self.assertEqual('gate_authority.gate-transition-decision',r3['next_node'])
        r4=self.resolve(context('resolve_gate_transition')); self.assertEqual('G3_PR',r4['next_gate']); self.assertFalse(r4['pr_authority_granted'])
    def test_missing_instruction_fails_closed(self):
        p=copy.deepcopy(self.profile); p['routes'][1]['node_instruction_ref']='missing.yaml'; self.assertEqual('NODE_INSTRUCTION_MISSING',self.resolve(profile=p)['reason_code'])
    def test_empty_context_is_not_loaded(self):
        c=context(); c['context']['approval_receipt']={}; self.assertEqual('NODE_CONTEXT_NOT_LOADED',self.resolve(c)['reason_code'])
    def test_missing_context_fails_closed(self):
        c=context(); del c['context']['task_claim']; self.assertEqual('NODE_CONTEXT_NOT_LOADED',self.resolve(c)['reason_code'])
    def test_invalid_authority_readback_fails(self):
        c=context(); c['context']['approval_receipt']={'status':'EXPIRED'}; self.assertEqual('GATE_NODE_BINDING_MISMATCH',self.resolve(c)['reason_code'])
    def test_modes_still_route_through_runtime(self):
        for mode in ('fastlane','e2e','hotfix','rescue'):
            with self.subTest(mode=mode): self.assertTrue(self.resolve(context(mode=mode))['instruction_validated'])
    def test_missing_route_fails_closed(self): self.assertEqual('NODE_ROUTE_MISSING',self.resolve(context('undefined'))['reason_code'])
    def test_ambiguous_route_fails_closed(self):
        p=copy.deepcopy(self.profile); p['routes'].append(copy.deepcopy(p['routes'][1])); self.assertEqual('NODE_ROUTE_AMBIGUOUS',self.resolve(profile=p)['reason_code'])
    def test_maturity_and_implementation_fail_closed(self):
        p=copy.deepcopy(self.profile); p['routes'][1]['minimum_maturity']='stable'; self.assertEqual('NODE_NOT_EXECUTABLE_AT_MATURITY',self.resolve(profile=p)['reason_code'])
        p=copy.deepcopy(self.profile); p['routes'][1]['implementation']['ref']='missing.py:run'; self.assertEqual('NODE_IMPLEMENTATION_UNAVAILABLE',self.resolve(profile=p)['reason_code'])
    def test_implementation_check_does_not_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'danger.py').write_text('raise RuntimeError("no")\n\ndef run():\n return True\n'); self.assertTrue(self.mod._implementation_available(root,{'kind':'python','ref':'danger.py:run'},{}))
    def test_digest_deterministic(self): self.assertEqual(self.resolve()['decision_digest'],self.resolve()['decision_digest'])
if __name__=='__main__': unittest.main()
