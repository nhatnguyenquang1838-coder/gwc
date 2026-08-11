"""Compiler identity regressions for SCRUM-394 P1-C hardening."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.node_architect.compile_flow_policy_profile import compile_flow_policy_profile

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_COMPILED_DIGEST = "sha256:b4d286de8ee954b086be7abb452e27fb194252bc812538d3918cf3dc43eb6a50"


def _load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _artifacts():
    profiles = _load("core/node-architect/profile-registry.json")
    flow = next(item for item in profiles["profiles"] if item.get("id") == "full-flow-v3")
    policy = _load("core/node-architect/gate-applicability-policy-registry.json")
    route = _load("core/node-architect/gate-node-route-profile.json")
    return flow, policy, route


class FlowPolicyCompilerIdentityHardeningTests(unittest.TestCase):
    def test_exact_materialized_sources_compile_to_committed_identity(self):
        flow, policy, route = _artifacts()
        result = compile_flow_policy_profile(
            flow_profile=flow, policy_registry=policy, route_profile=route, root=ROOT,
        )
        committed = _load("core/node-architect/flow-policy-compiled-profile.json")
        self.assertEqual(result["result"]["status"], "COMPATIBLE", result["result"])
        self.assertEqual(result, committed)
        self.assertEqual(result["compiled_digest"], EXPECTED_COMPILED_DIGEST)

    def test_live_composition_registry_drift_blocks_compile(self):
        flow, policy, route = _artifacts()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in (
                "core/node-architect/node-registry.json",
                "core/node-architect/scenario-registry.json",
                "core/node-architect/runtime-graph-registry.json",
                "core/GATE_LIFECYCLE_CONTRACT_v1.0.md",
            ):
                source = ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

            node_path = root / "core/node-architect/node-registry.json"
            node_registry = json.loads(node_path.read_text(encoding="utf-8"))
            node_registry["compiler_identity_test_drift"] = True
            node_path.write_text(
                json.dumps(node_registry, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            result = compile_flow_policy_profile(
                flow_profile=flow, policy_registry=policy, route_profile=route, root=root,
            )
        self.assertEqual(result["result"]["status"], "BLOCKED", result["result"])
        self.assertIn("COMPOSITION_REGISTRY_DIGEST_DRIFT", result["result"]["reason_codes"])

    def test_legacy_route_revision_changes_compiled_identity(self):
        flow, policy, route = _artifacts()
        baseline = compile_flow_policy_profile(
            flow_profile=flow, policy_registry=policy, route_profile=route, root=ROOT,
        )
        changed_route = copy.deepcopy(route)
        changed_route["revision"] = str(route["revision"]) + "-identity-drift"
        changed = compile_flow_policy_profile(
            flow_profile=flow, policy_registry=policy, route_profile=changed_route, root=ROOT,
        )
        self.assertEqual(changed["result"]["status"], "COMPATIBLE", changed["result"])
        self.assertNotEqual(baseline["compiled_digest"], changed["compiled_digest"])
        self.assertEqual(
            changed["bindings"]["legacy_route_projection_revision"],
            changed_route["revision"],
        )


if __name__ == "__main__":
    unittest.main()
