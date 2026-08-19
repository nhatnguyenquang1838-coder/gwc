#!/usr/bin/env python3
"""NA81 projection source-authority tests for SCRUM-346 (NA81-F6-N04).

Exercises ``decide_projection_source_authority`` in
``tools/node_architect/projection_source_authority_check.py`` for the
SCRUM-346 (NA81-F6-N04) gate ``sync_projection.projection-source-authority-check``.

The node already exists as a provenance-pinned executable (the deterministic,
read-only, fail-closed source-authority evaluator). This NA81 recert maturity PR
binds the #281 brief / Jira SCRUM-346 requirement matrix to deterministic tests
over the existing module and leaves the descriptor and source untouched
(provenance-SHA trap avoided):

* every projected field derives from an allowed CANONICAL source evidence -> READY
* projection-of-projection (field sourced from a PROJECTION authority class) -> BLOCKED
* stale source -> BLOCKED
* untrusted / inference-derived source -> BLOCKED
* missing / non-canonical source fails closed -> BLOCKED
* digest mismatch / revision drift fails closed -> BLOCKED
* conflicts (duplicate ref) fail closed -> BLOCKED
* invalid input fails closed -> BLOCKED
* deterministic digest / replay idempotency
* non-authoritative: read-only projection, every authority grant fixed False
* every decision validates against the closed decision schema

Imported via an absolute ``tools/`` path insertion so ``import
node_architect...`` resolves under ``python -m unittest discover`` from the
repository root (PEP 420 namespace packages).
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import node_architect.projection_source_authority_check as psac  # noqa: E402

try:
    import jsonschema
    from jsonschema import Draft202012Validator

    _SCHEMA = json.loads(
        Path("schemas/projection-source-authority-decision.schema.json").read_text(encoding="utf-8")
    )
    _VALIDATOR = Draft202012Validator(_SCHEMA)
except Exception:  # pragma: no cover - schema validation best-effort in this suite
    _VALIDATOR = None

TASK_ID = "SCRUM-346"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
PROJECTION_TARGET = "ds-admin"
REVISION_A = "d9a89a002aae4348359cd88810a9d03926199597"
REVISION_B = "e9a89a002aae4348359cd88810a9d03926199598"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
OBSERVED_AT = "2026-08-04T17:00:00Z"
EVAL_AT = "2026-08-04T17:10:00Z"
READBACK_AT = "2026-08-04T17:05:00Z"
FRESHNESS = {"max_source_age_seconds": 3600, "max_readback_age_seconds": 3600}


def _canonical_binding(ref="jira:SCRUM-346", revision=REVISION_A, digest=DIGEST_A, status="VERIFIED",
                       observed_at=OBSERVED_AT):
    return {
        "source_type": "TASK_RECORD",
        "authority_class": "CANONICAL",
        "ref": ref,
        "revision": revision,
        "content_digest": digest,
        "observed_at": observed_at,
        "status": status,
    }


def _projection_binding(ref="proj:ds-admin", revision=REVISION_A, digest=DIGEST_A, status="VERIFIED"):
    return {
        "source_type": "REPOSITORY",
        "authority_class": "PROJECTION",
        "ref": ref,
        "revision": revision,
        "content_digest": digest,
        "observed_at": OBSERVED_AT,
        "status": status,
    }


def _field_evidence(field_path="/task/status", source_ref="jira:SCRUM-346", revision=REVISION_A,
                     digest=DIGEST_A, derivation="DIRECT", rule_id=None):
    ev = {
        "field_path": field_path,
        "source_ref": source_ref,
        "source_revision": revision,
        "evidence_digest": digest,
        "derivation": derivation,
    }
    if rule_id is not None:
        ev["derivation_rule_id"] = rule_id
    return ev


def _current(revision=REVISION_A, ref="jira:SCRUM-346"):
    return {"ref": ref, "revision": revision, "observed_at": READBACK_AT}


def valid_args(**overrides):
    payload = dict(
        task_id=TASK_ID,
        repository=REPOSITORY,
        projection_target=PROJECTION_TARGET,
        requested_fields=["/task/status"],
        source_bindings=[_canonical_binding()],
        field_evidence=[_field_evidence()],
        current_revisions=[_current()],
        freshness_policy=dict(FRESHNESS),
        observed_at=EVAL_AT,
    )
    payload.update(overrides)
    return payload


def decide(**overrides):
    return psac.decide_projection_source_authority(**valid_args(**overrides))


class ProjectionSourceAuthorityNa81Tests(unittest.TestCase):
    # --- 1. canonical-derived field -> READY ----------------------------
    def test_canonical_field_ready(self):
        res = decide()
        self.assertEqual(res["outcome"], "READY")
        self.assertEqual(res["authority_status"], "CONFIRMED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_AUTHORITY_CONFIRMED")
        self.assertEqual(res["reason_codes"], ["PROJECTION_SOURCE_AUTHORITY_CONFIRMED"])

    def test_canonical_field_multiple_fields_ready(self):
        res = decide(
            requested_fields=["/task/status", "/task/assignee"],
            field_evidence=[
                _field_evidence(field_path="/task/status"),
                _field_evidence(field_path="/task/assignee"),
            ],
        )
        self.assertEqual(res["outcome"], "READY")
        self.assertEqual(len(res["field_authority"]), 2)

    # --- deterministic DETERMINISTIC_DERIVATION with a known rule id ---
    def test_deterministic_derivation_with_known_rule_ready(self):
        res = decide(
            field_evidence=[_field_evidence(derivation="DETERMINISTIC_DERIVATION",
                                            digest=DIGEST_A,
                                            rule_id="canonical-scalar-v1")],
        )
        # DETERMINISTIC_DERIVATION bound to a known rule id is verified -> READY.
        self.assertEqual(res["outcome"], "READY")

    def test_deterministic_derivation_without_rule_id_unverified(self):
        # A DETERMINISTIC_DERIVATION claim carrying no known derivation_rule_id
        # must fail closed (unverified derivation).
        res = decide(
            field_evidence=[_field_evidence(derivation="DETERMINISTIC_DERIVATION",
                                            digest=DIGEST_A)],
        )
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_DERIVATION_UNVERIFIED")

    # --- 2. projection-of-projection fails closed -----------------------
    def test_projection_of_projection_blocked(self):
        # A CANONICAL source exists (so CANONICAL_MISSING does not fire), but the
        # requested field is bound to a PROJECTION authority class source -> illegal
        # projection-of-projection.
        res = decide(
            source_bindings=[_canonical_binding(), _projection_binding(ref="proj:ds-admin")],
            field_evidence=[_field_evidence(source_ref="proj:ds-admin")],
            current_revisions=[_current(), _current(ref="proj:ds-admin")],
        )
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_AUTHORITY_INVALID")
        self.assertEqual(res["authority_status"], "REJECTED")

    # --- 3. stale source fails closed -----------------------------------
    def test_stale_source_blocked(self):
        res = decide(
            source_bindings=[_canonical_binding(status="STALE")],
        )
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_STALE")

    def test_source_older_than_freshness_policy_blocked(self):
        stale_args = valid_args(
            source_bindings=[_canonical_binding(observed_at="2026-08-04T10:00:00Z")],
        )
        res = psac.decide_projection_source_authority(**stale_args)
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_STALE")

    # --- 4. untrusted / inferred source fails closed --------------------
    def test_inferred_derivation_rejected(self):
        res = decide(
            field_evidence=[_field_evidence(derivation="INFERRED")],
        )
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_INFERRED_STATUS_REJECTED")

    def test_probabilistic_derivation_rejected(self):
        res = decide(
            field_evidence=[_field_evidence(derivation="PROBABILISTIC")],
        )
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_INFERRED_STATUS_REJECTED")

    # --- missing / non-canonical source fails closed --------------------
    def test_canonical_missing_blocked(self):
        # Only a PROJECTION binding present; no CANONICAL source.
        res = decide(
            source_bindings=[_projection_binding()],
            field_evidence=[_field_evidence(source_ref="proj:ds-admin")],
            current_revisions=[_current(ref="proj:ds-admin")],
        )
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_CANONICAL_MISSING")

    def test_canonical_source_status_missing_blocked(self):
        res = decide(
            source_bindings=[_canonical_binding(status="MISSING")],
        )
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_CANONICAL_MISSING")

    def test_field_unbound_blocked(self):
        # No field evidence for the requested field.
        res = decide(field_evidence=[])
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_FIELD_UNBOUND")

    def test_field_bound_to_missing_source_blocked(self):
        # Evidence references a ref that has no binding at all. The engine reports
        # both the authority violation (no canonical binding for that ref) and the
        # unbound field; the primary reason by precedence is AUTHORITY_INVALID.
        res = decide(
            field_evidence=[_field_evidence(source_ref="jira:SCRUM-999")],
            current_revisions=[_current(ref="jira:SCRUM-999")],
        )
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_AUTHORITY_INVALID")
        self.assertIn("PROJECTION_SOURCE_FIELD_UNBOUND", res["reason_codes"])

    # --- 5. digest mismatch / revision drift fails closed ---------------
    def test_digest_mismatch_blocked(self):
        res = decide(
            field_evidence=[_field_evidence(digest=DIGEST_B)],
        )
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_DIGEST_MISMATCH")

    def test_revision_drift_blocked(self):
        # Current readback revision differs from the canonical binding revision.
        res = decide(current_revisions=[_current(revision=REVISION_B)])
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_REVISION_DRIFT")

    # --- 6. conflicts fail closed ----------------------------------------
    def test_duplicate_ref_conflict_blocked(self):
        res = decide(
            source_bindings=[
                _canonical_binding(ref="jira:SCRUM-346", revision=REVISION_A),
                _canonical_binding(ref="jira:SCRUM-346", revision=REVISION_B),
            ],
        )
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_CONFLICT")

    def test_ambiguous_source_status_conflict_blocked(self):
        res = decide(source_bindings=[_canonical_binding(status="AMBIGUOUS")])
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertIn("PROJECTION_SOURCE_CONFLICT", res["reason_codes"])

    # --- 7. invalid input fails closed -----------------------------------
    def test_invalid_task_id_blocked(self):
        res = decide(task_id="not-a-task")
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_INPUT_INVALID")

    def test_invalid_repository_blocked(self):
        for repo in ("not a/repo", "myrepo", "a//b"):
            with self.subTest(repo=repo):
                res = decide(repository=repo)
                self.assertEqual(res["outcome"], "BLOCKED")
                self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_INPUT_INVALID")

    def test_invalid_freshness_policy_blocked(self):
        res = decide(freshness_policy={"only_one_key": 1})
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_INPUT_INVALID")

    def test_empty_requested_fields_blocked(self):
        res = decide(requested_fields=[])
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "PROJECTION_SOURCE_FIELDS_EMPTY")

    # --- 8. deterministic / replay ---------------------------------------
    def test_replay_deterministic(self):
        r1 = decide()
        r2 = decide()
        self.assertEqual(r1["decision_digest"], r2["decision_digest"])

    def test_digest_stable_across_field_ordering(self):
        a = decide(
            requested_fields=["/task/status", "/task/assignee"],
            field_evidence=[
                _field_evidence(field_path="/task/status"),
                _field_evidence(field_path="/task/assignee"),
            ],
        )
        b = decide(
            requested_fields=["/task/assignee", "/task/status"],
            field_evidence=[
                _field_evidence(field_path="/task/assignee"),
                _field_evidence(field_path="/task/status"),
            ],
        )
        self.assertEqual(a["decision_digest"], b["decision_digest"])

    # --- 9. non-authoritative --------------------------------------------
    def test_projection_non_authoritative(self):
        res = decide()
        self.assertTrue(res["read_only_projection"])
        for key in (
            "write_authority_granted",
            "approval_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(res[key], key)
        self.assertEqual(res["artifact_type"], "projection-source-authority-decision")
        self.assertEqual(res["schema_version"], "1.0")

    # --- 10. schema-valid output -----------------------------------------
    def test_ready_decision_matches_schema(self):
        res = decide()
        if _VALIDATOR is not None:
            _VALIDATOR.validate(res)

    def test_blocked_decision_matches_schema(self):
        res = decide(field_evidence=[])
        if _VALIDATOR is not None:
            _VALIDATOR.validate(res)

    def test_all_scenarios_match_schema(self):
        if _VALIDATOR is None:
            self.skipTest("jsonschema unavailable")
        scenarios = [
            {},
            {"source_bindings": [_projection_binding()],
             "field_evidence": [_field_evidence(source_ref="proj:ds-admin")],
             "current_revisions": [_current(ref="proj:ds-admin")]},
            {"source_bindings": [_canonical_binding(status="STALE")]},
            {"field_evidence": [_field_evidence(derivation="INFERRED")]},
            {"field_evidence": [_field_evidence(digest=DIGEST_B)]},
            {"current_revisions": [_current(revision=REVISION_B)]},
            {"field_evidence": []},
            {"task_id": "not-a-task"},
        ]
        for sc in scenarios:
            with self.subTest(sc=list(sc)):
                _VALIDATOR.validate(decide(**sc))

    # --- defense-in-depth: no mutation of inputs -------------------------
    def test_inputs_not_mutated(self):
        args = valid_args()
        snapshot = deepcopy(args)
        psac.decide_projection_source_authority(**args)
        self.assertEqual(args, snapshot)


if __name__ == "__main__":
    unittest.main()
