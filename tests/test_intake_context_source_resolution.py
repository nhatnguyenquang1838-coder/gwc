#!/usr/bin/env python3
"""Focused + neighbor regression tests for intake_context.source-resolution (SCRUM-299)."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/source-resolution.schema.json"
EVAL = ROOT / "tools/node_architect/source_resolution.py"
NEIGHBOR_EVAL = ROOT / "tools/node_architect/request_intake.py"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


M = _load_module("source_resolution", EVAL)
NEIGHBOR = _load_module("request_intake", NEIGHBOR_EVAL)

from jsonschema import Draft202012Validator

SCHEMA_OBJ = json.loads(SCHEMA.read_text(encoding="utf-8"))
Draft202012Validator.check_schema(SCHEMA_OBJ)
VALIDATOR = Draft202012Validator(SCHEMA_OBJ)

TASK = "SCRUM-299"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "e4840edf3c2c33a37695b92a97d667664720f905"
SHA_A = "1111111111111111111111111111111111111111"
SHA_B = "2222222222222222222222222222222222222222"
SHA_C = "3333333333333333333333333333333333333333"


def _cand(source_id, source_class, sha=SHA_A, *, ref="refs/heads/pre-prod", path=None,
          availability="AVAILABLE", verified=True, origin="git-object", **kw):
    candidate = {
        "source_id": source_id,
        "source_class": source_class,
        "path": path or f"{source_id}.md",
        "ref": ref,
        "sha": sha,
        "availability": availability,
        "provenance": {"origin": origin, "verified": verified},
    }
    candidate.update(kw)
    return candidate


def _repo_pair():
    return [
        _cand("AGENTS.md", "REPO_INSTRUCTION", SHA_A),
        _cand("core/Coding_Project_Governance_v1.0.md", "REPO_CORE_CONTRACT", SHA_B),
    ]


class SourceResolutionTests(unittest.TestCase):
    def _assert_valid(self, art):
        errors = sorted(VALIDATOR.iter_errors(art), key=lambda e: list(e.path))
        self.assertEqual([], [e.message for e in errors], msg=json.dumps(art, indent=2))
        for f in M.AUTH_FIELDS:
            self.assertFalse(art[f], f"{f} must be false")
        self.assertTrue(art["read_only_projection"])
        # Total routing: a non-accepted outcome always carries remediation.
        if art["outcome"] == "ACCEPTED":
            self.assertIsNone(art["remediation"])
        else:
            self.assertIsNotNone(art["remediation"])

    # --- EARS 1 / 5: precedence + exact binding + deterministic digest -------
    def test_accepted_repo_mode_binds_exact_refs(self):
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE, candidates=_repo_pair(),
        )
        self.assertEqual("ACCEPTED", art["outcome"])
        self.assertEqual("SOURCE_ACCEPTED", art["reason_code"])
        self.assertEqual("REPO", art["source_mode"])
        self.assertEqual("REPO_INSTRUCTION", art["authoritative_source"]["source_class"])
        self.assertEqual([10, 20], [b["precedence"] for b in art["selected_sources"]])
        for binding in art["selected_sources"]:
            self.assertRegex(binding["sha"], r"^[0-9a-f]{40}$")
            self.assertTrue(binding["ref"])
            self.assertTrue(binding["provenance_origin"])
        self.assertTrue(art["source_set_digest"].startswith("sha256:"))
        self.assertEqual(
            ["intake_context.repo-identity-check", "intake_context.context-gap-escalation"],
            art["next_allowed_nodes"],
        )
        self._assert_valid(art)

    def test_mixed_mode_orders_repo_before_package(self):
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE,
            candidates=_repo_pair() + [_cand("MANIFEST.json", "PACKAGE_MANIFEST", SHA_C)],
        )
        self.assertEqual("ACCEPTED", art["outcome"])
        self.assertEqual("MIXED", art["source_mode"])
        self.assertEqual(
            ["REPO_INSTRUCTION", "REPO_CORE_CONTRACT", "PACKAGE_MANIFEST"],
            [b["source_class"] for b in art["selected_sources"]],
        )
        self._assert_valid(art)

    def test_package_only_mode(self):
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE,
            candidates=[
                _cand("MANIFEST.json", "PACKAGE_MANIFEST", SHA_A),
                _cand("pkg/core/GATE.md", "PACKAGE_CORE_CONTRACT", SHA_B),
            ],
            mandatory_classes=["PACKAGE_MANIFEST"],
        )
        self.assertEqual("ACCEPTED", art["outcome"])
        self.assertEqual("PACKAGE", art["source_mode"])
        self._assert_valid(art)

    def test_declared_mode_conflict_is_invalid_mode(self):
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE, candidates=_repo_pair(),
            declared_mode="PACKAGE",
        )
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertEqual("SOURCE_INVALID_MODE", art["reason_code"])
        self.assertIsNone(art["authoritative_source"])
        self.assertEqual("BLOCK_G1_REVIEW", art["remediation"]["route"])
        self._assert_valid(art)

    # --- EARS 2: disagree / ambiguous / unavailable / unbound ---------------
    def test_conflicting_bindings_same_class_are_ambiguous(self):
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE,
            candidates=_repo_pair() + [_cand("AGENTS.md@fork", "REPO_INSTRUCTION", SHA_C)],
        )
        self.assertEqual("HUMAN_REQUIRED", art["outcome"])
        self.assertEqual("SOURCE_AMBIGUOUS_AUTHORITY", art["reason_code"])
        self.assertIsNone(art["authoritative_source"])
        reasons = {r["rejection_reason"] for r in art["rejected_alternatives"]}
        self.assertIn("CONFLICTING_BINDING", reasons)
        self.assertEqual("REQUEST_HUMAN_INPUT", art["remediation"]["route"])
        self._assert_valid(art)

    def test_missing_mandatory_class_blocks(self):
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE,
            candidates=[_cand("AGENTS.md", "REPO_INSTRUCTION", SHA_A)],
        )
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertEqual("SOURCE_MISSING_MANDATORY", art["reason_code"])
        self.assertIsNone(art["authoritative_source"])
        self._assert_valid(art)

    def test_unavailable_mandatory_source_is_pending_retry(self):
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE,
            candidates=[
                _cand("AGENTS.md", "REPO_INSTRUCTION", SHA_A),
                _cand("core/x.md", "REPO_CORE_CONTRACT", SHA_B, availability="UNAVAILABLE"),
            ],
        )
        self.assertEqual("PENDING", art["outcome"])
        self.assertEqual("SOURCE_UNAVAILABLE", art["reason_code"])
        self.assertEqual("RETRY_RESOLUTION", art["remediation"]["route"])
        self._assert_valid(art)

    def test_unknown_availability_never_passes(self):
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE,
            candidates=[
                _cand("AGENTS.md", "REPO_INSTRUCTION", SHA_A),
                _cand("core/x.md", "REPO_CORE_CONTRACT", SHA_B, availability="UNKNOWN"),
            ],
        )
        self.assertNotEqual("ACCEPTED", art["outcome"])
        self.assertEqual("SOURCE_UNAVAILABLE", art["reason_code"])
        self._assert_valid(art)

    def test_unbound_ref_blocks(self):
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE,
            candidates=[
                _cand("AGENTS.md", "REPO_INSTRUCTION", SHA_A),
                _cand("core/x.md", "REPO_CORE_CONTRACT", "not-a-sha"),
            ],
        )
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertEqual("SOURCE_UNBOUND_REF", art["reason_code"])
        reasons = {r["rejection_reason"] for r in art["rejected_alternatives"]}
        self.assertIn("UNBOUND_REF", reasons)
        self._assert_valid(art)

    def test_unverified_provenance_is_missing_evidence(self):
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE,
            candidates=[
                _cand("AGENTS.md", "REPO_INSTRUCTION", SHA_A),
                _cand("core/x.md", "REPO_CORE_CONTRACT", SHA_B, verified=False),
            ],
        )
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertEqual("SOURCE_MISSING_EVIDENCE", art["reason_code"])
        self._assert_valid(art)

    def test_malformed_inputs_fail_closed(self):
        art = M.render_source_resolution(
            task_id="", repository="bad repo", base_sha="xyz", candidates=[],
        )
        self.assertEqual("BLOCKED", art["outcome"])
        self.assertEqual("SOURCE_MALFORMED_INPUT", art["reason_code"])
        self.assertIsNone(art["source_mode"])
        self._assert_valid(art)

    def test_unknown_source_class_is_rejected_as_malformed_candidate(self):
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE,
            candidates=_repo_pair() + [_cand("mystery", "TELEPATHY", SHA_C)],
        )
        reasons = {r["rejection_reason"] for r in art["rejected_alternatives"]}
        self.assertIn("MALFORMED_CANDIDATE", reasons)
        # An unknown non-mandatory class is recorded, never silently promoted.
        self.assertEqual("ACCEPTED", art["outcome"])
        self.assertNotIn("TELEPATHY", [b["source_class"] for b in art["selected_sources"]])
        self._assert_valid(art)

    # --- EARS 3: precedence selection records rejected alternatives ---------
    def test_duplicate_identical_binding_recorded_not_duplicated(self):
        dup = _cand("AGENTS.md.copy", "REPO_INSTRUCTION", SHA_A, path="AGENTS.md")
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE,
            candidates=[_cand("AGENTS.md", "REPO_INSTRUCTION", SHA_A, path="AGENTS.md"), dup]
            + [_cand("core/x.md", "REPO_CORE_CONTRACT", SHA_B)],
        )
        self.assertEqual("ACCEPTED", art["outcome"])
        self.assertEqual(2, len(art["selected_sources"]))
        rejected = {r["source_id"]: r["rejection_reason"] for r in art["rejected_alternatives"]}
        self.assertEqual("DUPLICATE_IDENTICAL_BINDING", rejected["AGENTS.md.copy"])
        self._assert_valid(art)

    def test_lower_precedence_class_does_not_outrank_repo_instruction(self):
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE,
            candidates=[_cand("MANIFEST.json", "PACKAGE_MANIFEST", SHA_C)] + _repo_pair(),
        )
        self.assertEqual("AGENTS.md", art["authoritative_source"]["source_id"])
        self._assert_valid(art)

    # --- EARS 4: drift invalidates stale evidence ---------------------------
    def test_drifted_prior_binding_invalidates_and_refreshes(self):
        art = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE, candidates=_repo_pair(),
            prior_resolution={"source_set_digest": "sha256:" + "0" * 64,
                              "bindings": {"AGENTS.md": SHA_C}},
        )
        self.assertEqual("PENDING", art["outcome"])
        self.assertEqual("SOURCE_STALE_DRIFT", art["reason_code"])
        self.assertEqual("REFRESH_SOURCE", art["remediation"]["route"])
        self.assertEqual(
            [{"source_id": "AGENTS.md", "prior_sha": SHA_C, "current_sha": SHA_A}],
            art["invalidated_evidence"],
        )
        self.assertIsNone(art["authoritative_source"])
        self._assert_valid(art)

    # --- determinism / replay ----------------------------------------------
    def test_replay_is_deterministic_and_idempotent(self):
        kw = dict(task_id=TASK, repository=REPO, base_sha=BASE, candidates=_repo_pair())
        a = M.render_source_resolution(**kw)
        b = M.render_source_resolution(**kw)
        self.assertEqual(a["decision_digest"], b["decision_digest"])
        self.assertEqual(a["source_set_digest"], b["source_set_digest"])

        c = M.render_source_resolution(
            **kw, prior_resolution={"source_set_digest": a["source_set_digest"],
                                    "bindings": {"AGENTS.md": SHA_A}},
        )
        self.assertEqual("ACCEPTED", c["outcome"])
        self.assertEqual("SOURCE_REPLAY_IDEMPOTENT", c["reason_code"])
        self.assertEqual(a["source_set_digest"], c["source_set_digest"])
        self._assert_valid(c)

    def test_candidate_order_does_not_change_digest(self):
        forward = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE, candidates=_repo_pair())
        reverse = M.render_source_resolution(
            task_id=TASK, repository=REPO, base_sha=BASE, candidates=list(reversed(_repo_pair())))
        self.assertEqual(forward["source_set_digest"], reverse["source_set_digest"])
        self.assertEqual(forward["decision_digest"], reverse["decision_digest"])

    def test_routing_is_total_over_reason_taxonomy(self):
        self.assertEqual(set(M.REASONS), set(M.PRECEDENCE))
        for code in M.REASONS:
            if code in ("SOURCE_ACCEPTED", "SOURCE_REPLAY_IDEMPOTENT"):
                self.assertNotIn(code, M.ROUTING)
            else:
                self.assertIn(code, M.ROUTING)
                outcome, route = M.ROUTING[code]
                self.assertIn(outcome, {"BLOCKED", "PENDING", "HUMAN_REQUIRED"})
                self.assertTrue(M._stop_condition(route))

    # --- authority-negative --------------------------------------------------
    def test_no_route_grants_authority(self):
        cases = [
            M.render_source_resolution(task_id=TASK, repository=REPO, base_sha=BASE,
                                       candidates=_repo_pair()),
            M.render_source_resolution(task_id="", repository="x", base_sha="y", candidates=[]),
            M.render_source_resolution(task_id=TASK, repository=REPO, base_sha=BASE,
                                       candidates=[_cand("a", "REPO_INSTRUCTION", SHA_A)]),
        ]
        for art in cases:
            for f in M.AUTH_FIELDS:
                self.assertFalse(art[f])
            self._assert_valid(art)


class NeighborRegressionTests(unittest.TestCase):
    """intake_context.request-intake (SCRUM-298) must keep routing to this node."""

    def test_request_intake_still_accepts_and_routes_to_source_resolution(self):
        art = NEIGHBOR.render_request_intake(
            task_id="SCRUM-298", repository=REPO, base_sha=BASE,
            request={"raw_text": "Implement source-resolution node", "source": "USER",
                     "provenance": {"actor": "hermes-pc"},
                     "task_binding": "SCRUM-299", "repository_intent": REPO,
                     "requested_outcome": "Typed source-resolution record"},
        )
        self.assertEqual("ACCEPTED", art["outcome"])
        self.assertIn("intake_context.source-resolution", art["next_allowed_nodes"])
        for f in NEIGHBOR.AUTH_FIELDS:
            self.assertFalse(art[f])


if __name__ == "__main__":
    unittest.main()
