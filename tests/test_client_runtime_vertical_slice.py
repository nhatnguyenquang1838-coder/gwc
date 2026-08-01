import json, unittest
from pathlib import Path
from jsonschema import Draft202012Validator
from tools.node_architect.client_runtime import *
BASE="3acf169b91fa2d4c4c32f573fa3318d00dad9088"
def req():
    return {"task_id":"SCRUM-259","repository":"nhatnguyenquang1838-coder/gwc","protected_base_sha":BASE,"scenario_id":"client-runtime-node-architect-vertical-slice","route_intent":"client-runtime-node-architect-vertical-slice","route_nodes":list(VERTICAL_SLICE_ROUTE),"evidence":{"ci":{"status":"success","head_sha":BASE}}}
class ClientRuntimeVerticalSliceTests(unittest.TestCase):
    def test_pass_typed_terminal(self):
        r=run_client_runtime(req()); self.assertEqual(r.status,PASS); self.assertEqual(r.terminal_code,TERMINAL_PASS); self.assertEqual(r.executed_nodes[-1],TERMINAL_NODE); self.assertFalse(r.manual_fallback_used)
    def test_checkpoint_persisted(self):
        r=run_client_runtime(req()); self.assertEqual(r.checkpoints[0]["node"],"runtime_checkpoint.checkpoint-persist"); self.assertEqual(r.checkpoints[0]["protected_base_sha"],BASE)
    def test_missing_handler_fails_closed(self):
        reg=dict(default_handler_registry()); reg.pop("validation_quality.evidence-quality-check"); r=run_client_runtime(req(),reg); self.assertEqual(r.status,BLOCKED); self.assertEqual(r.terminal_code,BLOCKED_NODE_HANDLER_UNAVAILABLE); self.assertFalse(r.manual_fallback_used)
    def test_route_drift_rejected(self):
        x=req(); x["route_nodes"]=["client_request","route_scenario_validation","package_export.smoke-verification"]; r=run_client_runtime(x); self.assertEqual(r.status,BLOCKED); self.assertEqual(r.terminal_code,BLOCKED_ROUTE_NOT_ALLOWLISTED)
    def test_json_schemas_accept_examples(self):
        s1=json.loads(Path("schemas/client-runtime-request.schema.json").read_text()); s2=json.loads(Path("schemas/client-runtime-result.schema.json").read_text()); Draft202012Validator.check_schema(s1); Draft202012Validator.check_schema(s2); Draft202012Validator(s1).validate(req()); Draft202012Validator(s2).validate(run_client_runtime(req()).to_dict())
if __name__=="__main__": unittest.main()
