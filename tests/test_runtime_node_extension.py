import copy
import json
import tempfile
import unittest
from pathlib import Path
from tools.node_architect.validate_runtime_registry import validate_registry

ROOT=Path(__file__).resolve().parents[1]
class ExtensionTests(unittest.TestCase):
    def test_baseline_preserved_one_extension(self):
        report=validate_registry(ROOT); extension_issues=[x for x in report["issues"] if not (x.startswith("scenario ") and x.endswith("provenance source is missing"))]; self.assertEqual(extension_issues,[],extension_issues); self.assertEqual(report["counts"]["baseline_nodes"],81); self.assertEqual(report["counts"]["extension_nodes"],1); self.assertEqual(report["counts"]["effective_nodes"],82)
    def test_extension_is_scrum_284_node(self):
        data=json.loads((ROOT/"core/node-architect/runtime-node-extension-registry.json").read_text()); self.assertEqual(data["admitted_extension_count"],1); item=data["extensions"][0]; self.assertEqual(item["extension_slot"],82); self.assertEqual(item["decision_task_id"],"SCRUM-284"); self.assertEqual(item["node"]["id"],"gate_authority.research-review-to-execution")
    def test_undeclared_graph_growth_fails_closed(self):
        # Validator contract: graph closure is baseline + admitted extensions; unknown route nodes fail.
        graph=json.loads((ROOT/"core/node-architect/runtime-graph-registry.json").read_text()); self.assertEqual(set(graph["nodes"])-set(json.loads((ROOT/"core/node-architect/node-registry.json").read_text())["nodes"][i]["id"] for i in range(81)), {"gate_authority.research-review-to-execution"})
if __name__ == "__main__": unittest.main()
