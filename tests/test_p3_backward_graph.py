import unittest
from tools.p3_backward_graph import CompileError,append_scenario_decision,compile_backward_graph,decide_scenario,enumerate_routes,evaluate_guard
class BackwardCompilerTests(unittest.TestCase):
 def test_deterministic_dependency_closure(self):
  nodes=[{'id':'green','dependencies':['b','a']},{'id':'a','dependencies':['read']},{'id':'b','dependencies':[]},{'id':'read','dependencies':[]},{'id':'safe','dependencies':[]}]
  self.assertEqual(compile_backward_graph(nodes,'green','safe')['selected_nodes'],['read','a','b','green'])
 def test_cycle_is_rejected(self):
  with self.assertRaisesRegex(CompileError,'CYCLE_UNSAFE'):compile_backward_graph([{'id':'green','dependencies':['a']},{'id':'a','dependencies':['green']},{'id':'safe'}],'green','safe')
class GuardAndScenarioTests(unittest.TestCase):
 def test_guard_equality_is_type_strict(self):self.assertFalse(evaluate_guard({'type':'equals','field':'value','value':1},{'value':True}).passed)
 def test_reference_comparison_is_supported(self):self.assertTrue(evaluate_guard({'type':'equals','field':'head','value':'expected'},{'head':'x','expected':'x'}).passed)
 def test_decision_digest_is_deterministic_and_history_immutable(self):
  s={'id':'ci-failure','version':'1.0.0','activation_facts':['ci_status'],'guards':[{'id':'ci-ok','type':'equals','field':'ci_status','value':'success','conditional':False,'reason':'CI_FAILED'}],'route_nodes':['start','green'],'edges':[{'source':'start','target':'green','edge_type':'runtime','runtime_executable':True}],'route_policy':{'start_node':'start','green_targets':['green'],'max_depth':8}}
  a=decide_scenario(s,{'ci_status':'failure'});b=decide_scenario(s,{'ci_status':'failure'});self.assertEqual(a['decision_id'],b['decision_id']);self.assertEqual(a['classification'],'BLOCKED')
  h=[];append_scenario_decision(h,a);append_scenario_decision(h,b);self.assertEqual(len(h),1)
  bad=dict(a);bad['classification']='VALID_AUTO'
  with self.assertRaisesRegex(CompileError,'IMMUTABILITY_VIOLATION'):append_scenario_decision(h,bad)
if __name__=='__main__':unittest.main()
