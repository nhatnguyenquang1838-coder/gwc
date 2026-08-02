import json
import tempfile
import unittest
from pathlib import Path
import importlib.util


VALIDATOR_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "node_architect"
    / "validate_node_catalog_intake_context.py"
)


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_intake_context", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def valid_node(slug: str) -> dict:
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
                "protected_base_sha": PROTECTED_BASE_SHA,
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
    elif slug == "risk-classification":
        node.update(
            {
                "intent": "Classify request risk before gate routing.",
                "outcome": "Typed risk_profile record with risk_level, risk_flags, required_gate, approval_requirements, reason_codes, source_bindings, and classified_at.",
                "constraints": [
                    "Equivalent intake facts must classify to the same risk_profile.",
                    "Missing, stale, ambiguous, or conflicting evidence must fail closed.",
                    "The node must not grant approval, execution, merge, deploy, or production authority.",
                    "The risk_profile schema must remain closed to undeclared fields.",
                ],
                "exclusions": [
                    "Merge, deploy, release, or production authority.",
                    "Credential, secret, migration, or destructive operations.",
                    "Mutating repository state or changing gate authority.",
                ],
                "entry_guards": [
                    "G0_CONTEXT",
                    "read_only",
                    "verified intake facts",
                ],
                "reason_codes": RISK_CLASSIFICATION_REASON_CODES,
                "risk_profile": {
                    "risk_level": "R2",
                    "risk_flags": [
                        "scope_ambiguous",
                        "source_stale",
                    ],
                    "required_gate": "G2_HUMAN_DIRECTION",
                    "approval_requirements": [
                        "Explicit human direction is required.",
                        "Verified source and protected-base evidence must be present.",
                    ],
                    "reason_codes": list(RISK_CLASSIFICATION_REASON_CODES.keys()),
                    "source_bindings": {
                        "request_intake": "intake_context.request-intake",
                        "source_resolution": "intake_context.source-resolution",
                        "repo_identity_check": "intake_context.repo-identity-check",
                        "protected_base_capture": "intake_context.protected-base-capture",
                        "repository": "nhatnguyenquang1838-coder/gwc",
                        "base_sha": PROTECTED_BASE_SHA,
                    },
                    "classified_at": "2026-08-01T00:00:00Z",
                },
            }
        )
    return node


PROTECTED_BASE_SHA = "5aea52a73cfcee02576766db4adf290a94212157"
RISK_CLASSIFICATION_REASON_CODES = {
    "RISK_PRODUCTION_OPERATION": "Production data, configuration, or operational scope is present.",
    "RISK_SECRET_CHANGE": "Credentials or secrets are present or would change.",
    "RISK_DESTRUCTIVE_OPERATION": "The request includes destructive or irreversible work.",
    "RISK_MIGRATION": "A migration or storage cutover is required.",
    "RISK_RELEASE_DEPLOYMENT": "A release or deployment action is required.",
    "RISK_SCOPE_AMBIGUOUS": "The requested scope is ambiguous or conflicting.",
    "RISK_SOURCE_STALE": "The evidence source is stale or no longer verified.",
    "RISK_UNCLASSIFIED": "The signal set cannot be classified deterministically.",
}


class IntakeContextNodeCatalogTests(unittest.TestCase):
    def setUp(self):
        self.validator = load_validator()

    def write_family(self, root: Path, nodes: list[dict]) -> Path:
        family_dir = root / "intake_context"
        family_dir.mkdir(parents=True, exist_ok=True)
        for node in nodes:
            slug = node["node_id"].split(".", 1)[1]
            (family_dir / f"{slug}.node.json").write_text(
                json.dumps(node, indent=2) + "\n",
                encoding="utf-8",
            )
        return family_dir

    def test_valid_nine_node_family_passes(self):
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
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), [valid_node(slug) for slug in slugs])
            self.assertEqual([], self.validator.validate_family(family_dir))

    def test_rejects_non_g0_gate(self):
        slugs = [f"node-{index}" for index in range(9)]
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0]["gates"] = ["G1_ALIGNMENT"]
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("gates must be exactly" in error for error in errors))

    def test_rejects_extra_node(self):
        slugs = [f"node-{index}" for index in range(10)]
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), [valid_node(slug) for slug in slugs])
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("expected exactly 9" in error for error in errors))

    def test_rejects_write_authority(self):
        slugs = [f"node-{index}" for index in range(9)]
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0]["authority_boundary"] = "g2_required"
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("read-only/none authority" in error for error in errors))

    def test_accepts_typed_intake_contract(self):
        """Test that request-intake with typed intake fields validates successfully."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0].update({
            "intent": "User-specified task scope.",
            "outcome": "Normalized typed intake record.",
            "constraints": ["Input must follow canonical request shape."],
            "exclusions": ["Production runtime behavior."],
            "entry_guards": ["G0_CONTEXT", "read_only"],
            "reason_codes": {"ACCEPTED": "Request normalized successfully."}
        })
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"Typed intake contract should validate: {errors}")

    def test_rejects_malformed_typed_fields(self):
        """Test that malformed typed intake fields are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0]["intent"] = 123
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("intent must be a string" in error for error in errors))

    def test_rejects_malformed_constraints(self):
        """Test that non-list or non-string constraints are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0]["constraints"] = "not a list"
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("constraints must be a list" in error for error in errors))

    def test_rejects_malformed_reason_codes(self):
        """Test that invalid reason_codes structures are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0]["reason_codes"] = {"key": "value", "nested": {"obj": "value"}}
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("reason_codes" in error for error in errors))

    def test_accepts_string_reason_code(self):
        """Test that string reason_codes are accepted."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0]["reason_codes"] = "ACCEPTED"
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"String reason_codes should validate: {errors}")

    def test_typed_fields_preserve_g0_gate_and_readonly(self):
        """Test that typed intake contract preserves G0_CONTEXT and read_only boundary."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[0].update({
            "intent": "Test intent.",
            "outcome": "Test outcome.",
            "constraints": [],
            "exclusions": [],
            "entry_guards": [],
            "reason_codes": {}
        })
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"G0 gate and read-only authority should persist: {errors}")

    def test_accepts_typed_risk_classification_contract(self):
        """Test that risk-classification with typed risk_profile fields validates successfully."""
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
        nodes = [valid_node(slug) for slug in slugs]
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"Typed risk-classification contract should validate: {errors}")

    def test_rejects_malformed_risk_profile(self):
        """Test that malformed risk_profile fields are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[4]["risk_profile"]["risk_level"] = 123
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("risk_profile.risk_level" in error for error in errors))

    def test_rejects_drifted_risk_reason_codes(self):
        """Test that unsupported risk reason codes are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[4]["risk_profile"]["reason_codes"] = [
            "RISK_PRODUCTION_OPERATION",
            "RISK_SOURCE_STALE",
            "RISK_UNKNOWN",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("unsupported values" in error for error in errors))

    def test_accepts_typed_protected_base_contract(self):
        """Test that protected-base capture with typed fields validates successfully."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[3].update(
            {
                "protected_base_sha": PROTECTED_BASE_SHA,
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
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"Typed protected-base contract should validate: {errors}")

    def test_rejects_malformed_protected_base_sha(self):
        """Test that malformed protected-base SHA values are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[3].update(
            {
                "protected_base_sha": 123,
                "evidence_source": "Verified source-of-truth readback.",
                "readback_status": "VERIFIED",
                "drift_state": "NONE",
                "reason_codes": {},
                "captured_at": "2026-07-31T00:00:00Z",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("protected_base_sha" in error for error in errors))

    def test_rejects_stale_protected_base_status(self):
        """Test that unsupported readback statuses are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[3].update(
            {
                "protected_base_sha": PROTECTED_BASE_SHA,
                "evidence_source": "Verified source-of-truth readback.",
                "readback_status": "BROKEN",
                "drift_state": "NONE",
                "reason_codes": {},
                "captured_at": "2026-07-31T00:00:00Z",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("readback_status" in error for error in errors))

    def test_rejects_malformed_protected_base_reason_codes(self):
        """Test that malformed protected-base reason_codes are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[3].update(
            {
                "protected_base_sha": PROTECTED_BASE_SHA,
                "evidence_source": "Verified source-of-truth readback.",
                "readback_status": "VERIFIED",
                "drift_state": "NONE",
                "reason_codes": {"nested": {"obj": "value"}},
                "captured_at": "2026-07-31T00:00:00Z",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("reason_codes" in error for error in errors))

    def test_typed_protected_base_fields_preserve_g0_gate_and_readonly(self):
        """Test that protected-base capture preserves G0_CONTEXT and read_only boundary."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[3].update(
            {
                "protected_base_sha": PROTECTED_BASE_SHA,
                "evidence_source": "Verified source-of-truth readback.",
                "readback_status": "VERIFIED",
                "drift_state": "NONE",
                "reason_codes": {},
                "captured_at": "2026-07-31T00:00:00Z",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"G0 gate and read-only authority should persist: {errors}")

    def test_source_resolution_accepts_typed_source_contract(self):
        """Test that source-resolution with typed source-resolution fields validates successfully."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[1].update({
            "intent": "Determine the authoritative source of active instructions.",
            "outcome": "Typed source-resolution record with mode, authority, provenance, and reason codes.",
            "constraints": [
                "Source mode must be deterministically resolved as REPO, PACKAGE, or MIXED.",
                "Fail closed when source authority cannot be distinguished."
            ],
            "exclusions": [
                "Production runtime behavior",
                "Deployment logic",
                "Migration logic"
            ],
            "entry_guards": [
                "G0_CONTEXT",
                "read_only"
            ],
            "reason_codes": {
                "ACCEPTED": "Source mode resolved deterministically with verified provenance.",
                "AMBIGUOUS": "Repository and package authority cannot be distinguished.",
                "MALFORMED": "Provenance evidence is incomplete or invalid.",
                "MISSING_EVIDENCE": "Required source inputs cannot be audited.",
                "INVALID_MODE": "Resolved source mode token is not REPO, PACKAGE, or MIXED."
            }
        })
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"Typed source-resolution contract should validate: {errors}")

    def test_source_resolution_rejects_malformed_reason_codes(self):
        """Test that malformed reason_codes in source-resolution are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[1]["reason_codes"] = {"key": {"nested": "object"}}
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("reason_codes" in error for error in errors))

    def test_source_resolution_rejects_malformed_constraints(self):
        """Test that malformed constraints in source-resolution are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[1]["constraints"] = "not a list"
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("constraints must be a list" in error for error in errors))

    def test_source_resolution_rejects_malformed_entry_guards(self):
        """Test that malformed entry_guards in source-resolution are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[1]["entry_guards"] = "not a list"
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("entry_guards must be a list" in error for error in errors))

    def test_source_resolution_rejects_malformed_exclusions(self):
        """Test that malformed exclusions in source-resolution are rejected."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[1]["exclusions"] = "not a list"
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertTrue(any("exclusions must be a list" in error for error in errors))

    def test_source_resolution_accepts_string_reason_code(self):
        """Test that string reason_codes in source-resolution are accepted."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[1]["reason_codes"] = "ACCEPTED"
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"String reason_codes should validate: {errors}")

    def test_files_read_scope_accepts_typed_scope_contract(self):
        """Test that files-read-scope with typed scope fields validates successfully."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[5].update(
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
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"Typed files-read-scope contract should validate: {errors}")

    def test_files_write_scope_accepts_typed_scope_contract(self):
        """Test that files-write-scope with typed scope fields validates successfully."""
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
        nodes = [valid_node(slug) for slug in slugs]
        nodes[6].update(
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
        with tempfile.TemporaryDirectory() as tmp:
            family_dir = self.write_family(Path(tmp), nodes)
            errors = self.validator.validate_family(family_dir)
            self.assertEqual([], errors, f"Typed files-write-scope contract should validate: {errors}")


if __name__ == "__main__":
    unittest.main()


class IntakeContextRuntimeContractLinkageTests(unittest.TestCase):
    def setUp(self):
        self.validator = load_validator()
        self.repo_root = Path(__file__).resolve().parents[1]

    def _copy_runtime_contract(self, root: Path) -> None:
        schema_target = root / "schemas/intake-card.schema.json"
        evaluator_target = root / "tools/node_architect/intake_card_render.py"
        schema_target.parent.mkdir(parents=True, exist_ok=True)
        evaluator_target.parent.mkdir(parents=True, exist_ok=True)
        schema_target.write_text(
            (self.repo_root / "schemas/intake-card.schema.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        evaluator_target.write_text(
            (self.repo_root / "tools/node_architect/intake_card_render.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def test_current_intake_card_runtime_contract_linkage_passes(self):
        self.assertEqual([], self.validator.validate_runtime_contracts(self.repo_root))

    def test_missing_runtime_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_runtime_contract(root)
            (root / "schemas/intake-card.schema.json").unlink()
            errors = self.validator.validate_runtime_contracts(root)
            self.assertTrue(any("runtime schema missing" in error for error in errors))

    def test_wrong_schema_artifact_type_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_runtime_contract(root)
            schema_path = root / "schemas/intake-card.schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema["properties"]["artifact_type"]["const"] = "wrong-artifact"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            errors = self.validator.validate_runtime_contracts(root)
            self.assertTrue(any("artifact_type" in error for error in errors))

    def test_missing_runtime_evaluator_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_runtime_contract(root)
            (root / "tools/node_architect/intake_card_render.py").unlink()
            errors = self.validator.validate_runtime_contracts(root)
            self.assertTrue(any("runtime evaluator missing" in error for error in errors))

    def test_missing_runtime_entrypoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._copy_runtime_contract(root)
            evaluator_path = root / "tools/node_architect/intake_card_render.py"
            evaluator_path.write_text("VALUE = 1\n", encoding="utf-8")
            errors = self.validator.validate_runtime_contracts(root)
            self.assertTrue(any("missing callable render_intake_card" in error for error in errors))
