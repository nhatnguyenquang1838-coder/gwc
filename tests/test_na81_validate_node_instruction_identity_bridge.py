"""NA81 regression: registry_provenance_source_path_identity_bridge must fail closed.

SCRUM-337 / NA81 recert (run SCRUM-288-NA81-20260819T1905-SCRUM337).

The B2 identity bridge resolves a node descriptor's identity through the registry
entry whose ``provenance.source_path`` matches the route descriptor path
(``registry_provenance_source_path_identity_bridge``). It must never silently bind
a mismatched, ambiguous, or missing descriptor to the wrong runtime node.

Controller S1 requirement: "add regression tests fails-closed on mismatch/ambiguous/missing
provenance". These tests lock that contract for the validation_quality.ci-evidence-capture
node without mutating the descriptor, registry identity, or schema.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, rel: str):
    p = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load(path: str):
    text = (ROOT / path).read_text(encoding="utf-8")
    if path.endswith((".yaml", ".yml")):
        import yaml
        return yaml.safe_load(text)
    return json.loads(text)


CARD = "core/node-architect/node-instructions/validation_quality/ci-evidence-capture.node-instruction.yaml"
SCHEMA = "schemas/node-architect/node-instruction.schema.json"
DESCRIPTOR = "core/node-architect/node-catalog/validation_quality/ci-evidence-capture.node.json"
REGISTRY = "core/node-architect/node-registry.json"
PROFILE = "core/node-architect/gate-node-route-profile.json"
NODE_ID = "validation_quality.ci-evidence-capture"


class NA81IdentityBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vin = _module("vin_na81", "tools/node_architect/validate_node_instruction.py")
        cls.profile = _load(PROFILE)
        cls.registry = _load(REGISTRY)

    def _run(self, profile_dict, registry_dict=None):
        d = tempfile.mkdtemp()
        pp = Path(d) / "profile.json"
        pp.write_text(json.dumps(profile_dict))
        rp = Path(d) / "registry.json"
        rp.write_text(json.dumps(registry_dict if registry_dict is not None else self.registry))
        return self.vin.validate_instruction_path(
            instruction_path=ROOT / CARD,
            schema_path=ROOT / SCHEMA,
            descriptor_path=ROOT / DESCRIPTOR,
            registry_path=rp,
            route_profile_path=pp,
            active_gate="G3_PR",
            mode="normal",
        )

    def test_positive_ci_evidence_capture_validates(self):
        r = self._run(self.profile)
        self.assertTrue(r.valid, r.reason_code)
        self.assertEqual(r.reason_code, "NODE_INSTRUCTION_VALID")

    def test_mismatched_resolved_registry_id_fails_closed(self):
        # Route resolves (current_node == card node_id), descriptor provenance resolves
        # to exactly one registry node, but that node's runtime id != card node_id.
        reg = copy.deepcopy(self.registry)
        for n in reg["nodes"]:
            if n.get("id") == NODE_ID:
                n["id"] = "validation_quality.NOT_REAL"
                break
        r = self._run(self.profile, reg)
        self.assertFalse(r.valid)
        self.assertEqual(r.reason_code, "NODE_INSTRUCTION_INVALID")

    def test_ambiguous_descriptor_provenance_fails_closed(self):
        # Two registry nodes share the same provenance.source_path -> ambiguous.
        reg = copy.deepcopy(self.registry)
        src = [n for n in reg["nodes"] if n["id"] == NODE_ID][0]
        dup = copy.deepcopy(src)
        dup["id"] = "validation_quality.ci-evidence-capture.DUP"
        reg["nodes"].append(dup)
        r = self._run(self.profile, reg)
        self.assertFalse(r.valid)
        self.assertEqual(r.reason_code, "NODE_INSTRUCTION_INVALID")

    def test_missing_descriptor_provenance_fails_closed(self):
        # No registry node has a provenance.source_path matching the descriptor path.
        reg = copy.deepcopy(self.registry)
        reg["nodes"] = [n for n in reg["nodes"] if n["id"] != NODE_ID]
        r = self._run(self.profile, reg)
        self.assertFalse(r.valid)
        self.assertEqual(r.reason_code, "NODE_INSTRUCTION_INVALID")


if __name__ == "__main__":
    unittest.main()
