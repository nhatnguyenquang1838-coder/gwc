from __future__ import annotations

import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

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


if __name__ == "__main__":
    unittest.main()
