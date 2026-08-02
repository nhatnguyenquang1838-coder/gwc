import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTEXT_PATH = REPO_ROOT / "tools" / "node_architect" / "context_gap_escalation.py"
CARD_PATH = REPO_ROOT / "tools" / "node_architect" / "intake_card_render.py"
TASK = "SCRUM-183"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "65c93c5927013c750631933495c5ecb5e22fae88"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


context_gap = load(CONTEXT_PATH, "context_gap_escalation")
card_render = load(CARD_PATH, "intake_card_render")


class IntakeContextM4BatchB2Tests(unittest.TestCase):
    def upstream(self, *, read_outcome="READY", files_missing=None, write_risk="R2", secret=False):
        files_missing = files_missing or []
        request = {
            "schema_version": "1.0",
            "artifact_type": "request-contract",
            "task_id": TASK,
            "repository": REPO,
            "base_sha": BASE,
            "revision": "request/v1",
            "intent": "implement context gap escalation",
            "outcome": "context_gap_decision",
            "constraints": ["read only evaluator"],
            "exclusions": ["merge", "deploy"],
        }
        if secret:
            request["client_secret"] = "[REDACTED]"
        source = {
            "schema_version": "1.0",
            "artifact_type": "source-resolution",
            "task_id": TASK,
            "repository": REPO,
            "base_sha": BASE,
            "revision": "source/v1",
            "source_mode": "REPO",
            "source_bindings": [
                {"source_type": "REPO", "ref": "main", "revision": BASE, "status": "VERIFIED"}
            ],
            "outcome": "READY",
        }
        repo = {
            "schema_version": "1.0",
            "artifact_type": "repo-identity",
            "task_id": TASK,
            "repository": REPO,
            "base_sha": BASE,
            "revision": "repo/v1",
            "default_branch": "main",
            "protected_branch": "main",
            "outcome": "READY",
        }
        protected = {
            "schema_version": "1.0",
            "artifact_type": "protected-base-snapshot",
            "task_id": TASK,
            "repository": REPO,
            "base_sha": BASE,
            "revision": "base/v1",
            "protected_base_sha": BASE,
            "outcome": "READY",
        }
        risk = {
            "schema_version": "1.0",
            "artifact_type": "risk-profile",
            "task_id": TASK,
            "repository": REPO,
            "base_sha": BASE,
            "source_bindings": source["source_bindings"],
            "outcome": "READY",
            "risk_level": write_risk,
            "risk_flags": ["workflow_change"],
            "required_gate": "G2_EXECUTION",
            "additional_authority_gates": ["G6_PRODUCTION_DATA"] if write_risk == "R3" else [],
            "reason_code": "RISK_CLASSIFIED_R2",
            "reason_codes": ["RISK_CLASSIFIED_R2"],
            "classified_at": "2026-08-02T16:01:00Z",
            "read_only_projection": True,
            "write_authority_granted": False,
            "merge_authority_granted": False,
            "deployment_authority_granted": False,
            "production_authority_granted": False,
            "approval_requirements": ["G2 execution approval"],
            "decision_digest": "pending",
        }
        risk["decision_digest"] = card_render.compute_risk_decision_digest(risk)
        read_scope = {
            "schema_version": "1.0",
            "artifact_type": "bounded-read-scope",
            "task_id": TASK,
            "repository": REPO,
            "base_sha": BASE,
            "source_bindings": source["source_bindings"],
            "entries": [],
            "include_paths": ["schemas/intake-card.schema.json"],
            "exclude_paths": [],
            "missing_required_files": files_missing,
            "connector_status": "CONFIRMED",
            "repository_readback_status": "CONFIRMED" if files_missing else "NOT_ATTEMPTED",
            "validator_status": "PASS",
            "outcome": read_outcome,
            "failure_classification": "REPOSITORY_EVIDENCE_MISSING" if files_missing else "NONE",
            "reason_code": "READ_REPOSITORY_EVIDENCE_MISSING" if files_missing else "READ_SCOPE_RESOLVED",
            "reason_codes": ["READ_REPOSITORY_EVIDENCE_MISSING"] if files_missing else ["READ_SCOPE_RESOLVED"],
            "observed_at": "2026-08-02T16:01:00Z",
            "read_only_projection": True,
            "write_authority_granted": False,
            "merge_authority_granted": False,
            "deployment_authority_granted": False,
            "production_authority_granted": False,
            "files_read": ["schemas/intake-card.schema.json"],
            "files_exclude": [],
            "files_missing": files_missing,
            "scope_hash": "pending",
        }
        read_scope["scope_hash"] = card_render.compute_scope_digest(read_scope)
        write_scope = {
            "schema_version": "1.0",
            "artifact_type": "bounded-write-scope",
            "task_id": TASK,
            "repository": REPO,
            "base_sha": BASE,
            "risk_profile_digest": risk["decision_digest"],
            "risk_level": write_risk,
            "source_bindings": source["source_bindings"],
            "allowed_changes": [],
            "allowed_paths": ["tools/node_architect/context_gap_escalation.py"],
            "excluded_paths": [],
            "prohibited_operations": ["MERGE", "DEPLOY", "PRODUCTION_DATA_WRITE"],
            "proposed_branch": None,
            "branch_binding_status": "REQUIRED_AT_G2",
            "outcome": "READY",
            "reason_code": "WRITE_SCOPE_PROPOSED",
            "reason_codes": ["WRITE_SCOPE_PROPOSED"],
            "authority_required": "G2_EXECUTION",
            "additional_authority_gates": ["G6_PRODUCTION_DATA"] if write_risk == "R3" else [],
            "observed_at": "2026-08-02T16:01:00Z",
            "read_only_projection": True,
            "write_authority_granted": False,
            "commit_authority_granted": False,
            "push_authority_granted": False,
            "pr_authority_granted": False,
            "merge_authority_granted": False,
            "deployment_authority_granted": False,
            "production_authority_granted": False,
            "candidate_paths": ["tools/node_architect/context_gap_escalation.py"],
            "exclusions": [],
            "required_authority_gates": ["G2_EXECUTION"] + (["G6_PRODUCTION_DATA"] if write_risk == "R3" else []),
            "scope_hash": "pending",
        }
        write_scope["scope_hash"] = card_render.compute_scope_digest(write_scope)
        return request, source, repo, protected, risk, read_scope, write_scope

    def render_card(self, **kwargs):
        request, source, repo, protected, risk, read_scope, write_scope = self.upstream(**kwargs)
        return card_render.render_intake_card(
            task_id=TASK,
            repository=REPO,
            base_sha=BASE,
            request_contract=request,
            source_resolution=source,
            repo_identity=repo,
            protected_base_snapshot=protected,
            risk_profile=risk,
            bounded_read_scope=read_scope,
            bounded_write_scope=write_scope,
            redaction_directives=[],
            created_at="2026-08-02T16:01:00Z",
        )

    def decide(self, card, **overrides):
        payload = dict(
            task_id=TASK,
            repository=REPO,
            base_sha=BASE,
            intake_card=card,
            current_base_sha=BASE,
            available_evidence_keys=context_gap.collect_required_evidence(card),
            confirmed_missing_evidence_keys=[],
            connector_status="CONFIRMED",
            repository_readback_status="CONFIRMED",
            ci_required=True,
            ci_status="SUCCESS",
            validator_status="PASS",
            observed_at="2026-08-02T16:01:00Z",
        )
        payload.update(overrides)
        return context_gap.decide_context_gap_escalation(**payload)

    def test_ready_b1_artifacts_to_card_to_family_verification_route(self):
        card = self.render_card()
        decision = self.decide(card)
        self.assertEqual("READY", card["outcome"])
        self.assertEqual("READY", decision["outcome"])
        self.assertEqual("READY_FOR_FAMILY_VERIFICATION", decision["preparation_block"]["route"])

    def test_blocked_read_scope_to_agent_preparation_route(self):
        card = self.render_card(read_outcome="BLOCKED", files_missing=["core/missing.md"])
        decision = self.decide(
            card,
            available_evidence_keys=[key for key in context_gap.collect_required_evidence(card) if key != "path:core/missing.md"],
            connector_status="ERROR",
        )
        self.assertEqual("BLOCKED", card["outcome"])
        self.assertEqual("AGENT_PREPARATION_BLOCKED", decision["preparation_block"]["classification"])
        self.assertEqual("RETRY_SOURCE_READBACK", decision["preparation_block"]["route"])

    def test_confirmed_repository_omission_to_repository_evidence_route(self):
        card = self.render_card(read_outcome="BLOCKED", files_missing=["core/missing.md"])
        decision = self.decide(
            card,
            available_evidence_keys=[key for key in context_gap.collect_required_evidence(card) if key != "path:core/missing.md"],
            confirmed_missing_evidence_keys=["path:core/missing.md"],
        )
        self.assertEqual("REPOSITORY_EVIDENCE_MISSING", decision["preparation_block"]["classification"])
        self.assertEqual("READ_REQUIRED_EVIDENCE", decision["preparation_block"]["route"])

    def test_stale_base_after_card_render_to_recapture_route(self):
        card = self.render_card()
        decision = self.decide(card, current_base_sha="1" * 40)
        self.assertEqual("RECAPTURE_PROTECTED_BASE", decision["preparation_block"]["route"])
        self.assertEqual("CONTEXT_BASE_STALE", decision["reason_code"])

    def test_redacted_card_does_not_leak_raw_protected_values(self):
        card = self.render_card(secret=True)
        rendered = str(card)
        self.assertNotIn("super-secret", rendered)
        decision = self.decide(card)
        self.assertNotIn("super-secret", str(decision))
        self.assertFalse(decision["production_authority_granted"])

    def test_r3_later_gate_projection_remains_non_authority(self):
        card = self.render_card(write_risk="R3")
        decision = self.decide(card)
        self.assertIn("G6_PRODUCTION_DATA", card["risk_projection"]["additional_authority_gates"])
        self.assertEqual("READY", decision["outcome"])
        self.assertFalse(decision["production_authority_granted"])
        self.assertFalse(decision["merge_authority_granted"])


if __name__ == "__main__":
    unittest.main()
