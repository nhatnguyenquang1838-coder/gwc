"""Exact-source activation binding regressions for SCRUM-394 P1-C.

The active compiled profile is immutable evidence, but the activation pointer is
live. Activation must fail closed when any bound source advances after compile.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.node_architect.compile_flow_policy_profile import GATE_LIFECYCLE_PATH
from tools.node_architect.resolve_active_flow_policy_profile import (
    ACTIVATION_PATH,
    GRAPH_REGISTRY_PATH,
    NODE_REGISTRY_PATH,
    POLICY_REGISTRY_PATH,
    PROFILE_REGISTRY_PATH,
    ROUTE_PROFILE_PATH,
    SCENARIO_REGISTRY_PATH,
    resolve_active_compiled_profile,
)

ROOT = Path(__file__).resolve().parents[1]
COMPILED_PROFILE_PATH = "core/node-architect/flow-policy-compiled-profile.json"

SOURCE_FILES = (
    ACTIVATION_PATH,
    COMPILED_PROFILE_PATH,
    PROFILE_REGISTRY_PATH,
    POLICY_REGISTRY_PATH,
    NODE_REGISTRY_PATH,
    SCENARIO_REGISTRY_PATH,
    GRAPH_REGISTRY_PATH,
    ROUTE_PROFILE_PATH,
    GATE_LIFECYCLE_PATH,
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class ActivationSourceBindingTests(unittest.TestCase):
    def _temp_root(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        for relative in SOURCE_FILES:
            source = ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return tmp, root

    def _resolve(self, root: Path):
        registry = _load(root / ACTIVATION_PATH)
        return resolve_active_compiled_profile(activation_registry=registry, root=root)

    def test_exact_materialized_source_set_is_active(self):
        tmp, root = self._temp_root()
        self.addCleanup(tmp.cleanup)
        result = self._resolve(root)
        self.assertEqual(result["outcome"], "ACTIVE", result["reason_codes"])

    def test_node_registry_drift_blocks_activation(self):
        tmp, root = self._temp_root()
        self.addCleanup(tmp.cleanup)
        path = root / NODE_REGISTRY_PATH
        payload = _load(path)
        payload["activation_test_drift"] = True
        _write(path, payload)
        result = self._resolve(root)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("ACTIVE_COMPILED_REGISTRY_BINDING_STALE", result["reason_codes"])

    def test_policy_registry_content_drift_blocks_activation(self):
        tmp, root = self._temp_root()
        self.addCleanup(tmp.cleanup)
        path = root / POLICY_REGISTRY_PATH
        payload = _load(path)
        payload["activation_test_drift"] = True
        _write(path, payload)
        result = self._resolve(root)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("ACTIVE_POLICY_REGISTRY_DIGEST_DRIFT", result["reason_codes"])

    def test_workflow_source_drift_with_stale_declared_digest_blocks_activation(self):
        tmp, root = self._temp_root()
        self.addCleanup(tmp.cleanup)
        path = root / PROFILE_REGISTRY_PATH
        registry = _load(path)
        flow = next(item for item in registry["profiles"] if item.get("id") == "full-flow-v3")
        flow["workflow"]["entry_nodes"] = list(flow["workflow"]["entry_nodes"]) + ["synthetic.drift"]
        # Intentionally leave flow["compiled"]["workflow_digest"] stale.
        _write(path, registry)
        result = self._resolve(root)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("ACTIVE_WORKFLOW_DIGEST_DRIFT", result["reason_codes"])

    def test_gate_lifecycle_text_drift_blocks_activation(self):
        tmp, root = self._temp_root()
        self.addCleanup(tmp.cleanup)
        path = root / GATE_LIFECYCLE_PATH
        path.write_text(path.read_text(encoding="utf-8") + "\n<!-- activation drift -->\n", encoding="utf-8")
        result = self._resolve(root)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("ACTIVE_GATE_LIFECYCLE_DIGEST_DRIFT", result["reason_codes"])

    def test_legacy_route_projection_revision_drift_blocks_activation(self):
        tmp, root = self._temp_root()
        self.addCleanup(tmp.cleanup)
        path = root / ROUTE_PROFILE_PATH
        payload = _load(path)
        payload["revision"] = str(payload.get("revision") or "") + "-drift"
        _write(path, payload)
        result = self._resolve(root)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("ACTIVE_LEGACY_ROUTE_PROJECTION_DRIFT", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
