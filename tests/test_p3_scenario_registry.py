import json,unittest
from pathlib import Path
from jsonschema import Draft202012Validator,RefResolver
ROOT=Path(__file__).resolve().parents[1]
class ScenarioRegistryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.registry=json.loads((ROOT/'core/node-architect/scenario-registry.json').read_text());cls.contract=json.loads((ROOT/'schemas/runtime/scenario-contract.schema.json').read_text());cls.schema=json.loads((ROOT/'schemas/runtime/scenario-registry.schema.json').read_text())
 def test_exact_initial_set_and_category_coverage(self):
  self.assertEqual(self.registry['declared_scenario_count'],116);self.assertEqual(self.registry['materialized_scenario_count'],14);self.assertEqual(len(self.registry['scenarios']),14);self.assertEqual(len({s['id'] for s in self.registry['scenarios']}),14)
  expected={'missing-context','ambiguity','baseline-drift','scope-drift','ambiguous-write-outcome','ci-pending','ci-failure','ci-sha-mismatch','stale-review','approval-expiry','observability-gap','partial-deployment','production-partial-success','blocked-authority'}
  self.assertEqual({s['category'] for s in self.registry['scenarios']},expected)
 def test_schema_and_projection_safety(self):
  resolver=RefResolver(self.schema['$id'],self.schema,{self.contract['$id']:self.contract,'scenario-contract.schema.json':self.contract})
  errors=list(Draft202012Validator(self.schema,resolver=resolver).iter_errors(self.registry));self.assertEqual(errors,[],[e.message for e in errors])
  for s in self.registry['scenarios']:
   for e in s['edges']:
    if e['edge_type'] in {'visualization','suggested_sequence','human_authority','blocked'}:self.assertFalse(e['runtime_executable'])
if __name__=='__main__':unittest.main()
