from __future__ import annotations
import copy, importlib.util, json, sys, unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
def load(rel):
    p=ROOT/rel
    return json.loads(p.read_text()) if p.suffix=='.json' else yaml.safe_load(p.read_text())
def module():
    p=ROOT/'tools/node_architect/validate_node_instruction.py'; spec=importlib.util.spec_from_file_location('vin',p); m=importlib.util.module_from_spec(spec); sys.modules['vin']=m; spec.loader.exec_module(m); return m
class TestNodeInstructionContract(unittest.TestCase):
    def setUp(self):
        self.m=module(); self.schema=load('schemas/node-architect/node-instruction.schema.json')
        self.profile=load('core/node-architect/gate-node-route-profile.json'); self.registry=load('core/node-architect/node-registry.json')
        self.route=self.profile['routes'][1]; self.card=load(self.route['node_instruction_ref']); self.desc=load(self.route['node_descriptor_ref'])
        self.node=next(n for n in self.registry['nodes'] if n['id']==self.route['current_node'])
    def validate(self, card=None, mode='normal'):
        return self.m.validate_instruction(card=card or self.card,schema=self.schema,descriptor=self.desc,registry_node=self.node,route=self.route,active_gate='G2_EXECUTION',mode=mode)
    def test_missing_instruction_fails_closed(self):
        r=self.m.validate_instruction_path(instruction_path=ROOT/'missing.yaml',schema_path=ROOT/'schemas/node-architect/node-instruction.schema.json',descriptor_path=ROOT/self.route['node_descriptor_ref'],registry_path=ROOT/'core/node-architect/node-registry.json',route_profile_path=ROOT/'core/node-architect/gate-node-route-profile.json',active_gate='G2_EXECUTION',mode='normal',route_id=self.route['route_id'])
        self.assertEqual(r.reason_code,'NODE_INSTRUCTION_MISSING')
    def test_missing_evidence_contract_fails_closed(self):
        c=copy.deepcopy(self.card); c['evidence_required'].remove('node-readback'); self.assertIn('NODE_EVIDENCE_CONTRACT_MISSING',self.validate(c).reason_codes)
    def test_missing_log_contract_fails_closed(self):
        c=copy.deepcopy(self.card); c['logs_required'].remove('event_digest'); self.assertIn('NODE_LOG_CONTRACT_MISSING',self.validate(c).reason_codes)
    def test_missing_next_route_fails_closed(self):
        c=copy.deepcopy(self.card); c['next']['pass']['next_node']=None; self.assertIn('NODE_NEXT_ROUTE_MISSING',self.validate(c).reason_codes)
    def test_instruction_cannot_grant_authority(self):
        c=copy.deepcopy(self.card); c['authority_boundary']['merge_authority_granted']=True; self.assertIn('NODE_AUTHORITY_ESCALATION_ATTEMPT',self.validate(c).reason_codes)
    def test_modes_require_runtime(self):
        for mode in ('fastlane','e2e','hotfix','rescue'):
            with self.subTest(mode=mode): self.assertTrue(self.validate(mode=mode).valid)
    def test_mode_bypass_fails_closed(self):
        c=copy.deepcopy(self.card); c['mode_policy']['evidence_required']=False
        for mode in ('fastlane','e2e','hotfix','rescue'):
            with self.subTest(mode=mode): self.assertIn('MODE_BYPASSES_NODE_RUNTIME',self.validate(c,mode).reason_codes)
if __name__=='__main__': unittest.main()
