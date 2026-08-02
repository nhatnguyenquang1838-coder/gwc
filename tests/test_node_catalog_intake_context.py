import importlib.util, json, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VP=ROOT/"tools/node_architect/validate_node_catalog_intake_context.py"
def load():
 s=importlib.util.spec_from_file_location("v",VP); m=importlib.util.module_from_spec(s); assert s.loader; s.loader.exec_module(m); return m
class IntakeContextNodeCatalogTests(unittest.TestCase):
 def setUp(self): self.v=load(); self.root=ROOT
 def test_current_family_and_runtime_contracts_pass(self):
  self.assertEqual([], self.v.validate_family(self.root/"core/node-architect/node-catalog/intake_context"))
  self.assertEqual([], self.v.validate_runtime_contracts(self.root))
 def test_runtime_contracts_include_intake_card_and_context_gap(self):
  self.assertEqual("intake-card", self.v.RUNTIME_CONTRACTS["intake_context.intake-card-render"]["artifact_type"])
  self.assertEqual("context-gap-decision", self.v.RUNTIME_CONTRACTS["intake_context.context-gap-escalation"]["artifact_type"])
 def test_rejects_wrong_count_and_write_authority(self):
  src=self.root/"core/node-architect/node-catalog/intake_context"
  with tempfile.TemporaryDirectory() as t:
   d=Path(t)
   for p in src.glob("*.node.json"):
    data=json.loads(p.read_text())
    if data["node_id"]=="intake_context.context-gap-escalation": data["authority_boundary"]="write"
    (d/p.name).write_text(json.dumps(data))
   self.assertTrue(any("read-only" in e for e in self.v.validate_family(d)))
   next(d.glob("*.node.json")).unlink()
   self.assertTrue(any("expected exactly 9" in e for e in self.v.validate_family(d)))
 def test_runtime_schema_and_entrypoint_fail_closed(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)
   for c in self.v.RUNTIME_CONTRACTS.values():
    sp=root/c["schema"]; ep=root/c["evaluator"]; sp.parent.mkdir(parents=True,exist_ok=True); ep.parent.mkdir(parents=True,exist_ok=True)
    sp.write_text((self.root/c["schema"]).read_text())
    ep.write_text((self.root/c["evaluator"]).read_text())
   (root/"schemas/context-gap-decision.schema.json").unlink()
   self.assertTrue(any("runtime schema missing" in e for e in self.v.validate_runtime_contracts(root)))
   (root/"schemas/context-gap-decision.schema.json").write_text((self.root/"schemas/context-gap-decision.schema.json").read_text())
   (root/"tools/node_architect/context_gap_escalation.py").write_text("VALUE=1\n")
   self.assertTrue(any("missing callable decide_context_gap_escalation" in e for e in self.v.validate_runtime_contracts(root)))
if __name__=="__main__": unittest.main()
