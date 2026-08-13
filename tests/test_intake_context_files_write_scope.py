from __future__ import annotations

import copy
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools/node_architect/files_write_scope.py"
SCHEMA = ROOT / "schemas/bounded-write-scope.schema.json"
TASK = "SCRUM-304"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "6" * 40
BRANCH = "auto/na81-20260810/SCRUM-304"

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_module():
    spec = importlib.util.spec_from_file_location("files_write_scope", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_artifact(mod, schema, artifact):
    """Lightweight structural validation mirroring the JSON schema, no jsonschema import."""
    errors: list[str] = []
    props = schema.get("properties", {})

    def check_type(value, typ):
        if typ is str:
            return isinstance(value, str)
        if typ is bool:
            return isinstance(value, bool)
        if typ is list:
            return isinstance(value, list)
        if typ is dict:
            return isinstance(value, dict)
        if isinstance(typ, list):  # ["string", "null"]
            return value is None or check_type(value, typ[1])
        return True

    for key, decl in props.items():
        if key not in artifact and "const" not in decl:
            if key in schema.get("required", []):
                errors.append(f"missing required {key}")
            continue
        value = artifact.get(key)
        if "const" in decl:
            if value != decl["const"]:
                errors.append(f"{key} expected const {decl['const']!r}, got {value!r}")
            continue
        if "enum" in decl:
            if value not in decl["enum"]:
                errors.append(f"{key} not in enum: {value!r}")
            continue
        if isinstance(decl.get("type"), list):
            if value is not None and not check_type(value, decl["type"]):
                errors.append(f"{key} type mismatch: {value!r}")
            continue
        if "type" in decl and not check_type(value, decl["type"]):
            errors.append(f"{key} type mismatch: {value!r}")

    if artifact.get("outcome") == "READY":
        if not artifact.get("source_bindings"):
            errors.append("READY requires source_bindings")
        if not artifact.get("files_write"):
            errors.append("READY requires files_write")
        if artifact.get("failure_classification") is not None:
            errors.append("READY must have null failure_classification")

    return errors


class FilesWriteScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        _validate_artifact(cls.mod, cls.schema, {})  # schema load smoke
        cls.validator = _validate_artifact

    def payload(self):
        return {
            "task_id": TASK,
            "repository": REPO,
            "base_sha": BASE,
            "branch": BRANCH,
            "allowed_roots": ["core", "schemas", "tools", "tests"],
            "repository_paths": [
                "core/node-architect/node-catalog/intake_context/files-write-scope.node.json",
                "schemas/bounded-write-scope.schema.json",
                "tools/node_architect/files_write_scope.py",
                "tests/test_intake_context_files_write_scope.py",
            ],
            "write_requirements": [
                {
                    "requirement_id": "descriptor",
                    "candidates": ["core/node-architect/node-catalog/intake_context/files-write-scope.node.json"],
                    "reason": "Bind the canonical node descriptor.",
                },
                {
                    "requirement_id": "evaluator",
                    "candidates": ["tools/node_architect/files_write_scope.py"],
                    "reason": "Implement the candidate write-scope evaluator.",
                },
            ],
            "excluded_paths": [
                {"path": "tests", "reason": "Tests are not required by this slice.", "match": "prefix"}
            ],
            "source_bindings": [
                {"source_type": "repository", "ref": "pre-prod", "revision": BASE, "status": "VERIFIED"},
                {"source_type": "ua", "ref": "SCRUM-304", "revision": "ua-v1", "status": "VERIFIED"},
            ],
            "repository_snapshot": {"base_sha": BASE, "tree_digest": "sha256:" + "1" * 64},
            "ua_snapshot": {"base_sha": BASE, "digest": "sha256:" + "2" * 64},
            "observed_at": "2026-08-10T08:00:00Z",
        }

    def render(self, **changes):
        payload = copy.deepcopy(self.payload())
        payload.update(changes)
        return self.mod.render_files_write_scope(payload)

    def assert_artifact(self, artifact):
        errors = self.validator(self.schema, artifact)
        self.assertEqual([], errors, msg="\n".join(errors))

    def test_minimum_verified_scope_is_ready_and_schema_valid(self):
        artifact = self.render()
        self.assertEqual("READY", artifact["outcome"])
        self.assertEqual(
            [
                "core/node-architect/node-catalog/intake_context/files-write-scope.node.json",
                "tools/node_architect/files_write_scope.py",
            ],
            artifact["files_write"],
        )
        self.assertEqual("ACCEPTED", artifact["reason_code"])
        self.assert_artifact(artifact)

    def test_prohibited_target_is_rejected_without_broadening(self):
        payload = self.payload()
        payload["write_requirements"][1]["candidates"] = ["core/node-architect/authority/x.json"]
        artifact = self.mod.render_files_write_scope(payload)
        # The prohibited target is recorded deterministically and excluded from the
        # selected write set; the safe descriptor requirement still resolves.
        self.assertIn("core/node-architect/authority/x.json", artifact["prohibited_targets"])
        self.assertIn("core/node-architect/authority/x.json", artifact["files_exclude"])
        self.assertNotIn("core/node-architect/authority/x.json", artifact["files_write"])
        self.assert_artifact(artifact)

    def test_explicit_exclusion_is_recorded_with_reason(self):
        payload = self.payload()
        payload["write_requirements"].append({
            "requirement_id": "optional-test",
            "candidates": ["tests/test_intake_context_files_write_scope.py", "schemas/bounded-write-scope.schema.json"],
            "reason": "One verified contract source is enough.",
        })
        artifact = self.mod.render_files_write_scope(payload)
        self.assertEqual("READY", artifact["outcome"])
        self.assertIn("tests/test_intake_context_files_write_scope.py", artifact["files_exclude"])
        self.assert_artifact(artifact)

    def test_outside_allowed_root_fails_closed(self):
        payload = self.payload()
        payload["write_requirements"][0]["candidates"] = [".github/workflows/validate-instructions.yml"]
        artifact = self.mod.render_files_write_scope(payload)
        self.assertEqual(("BLOCKED", "SCOPE_DRIFT", "RECOMPUTE_WRITE_SCOPE"),
                         (artifact["outcome"], artifact["reason_code"], artifact["next_route"]))
        self.assertIn(".github/workflows/validate-instructions.yml", artifact["files_exclude"])
        self.assert_artifact(artifact)

    def test_ambiguous_candidates_fail_closed(self):
        payload = self.payload()
        payload["write_requirements"][1]["candidates"] = [
            "tools/node_architect/files_write_scope.py",
            "schemas/bounded-write-scope.schema.json",
        ]
        artifact = self.mod.render_files_write_scope(payload)
        self.assertEqual(("BLOCKED", "MALFORMED_INPUT", "CLARIFY_WRITE_SCOPE"),
                         (artifact["outcome"], artifact["reason_code"], artifact["next_route"]))
        self.assert_artifact(artifact)

    def test_repository_or_ua_drift_invalidates_scope(self):
        artifact = self.render(repository_snapshot={"base_sha": "7" * 40, "tree_digest": "sha256:" + "1" * 64})
        self.assertEqual(("BLOCKED", "SCOPE_DRIFT", "RECOMPUTE_WRITE_SCOPE"),
                         (artifact["outcome"], artifact["reason_code"], artifact["next_route"]))
        self.assert_artifact(artifact)

    def test_stale_source_binding_invalidates_scope(self):
        payload = self.payload()
        payload["source_bindings"][0]["status"] = "STALE"
        artifact = self.mod.render_files_write_scope(payload)
        self.assertEqual(("BLOCKED", "SCOPE_DRIFT"), (artifact["outcome"], artifact["reason_code"]))
        self.assert_artifact(artifact)

    def test_prior_scope_from_another_base_is_stale(self):
        artifact = self.render(prior_scope={"base_sha": "8" * 40, "scope_hash": "sha256:" + "3" * 64})
        self.assertEqual(("BLOCKED", "SCOPE_DRIFT"), (artifact["outcome"], artifact["reason_code"]))
        self.assert_artifact(artifact)

    def test_scope_hash_is_deterministic_and_well_formed(self):
        first = self.render()
        payload = self.payload()
        payload["write_requirements"].reverse()
        payload["repository_paths"].reverse()
        payload["source_bindings"].reverse()
        payload["observed_at"] = "2099-01-01T00:00:00Z"
        second = self.mod.render_files_write_scope(payload)
        self.assertEqual(first["scope_hash"], second["scope_hash"])
        self.assertTrue(SHA256_RE.match(first["scope_hash"]))

    def test_no_authority_is_ever_granted(self):
        artifact = self.render()
        self.assertTrue(artifact["read_only_projection"])
        self.assertTrue(artifact["candidate_write_scope"])
        self.assertTrue(artifact["authority_negative"])
        self.assertFalse(any(value for key, value in artifact.items() if key.endswith("authority_granted")))

    def test_excluded_actions_are_present_and_prohibit_merge(self):
        artifact = self.render()
        self.assertIn("merge", artifact["excluded_actions"])
        self.assertIn("production_data", artifact["excluded_actions"])
        self.assert_artifact(artifact)

    def test_only_prohibited_candidate_fails_closed(self):
        artifact = self.mod.render_files_write_scope({
            "task_id": TASK,
            "repository": REPO,
            "base_sha": BASE,
            "branch": BRANCH,
            "write_requirements": [{
                "requirement_id": "only-prohibited",
                "candidates": ["core/node-architect/authority/x.json"],
                "reason": "Attempt to write authority control-plane.",
            }],
            "source_bindings": [
                {"source_type": "repository", "ref": "pre-prod", "revision": BASE, "status": "VERIFIED"},
            ],
            "repository_snapshot": {"base_sha": BASE, "tree_digest": "sha256:" + "1" * 64},
        })
        self.assertEqual(("BLOCKED", "PROHIBITED_ACTION", "RESTRICT_WRITE_SCOPE"),
                         (artifact["outcome"], artifact["reason_code"], artifact["next_route"]))
        self.assertIn("core/node-architect/authority/x.json", artifact["prohibited_targets"])
        self.assert_artifact(artifact)

    def test_legacy_payload_remains_compatible(self):
        artifact = self.mod.render_files_write_scope({
            "task_id": TASK,
            "repository": REPO,
            "base_sha": BASE,
            "branch": BRANCH,
            "files_write": [
                "core/node-architect/node-catalog/intake_context/files-write-scope.node.json",
                "tools/node_architect/files_write_scope.py",
            ],
        })
        self.assertEqual("READY", artifact["outcome"])
        self.assertEqual(
            [
                "core/node-architect/node-catalog/intake_context/files-write-scope.node.json",
                "tools/node_architect/files_write_scope.py",
            ],
            artifact["files_write"],
        )
        self.assert_artifact(artifact)

    def test_legacy_unsafe_path_still_raises(self):
        with self.assertRaises(ValueError):
            self.mod.render_files_write_scope({
                "task_id": TASK,
                "repository": REPO,
                "base_sha": BASE,
                "branch": BRANCH,
                "files_write": ["C:\\escape.md"],
            })


    # --- SCRUM-304 R7 recert: exact-match denial of the 5 immutable control-plane paths ---

    R7_PROHIBITED_EXACT = [
        "tools/node_architect/materialize_autonomous_preprod_run_authority.py",
        "core/AUTONOMOUS_PREPROD_INTEGRATION_POLICY_v1.0.md",
        "tools/node_architect/audit_guardrail.py",
        "tools/node_architect/autonomous_execution_runtime.py",
        "tools/node_architect/slack_task_controller.py",
    ]
    # Representative pre-existing R6 prohibitions retained for the 8-path denial probe.
    R6_PRESERVED_PROHIBITED = [
        "secrets/token.json",
        "core/node-architect/authority/x.json",
        ".env",
    ]

    def _sole_requirement_payload(self, candidate: str) -> dict:
        return {
            "task_id": TASK,
            "repository": REPO,
            "base_sha": BASE,
            "branch": BRANCH,
            "write_requirements": [{
                "requirement_id": "probe",
                "candidates": [candidate],
                "reason": "Probe denial of control-plane path.",
            }],
            "source_bindings": [
                {"source_type": "repository", "ref": "pre-prod", "revision": BASE, "status": "VERIFIED"},
            ],
            "repository_snapshot": {"base_sha": BASE, "tree_digest": "sha256:" + "1" * 64},
        }

    def test_r7_five_control_plane_paths_fail_closed(self):
        for path in self.R7_PROHIBITED_EXACT:
            with self.subTest(path=path):
                artifact = self.mod.render_files_write_scope(self._sole_requirement_payload(path))
                self.assertEqual(
                    ("BLOCKED", "PROHIBITED_ACTION", "RESTRICT_WRITE_SCOPE"),
                    (artifact["outcome"], artifact["reason_code"], artifact["next_route"]),
                )
                self.assertIn(path, artifact["prohibited_targets"])
                self.assertIn(path, artifact["files_exclude"])
                self.assertNotIn(path, artifact["files_write"])
                self.assertFalse(
                    any(value for key, value in artifact.items() if key.endswith("authority_granted"))
                )
                self.assert_artifact(artifact)

    def test_r7_eight_path_denial_probe_preserves_existing_prohibitions(self):
        # 5 new exact-match denials + 3 preserved R6 prohibitions = explicit 8-path probe.
        for path in (*self.R7_PROHIBITED_EXACT, *self.R6_PRESERVED_PROHIBITED):
            with self.subTest(path=path):
                artifact = self.mod.render_files_write_scope(self._sole_requirement_payload(path))
                self.assertEqual("BLOCKED", artifact["outcome"])
                self.assertEqual("PROHIBITED_ACTION", artifact["reason_code"])
                self.assertIn(path, artifact["prohibited_targets"])
                self.assertNotIn(path, artifact["files_write"])
                self.assert_artifact(artifact)

    def test_r7_mixed_payload_excludes_control_plane_but_keeps_safe_writes(self):
        payload = self.payload()
        payload["write_requirements"].append({
            "requirement_id": "control-plane-attempt",
            "candidates": [
                "tools/node_architect/audit_guardrail.py",
                "tools/node_architect/files_write_scope.py",
            ],
            "reason": "Attempt to broaden into control-plane plus safe evaluator.",
        })
        artifact = self.mod.render_files_write_scope(payload)
        # Control-plane path is excluded; the safe evaluator remains eligible for that
        # requirement, so the overall scope stays READY (no broadening of the gap).
        self.assertEqual("READY", artifact["outcome"])
        self.assertIn("tools/node_architect/audit_guardrail.py", artifact["prohibited_targets"])
        self.assertIn("tools/node_architect/audit_guardrail.py", artifact["files_exclude"])
        self.assertNotIn("tools/node_architect/audit_guardrail.py", artifact["files_write"])
        self.assert_artifact(artifact)

    def test_r7_negative_authority_holds_under_denial(self):
        for path in self.R7_PROHIBITED_EXACT:
            with self.subTest(path=path):
                artifact = self.mod.render_files_write_scope(self._sole_requirement_payload(path))
                self.assertTrue(artifact["authority_negative"])
                self.assertTrue(artifact["read_only_projection"])
                self.assertTrue(artifact["candidate_write_scope"])
                granted = [key for key in artifact if key.endswith("authority_granted")]
                self.assertTrue(granted, "expected authority_granted fields present")
                self.assertFalse(
                    any(artifact[key] for key in granted),
                    "no authority may be granted under denial",
                )
        ready = self.render()
        self.assertTrue(ready["authority_negative"])
        self.assertFalse(
            any(value for key, value in ready.items() if key.endswith("authority_granted"))
        )


if __name__ == "__main__":
    unittest.main()
