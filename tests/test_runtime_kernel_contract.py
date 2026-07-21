"""Tests for the GWC runtime kernel contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools/node_architect/validate_runtime_kernel_contract.py"
PACKAGE = ROOT / "projects/gwc/package.yaml"


def run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_runtime_kernel_contract", VALIDATOR)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RuntimeKernelContractTests(unittest.TestCase):
    def test_real_workspace_runtime_kernel_contract_passes(self) -> None:
        result = run_validator("--workspace", str(ROOT))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["outcome"], "PASS")

    def test_missing_invariant_blocks_kernel(self) -> None:
        module = load_validator_module()
        kernel = {
            "schema_version": "0.1",
            "kernel_id": "RUNTIME_KERNEL",
            "version": "0.1",
            "invariants": ["authority_boundary"],
            "authority": {
                "write_requires_exact_g2": True,
                "merge_requires_exact_g4": True,
                "external_projection_authority": False,
                "approval_boundaries": ["G2_EXECUTION", "G4_MERGE"],
            },
            "durability": {
                "event_history_required": True,
                "checkpoint_before_suspend": True,
                "version_pin_required": True,
            },
            "side_effects": {
                "idempotency_key_required": True,
                "readback_required": True,
                "retry_requires_reconciliation": True,
            },
            "node_catalog_guard": {
                "expansion_allowed_before_kernel_pass": False,
                "requires_reference_node_pack": True,
                "requires_failure_simulation": True,
            },
        }
        findings = module.validate_kernel(kernel)
        self.assertTrue(any(item["code"] == "KERNEL_INVARIANT_MISSING" for item in findings))

    def test_catalog_expansion_must_remain_gated(self) -> None:
        module = load_validator_module()
        kernel = {
            "schema_version": "0.1",
            "kernel_id": "RUNTIME_KERNEL",
            "version": "0.1",
            "invariants": sorted(module.REQUIRED_INVARIANTS),
            "authority": {
                "write_requires_exact_g2": True,
                "merge_requires_exact_g4": True,
                "external_projection_authority": False,
                "approval_boundaries": ["G2_EXECUTION", "G4_MERGE"],
            },
            "durability": {
                "event_history_required": True,
                "checkpoint_before_suspend": True,
                "version_pin_required": True,
            },
            "side_effects": {
                "idempotency_key_required": True,
                "readback_required": True,
                "retry_requires_reconciliation": True,
            },
            "node_catalog_guard": {
                "expansion_allowed_before_kernel_pass": True,
                "requires_reference_node_pack": True,
                "requires_failure_simulation": True,
            },
        }
        findings = module.validate_kernel(kernel)
        self.assertTrue(any(item["code"] == "CATALOG_EXPANSION_NOT_GATED" for item in findings))

    def test_package_exports_runtime_kernel_artifacts_without_version_bump(self) -> None:
        package_text = PACKAGE.read_text(encoding="utf-8")
        self.assertIn('package_version: "1.16.0"', package_text)
        for package_id in [
            "runtime-kernel-rule",
            "runtime-kernel-schema",
            "runtime-event-schema",
            "transition-envelope-schema",
            "node-pack-schema",
            "runtime-kernel-validator",
        ]:
            self.assertIn(f"id: {package_id}", package_text)


if __name__ == "__main__":
    unittest.main()
