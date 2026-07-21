from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "resolve_profiles", ROOT / "tools/resolve_profiles.py"
)
RESOLVER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RESOLVER
SPEC.loader.exec_module(RESOLVER)


class ProfileResolverTests(unittest.TestCase):
    def test_resolves_in_canonical_order(self) -> None:
        result = RESOLVER.resolve_profile_set(
            ROOT, ROOT / "governance/profile-sets/gwc-standard.yaml"
        )
        self.assertEqual(
            [item["profile_type"] for item in result["resolved_profiles"]],
            ["gate_policy", "agent_runtime", "agent_runtime", "environment", "risk"],
        )
        self.assertEqual(
            [item["profile_id"] for item in result["resolved_profiles"]],
            ["standard", "chatgpt", "dwc", "repo-governance", "default"],
        )

    def copy_fixture(self) -> Path:
        root = Path(tempfile.mkdtemp())
        paths = [
            "governance/profile-sets/gwc-standard.yaml",
            "governance/gate-policy-profiles/standard.yaml",
            "governance/agent-runtime-profiles/chatgpt.yaml",
            "governance/agent-runtime-profiles/dwc.yaml",
            "governance/environment-profiles/repo-governance.yaml",
            "governance/risk-profiles/default.yaml",
            "schemas/profile-set.schema.json",
            "schemas/gate-policy-profile.schema.json",
        ]
        for relative in paths:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes())
        return root

    def test_missing_reference_fails_closed(self) -> None:
        root = self.copy_fixture()
        (root / "governance/risk-profiles/default.yaml").unlink()
        with self.assertRaisesRegex(RESOLVER.ProfileResolutionError, "does not exist"):
            RESOLVER.resolve_profile_set(
                root, root / "governance/profile-sets/gwc-standard.yaml"
            )

    def test_duplicate_id_fails_closed(self) -> None:
        root = self.copy_fixture()
        path = root / "governance/profile-sets/gwc-standard.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["profiles"]["agent_runtimes"].append(
            copy.deepcopy(data["profiles"]["agent_runtimes"][0])
        )
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        with self.assertRaisesRegex(
            RESOLVER.ProfileResolutionError, "duplicate profile reference"
        ):
            RESOLVER.resolve_profile_set(root, path)

    def test_wrong_profile_type_fails_closed(self) -> None:
        root = self.copy_fixture()
        path = root / "governance/risk-profiles/default.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["profile_type"] = "environment"
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        with self.assertRaisesRegex(
            RESOLVER.ProfileResolutionError, "wrong profile type"
        ):
            RESOLVER.resolve_profile_set(
                root, root / "governance/profile-sets/gwc-standard.yaml"
            )

    def test_gate_policy_schema_rejects_authority_and_write_drift(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/gate-policy-profile.schema.json").read_text(
                encoding="utf-8"
            )
        )
        profile = yaml.safe_load(
            (ROOT / "governance/gate-policy-profiles/standard.yaml").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft202012Validator(schema)
        cases = [
            ("G0_CONTEXT", "authority", "exact_human_approval"),
            ("G0_CONTEXT", "write_allowed", True),
            ("G1_ALIGNMENT", "authority", "exact_human_approval"),
            ("G1_ALIGNMENT", "write_allowed", True),
            ("G2_EXECUTION", "authority", "automatic_read_only"),
            ("G2_EXECUTION", "write_allowed", False),
            ("G3_PR", "authority", "exact_human_approval"),
            ("G3_PR", "write_allowed", False),
            ("G3_PR", "draft_pr_only", False),
            ("G3_PR", "ready_for_review_after_pass", False),
            ("G4_MERGE", "authority", "evidence_driven"),
            ("G4_MERGE", "write_allowed", False),
            ("G5_DEPLOY", "authority", "automatic_read_only"),
            ("G5_DEPLOY", "write_allowed", False),
            ("G6_PRODUCTION_DATA", "authority", "automatic_read_only"),
            ("G6_PRODUCTION_DATA", "write_allowed", False),
        ]
        for gate, field, unsafe_value in cases:
            with self.subTest(gate=gate, field=field, unsafe_value=unsafe_value):
                mutated = copy.deepcopy(profile)
                mutated["gates"][gate][field] = unsafe_value
                self.assertTrue(
                    list(validator.iter_errors(mutated)),
                    f"unsafe gate-policy drift was accepted: {gate}.{field}={unsafe_value!r}",
                )

    def test_gate_policy_schema_rejects_pr_flags_outside_g3(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/gate-policy-profile.schema.json").read_text(
                encoding="utf-8"
            )
        )
        profile = yaml.safe_load(
            (ROOT / "governance/gate-policy-profiles/standard.yaml").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft202012Validator(schema)
        for gate in (
            "G0_CONTEXT",
            "G1_ALIGNMENT",
            "G2_EXECUTION",
            "G4_MERGE",
            "G5_DEPLOY",
            "G6_PRODUCTION_DATA",
        ):
            with self.subTest(gate=gate):
                mutated = copy.deepcopy(profile)
                mutated["gates"][gate]["draft_pr_only"] = True
                self.assertTrue(list(validator.iter_errors(mutated)))


if __name__ == "__main__":
    unittest.main()
