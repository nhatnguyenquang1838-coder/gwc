import unittest
from tools.node_architect.viewer.registry_adapter import build_cytoscape_elements,build_scenario_decision_elements
class V3ScenarioAdapterTests(unittest.TestCase):
 def test_scenario_overlay_edges_are_non_executable(self):
  d={'decision_id':'sha256:abc','scenario_id':'ci-failure','scenario_version':'1.0.0','classification':'BLOCKED','graph_revision':'sha256:g','candidate_routes':[{'rank':1,'class':'BLOCKED','path':['a','b']}],'selected_route':{'rank':1,'class':'BLOCKED','path':['a','b']}}
  overlay=build_scenario_decision_elements(d);self.assertTrue(any('selected-route' in n['classes'] for n in overlay['nodes']));self.assertTrue(all(not e['data']['runtime_executable'] for e in overlay['edges']))
 def test_registry_adapter_accepts_scenario_decision(self):
  b={'nodes':{'nodes':[{'id':'a','family':'x','maturity':'candidate','source_status':'proposed_registry_slot','provenance':{}}]},'graph':{'edges':[]}}
  d={'decision_id':'sha256:abc','scenario_id':'x','scenario_version':'1.0.0','classification':'CONDITIONAL','candidate_routes':[],'selected_route':None}
  x=build_cytoscape_elements(b,scenario_decision=d);self.assertTrue(any(n['data'].get('kind')=='scenario' for n in x['nodes']))
if __name__=='__main__':unittest.main()
