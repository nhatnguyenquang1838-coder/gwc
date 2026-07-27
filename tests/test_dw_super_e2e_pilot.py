import importlib.util,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('v',ROOT/'tools/validate_dw_super_e2e_pilot.py')
v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)

def rec():
    return {"schema_version":"0.1","task_id":"SCRUM-121","pilot_id":"PILOT-121-A","g6":{"applicable":False},"nodes":[{"id":"bmad","provider":"bmad","version":"6.10.0","allowed_actions":["read"],"attempted_actions":["read"],"checkpoint_revision":1}],"side_effects":[{"type":"jira","idempotency_key":"x"}],"replay":{"route_matches":True,"decision_matches":True},"projections":[{"system":"jira","authority":"projection","grants_gate_authority":False}]}
class T(unittest.TestCase):
    def codes(self,x): return {i['code'] for i in x}
    def test_positive(self): self.assertEqual([],v.validate_run(rec()))
    def test_duplicate(self): r=rec(); r['side_effects'].append({'type':'jira','idempotency_key':'x'}); self.assertIn('DUPLICATE_SIDE_EFFECT',self.codes(v.validate_run(r)))
    def test_g6(self): r=rec(); r['g6']={'applicable':True,'action':'deploy'}; self.assertIn('G6_REQUIRED',self.codes(v.validate_run(r)))
    def test_scope_violation(self): r=rec(); r['nodes'][0]['attempted_actions']=['read','write_main']; self.assertIn('BMAD_SCOPE_VIOLATION',self.codes(v.validate_run(r)))
    def test_projection_leakage(self): r=rec(); r['projections'][0]['grants_gate_authority']=True; self.assertIn('PROJECTION_AUTHORITY_LEAKAGE',self.codes(v.validate_run(r)))
    def test_suite(self): self.assertTrue(v.run_suite(ROOT)['valid'])
if __name__=='__main__': unittest.main()
