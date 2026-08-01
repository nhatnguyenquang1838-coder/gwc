from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import validate as jsonschema_validate


ROOT = Path(__file__).resolve().parents[1]
READ_RENDERER = ROOT / "tools" / "node_architect" / "files_read_scope.py"
WRITE_RENDERER = ROOT / "tools" / "node_architect" / "files_write_scope.py"
READ_SCHEMA = ROOT / "schemas" / "bounded-read-scope.schema.json"
WRITE_SCHEMA = ROOT / "schemas" / "bounded-write-scope.schema.json"
VALIDATOR = ROOT / "tools" / "node_architect" / "validate_node_catalog_intake_context.py"


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_scope_family_node(slug: str) -> dict:
    node = {
        "node_id": f"intake_context.{slug}",
        "node_type": "workflow",
        "title": slug.replace("-", " ").title(),
        "canonical": "canonical",
        "authority_boundary": "read_only",
        "gates": ["G0_CONTEXT"],
        "description": f"{slug} validation fixture.",
    }
    if slug == "protected-base-capture":
        node.update(
            {
                "protected_base_sha": "5aea52a73cfcee02576766db4adf290a94212157",
                "evidence_source": "Verified source-of-truth readback.",
                "readback_status": "VERIFIED",
                "drift_state": "NONE",
                "reason_codes": {
                    "VERIFIED": "Captured protected base matches the verified source of truth.",
                    "MISMATCH": "Captured SHA does not match the verified source of truth.",
                    "STALE": "Captured SHA is stale relative to the current task context.",
                    "DRIFTED": "Protected base evidence drifted from the verified source of truth.",
                },
                "captured_at": "2026-07-31T00:00:00Z",
            }
        )
    if slug == "files-read-scope":
        node.update(
            {
                "intent": "Render the bounded read set for the current task from governance and task-specific inputs.",
                "outcome": "Deterministic files_read scope evidence with bounded provenance and reason codes.",
                "constraints": [
                    "Read scope must be derived from verified governance and task-specific inputs only.",
                    "Read scope must remain read-only and fail closed on missing evidence.",
                    "Read paths must stay within the repository boundary.",
                ],
                "exclusions": [
                    "Production runtime behavior.",
                    "Merge, deploy, release, or production-data operations.",
                    "Write paths and destructive side effects.",
                ],
                "entry_guards": ["G0_CONTEXT", "read_only authority_boundary"],
                "reason_codes": {
                    "ACCEPTED": "Required read scope rendered successfully.",
                    "MISSING_EVIDENCE": "Required read inputs are missing or incomplete.",
                    "MALFORMED_INPUT": "Read scope inputs are invalid or ambiguous.",
                    "SCOPE_DRIFT": "Requested read scope exceeds the bounded task envelope.",
                },
            }
        )
    if slug == "files-write-scope":
        node.update(
            {
                "intent": "Render the bounded write set and explicit exclusions for a later G2 execution envelope.",
                "outcome": "Deterministic files_write scope evidence with bounded write paths, excluded actions, and reason codes.",
                "constraints": [
                    "Write scope must be repo-relative and bounded to approved task files only.",
                    "Write scope must exclude protected-branch, merge, deploy, release, credential, migration, and production-data actions.",
                    "Write scope must fail closed when the candidate write set is empty or ambiguous.",
                ],
                "exclusions": [
                    "Direct push to protected branches.",
                    "Force push, branch deletion, or PR base changes.",
                    "Merge, auto-merge, deploy, release, production config, credentials, secrets, migration, and production data.",
                ],
                "entry_guards": ["G0_CONTEXT", "read_only authority_boundary"],
                "reason_codes": {
                    "ACCEPTED": "Required write scope rendered successfully.",
                    "EMPTY_SCOPE": "No bounded write paths were available for the task.",
                    "PROHIBITED_ACTION": "Candidate write scope includes a prohibited action or target.",
                    "MALFORMED_INPUT": "Write scope inputs are invalid or ambiguous.",
                    "SCOPE_DRIFT": "Requested write scope exceeds the bounded task envelope.",
                },
            }
        )
    if slug == "risk-classification":
        node.update(
            {
                "intent": "Classify the current intake evidence into a closed risk profile.",
                "outcome": "Deterministic risk_profile evidence with bounded gate and reason codes.",
                "constraints": [
                    "Risk classification must be deterministic for equivalent intake facts.",
                    "Risk classification must fail closed on missing or ambiguous evidence.",
                ],
                "exclusions": [
                    "No production, migration, credential, or release authority.",
                    "No writes, merges, or deployments.",
                ],
                "entry_guards": ["G0_CONTEXT", "read_only authority_boundary"],
                "reason_codes": {
                    "RISK_PRODUCTION_OPERATION": "The intake implies production data, configuration, or runtime change.",
                    "RISK_SECRET_CHANGE": "The intake implies credential or secret handling.",
                    "RISK_DESTRUCTIVE_OPERATION": "The intake implies a destructive write path.",
                    "RISK_MIGRATION": "The intake implies a migration or schema change.",
                    "RISK_RELEASE_DEPLOYMENT": "The intake implies deployment or release activity.",
                    "RISK_SCOPE_AMBIGUOUS": "The intake scope is not sufficiently bounded.",
                    "RISK_SOURCE_STALE": "The source evidence is stale or inconsistent.",
                    "RISK_UNCLASSIFIED": "The intake has no supported risk classification.",
                },
                "risk_profile": {
                    "risk_level": "R1",
                    "risk_flags": ["scope_ambiguous"],
                    "required_gate": "G2_AUTOMATIC_BOUNDED",
                    "approval_requirements": [
                        "Bounded G2 execution envelope required before any write.",
                    ],
                    "reason_codes": [
                        "RISK_SCOPE_AMBIGUOUS",
                        "RISK_UNCLASSIFIED",
                    ],
                    "source_bindings": {
                        "request_intake": "request-intake",
                        "source_resolution": "source-resolution",
                        "repo_identity_check": "repo-identity-check",
                        "protected_base_capture": "protected-base-capture",
                        "repository": "nhatnguyenquang1838-coder/gwc",
                        "base_sha": "5aea52a73cfcee02576766db4adf290a94212157",
                    },
                    "classified_at": "2026-08-01T00:00:00Z",
                },
            }
        )
    return node


class IntakeContextM4BatchB1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.read_renderer = load_module(READ_RENDERER, "files_read_scope_renderer")
        self.write_renderer = load_module(WRITE_RENDERER, "files_write_scope_renderer")
        self.validator = load_module(VALIDATOR, "intake_context_validator")
        self.read_schema = load_json(READ_SCHEMA)
        self.write_schema = load_json(WRITE_SCHEMA)

    def _family_dir(self, root: Path, nodes: list[dict]) -> Path:
        family_dir = root / "intake_context"
        family_dir.mkdir(parents=True, exist_ok=True)
        for node in nodes:
            slug = node["node_id"].split(".", 1)[1]
            (family_dir / f"{slug}.node.json").write_text(json.dumps(node, indent=2) + "\n", encoding="utf-8")
        return family_dir

    def _family_nodes(self) -> list[dict]:
        slugs = [
            "request-intake",
            "source-resolution",
            "repo-identity-check",
            "protected-base-capture",
            "risk-classification",
            "files-read-scope",
            "files-write-scope",
            "intake-card-render",
            "context-gap-escalation",
        ]
        return [build_scope_family_node(slug) for slug in slugs]

    def test_read_scope_renderer_canonicalizes_file_paths(self) -> None:
        payload = {
            "task_id": "SCRUM-180-181",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "base_sha": "78d596242a9e042d62d6174afc40aa4976eb3285",
            "branch": "codex/fastlane-scrum-180-181-intake-context-20260801",
            "governance_reads": [
                "AGENTS.md",
                "core/Coding_Project_Governance_v1.0.md",
                "AGENTS.md",
            ],
            "task_reads": [
                "projects/gwc/project-profile.yaml",
                "projects/gwc/project-profile.yaml",
            ],
        }
        rendered = self.read_renderer.render_files_read_scope(payload)
        self.assertEqual(
            rendered["files_read"],
            [
                "AGENTS.md",
                "core/Coding_Project_Governance_v1.0.md",
                "projects/gwc/project-profile.yaml",
            ],
        )
        jsonschema_validate(rendered, self.read_schema)

    def test_write_scope_renderer_canonicalizes_file_paths_and_actions(self) -> None:
        payload = {
            "task_id": "SCRUM-180-181",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "base_sha": "78d596242a9e042d62d6174afc40aa4976eb3285",
            "branch": "codex/fastlane-scrum-180-181-intake-context-20260801",
            "files_write": [
                "core/node-architect/node-catalog/intake_context/files-read-scope.node.json",
                "core/node-architect/node-catalog/intake_context/files-write-scope.node.json",
                "core/node-architect/node-catalog/intake_context/files-read-scope.node.json",
            ],
        }
        rendered = self.write_renderer.render_files_write_scope(payload)
        self.assertEqual(
            rendered["files_write"],
            [
                "core/node-architect/node-catalog/intake_context/files-read-scope.node.json",
                "core/node-architect/node-catalog/intake_context/files-write-scope.node.json",
            ],
        )
        self.assertIn("merge", rendered["excluded_actions"])
        self.assertIn("production_data", rendered["excluded_actions"])
        jsonschema_validate(rendered, self.write_schema)

    def test_renderers_reject_unsafe_paths(self) -> None:
        shared = {
            "task_id": "SCRUM-180-181",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "base_sha": "78d596242a9e042d62d6174afc40aa4976eb3285",
            "branch": "codex/fastlane-scrum-180-181-intake-context-20260801",
        }
        with self.assertRaises(ValueError):
            self.read_renderer.render_files_read_scope({**shared, "files_read": ["../escape.md"]})
        with self.assertRaises(ValueError):
            self.write_renderer.render_files_write_scope({**shared, "files_write": ["C:\\escape.md"]})

    def test_family_validator_accepts_typed_files_scope_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self._family_dir(Path(tmp), self._family_nodes())
            self.assertEqual([], self.validator.validate_family(family_dir))


# Compatibility aliases for the documented focused unittest entrypoints.
BoundedReadScopeTests = IntakeContextM4BatchB1Tests
BoundedWriteScopeTests = IntakeContextM4BatchB1Tests


if __name__ == "__main__":
    unittest.main()
