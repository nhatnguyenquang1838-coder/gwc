from __future__ import annotations
import json,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; VALIDATOR=ROOT/"tools/node_architect/validate_runtime_registry.py"
class RuntimeRegistryValidationTests(unittest.TestCase):
 def test_canonical_registries_pass_cross_registry_validation(self):
  result=subprocess.run([sys.executable,str(VALIDATOR),"--root",str(ROOT)],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False);self.assertEqual(result.returncode,0,result.stdout+result.stderr);report=json.loads(result.stdout);self.assertEqual(report["outcome"],"PASS");self.assertEqual(report["counts"]["nodes"],81);self.assertEqual(report["counts"]["declared_scenarios"],116);self.assertEqual(report["counts"]["materialized_scenarios"],14)
 def test_scenario_count_is_not_graph_edge_count(self):
  s=json.loads((ROOT/"core/node-architect/scenario-registry.json").read_text());g=json.loads((ROOT/"core/node-architect/runtime-graph-registry.json").read_text());self.assertEqual(s["materialized_scenario_count"],14);self.assertNotEqual(14,len(g["edges"]))
if __name__=="__main__":unittest.main()
