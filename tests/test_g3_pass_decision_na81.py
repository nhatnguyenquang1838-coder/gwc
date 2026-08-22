#!/usr/bin/env python3
"""NA81 g3-pass-decision tests for SCRUM-342 (NA81-F5-N09).

Exercises the SCRUM-342 (NA81-F5-N09) ``decide_g3_pass_na81`` layer over the
existing ``decide_g3_pass`` G3 renderer (SCRUM-219). Maps every current-brief
requirement to code + tests:

* deterministic render
* replay / idempotency (na81_decision_digest stable across identical inputs)
* fail-closed on rejected evidence (EVIDENCE_REJECTED)
* fail-closed on head-drift evidence (HEAD_DRIFT)
* fail-closed on missing evidence (REQUIRED_EVIDENCE_MISSING)
* explicit authority boundary (no merge/approval/deploy/production grants)
* explicit non-authoritative guarantee

Imported via an absolute ``tools/`` path insertion so ``import
node_architect...`` resolves under ``python -m unittest discover`` from the
repository root (PEP 420 namespace packages).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import node_architect.g3_pass_decision as g3  # noqa: E402

TASK_ID = "SCRUM-342"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
BRANCH = "auto/SCRUM-342-na81-recert-20260814-r10"
BASE_SHA = "3e6ad57cf4326c9c04b0ee57c43538684cb026db"
HEAD_SHA = "9f2c1a7b4e0d5c3f8a6b1e2d4c5f60718293a4b5"
SCOPE_HASH = "sha256:" + "a1" * 32
GRAPH_REVISION = "g3-graph-20260814"
POLICY_DIGEST = "sha256:" + "b2" * 32
IDEMPOTENCY_KEY = "na81-g3-pass-decision-SCRUM-342-r10"


def _digest(payload):
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _valid_evidence(**overrides):
    ev = {
        "task_id": TASK_ID,
        "repository": REPOSITORY,
        "branch": BRANCH,
        "base_sha": BASE_SHA,
        "head_sha": HEAD_SHA,
        "scope_hash": SCOPE_HASH,
        "graph_revision": GRAPH_REVISION,
        "policy_digest": POLICY_DIGEST,
        "idempotency_key": IDEMPOTENCY_KEY,
        "evidence_quality_decision": {
            "status": "PASS",
            "reason_codes": ["EVIDENCE_ACCEPTED"],
            "task_id": TASK_ID,
            "repository": REPOSITORY,
            "branch": BRANCH,
            "head_sha": HEAD_SHA,
            "scope_hash": SCOPE_HASH,
            "graph_revision": GRAPH_REVISION,
            "quality_digest": _digest({"q": 1}),
        },
        "validations": [
            {
                "status": "PASS",
                "head_sha": HEAD_SHA,
                "scope_hash": SCOPE_HASH,
                "digest": _digest({"v": 1}),
            },
        ],
        "ready_for_review": {
            "eligible": True,
            "head_sha": HEAD_SHA,
            "scope_drift": False,
            "unresolved_threads": 0,
        },
        "findings": [],
    }
    ev.update(overrides)
    return ev


def _decide(**overrides):
    return g3.decide_g3_pass_na81(_valid_evidence(**overrides))


class G3PassDecisionNa81Tests(unittest.TestCase):
    # --- 1. deterministic render ----------------------------------------
    def test_deterministic_render(self):
        r1 = _decide()
        r2 = _decide()
        self.assertEqual(r1["outcome"], g3.G3_PASS)
        self.assertEqual(r2["outcome"], g3.G3_PASS)
        self.assertEqual(r1["decision_digest"], r2["decision_digest"])
        self.assertEqual(r1["na81_decision_digest"], r2["na81_decision_digest"])
        self.assertTrue(r1["na81"]["deterministic"])
        self.assertTrue(r2["na81"]["deterministic"])

    # --- 2. replay / idempotency ----------------------------------------
    def test_replay_idempotent(self):
        cache: dict = {}
        r1 = g3.decide_g3_pass_na81(_valid_evidence(), replay_cache=cache)
        r2 = g3.decide_g3_pass_na81(_valid_evidence(), replay_cache=cache)
        # second identical call is served from the replay cache
        self.assertTrue(r2["replayed"])
        self.assertTrue(r2["na81"]["idempotent"])
        # identical inputs -> identical NA81 decision digest
        self.assertEqual(r1["na81_decision_digest"], r2["na81_decision_digest"])
        self.assertEqual(r1["decision_digest"], r2["decision_digest"])

    # --- 3. fail-closed on rejected evidence ----------------------------
    def test_fail_closed_evidence_rejected(self):
        # corrupt base_sha so the core rejects the evidence
        res = _decide(base_sha="NOT-A-SHA")
        self.assertTrue(res["na81"]["fail_closed"])
        self.assertEqual(res["outcome"], g3.G3_BLOCKED)
        self.assertIn("EVIDENCE_REJECTED", res["reason_codes"])
        self.assertEqual(res["decision"]["outcome"], g3.G3_BLOCKED)

    def test_fail_closed_quality_not_pass(self):
        res = _decide(evidence_quality_decision={"status": "FAIL", "reason_codes": ["EVIDENCE_REJECTED"]})
        self.assertTrue(res["na81"]["fail_closed"])
        self.assertEqual(res["outcome"], g3.G3_BLOCKED)
        self.assertEqual(res["decision"]["outcome"], g3.G3_BLOCKED)

    # --- 4. fail-closed on head-drift evidence --------------------------
    def test_fail_closed_head_drift(self):
        # validation head_sha differs from identity head_sha -> HEAD_DRIFT
        res = _decide(validations=[{"status": "PASS", "head_sha": "0" * 40, "scope_hash": SCOPE_HASH}])
        self.assertTrue(res["na81"]["fail_closed"])
        self.assertEqual(res["outcome"], g3.G3_BLOCKED)
        self.assertIn("HEAD_DRIFT", res["reason_codes"])

    # --- 5. fail-closed on missing evidence -----------------------------
    def test_missing_evidence_blocked(self):
        # drop the idempotency_key so required identity evidence is missing
        ev = _valid_evidence()
        del ev["idempotency_key"]
        res = g3.decide_g3_pass_na81(ev)
        self.assertTrue(res["na81"]["fail_closed"])
        self.assertEqual(res["outcome"], g3.G3_BLOCKED)
        self.assertIn("REQUIRED_EVIDENCE_MISSING", res["reason_codes"])

    def test_missing_validations_blocked(self):
        res = _decide(validations=[])
        self.assertTrue(res["na81"]["fail_closed"])
        self.assertEqual(res["outcome"], g3.G3_BLOCKED)
        self.assertIn("REQUIRED_EVIDENCE_MISSING", res["reason_codes"])

    # --- 6. explicit authority boundary --------------------------------
    def test_explicit_authority_boundary(self):
        res = _decide()
        # NA81 never grants merge / deployment / production authority
        self.assertFalse(res["merge_authority_granted"])
        self.assertFalse(res["deployment_authority_granted"])
        self.assertFalse(res["production_authority_granted"])
        self.assertFalse(res["approval_authority_granted"])
        # and the embedded core decision carries the same closed boundary
        self.assertFalse(res["decision"]["merge_authority_granted"])
        self.assertFalse(res["decision"]["deployment_authority_granted"])
        self.assertFalse(res["decision"]["production_authority_granted"])
        # explicit non-authoritative guarantee is surfaced
        self.assertTrue(res["na81"]["non_authoritative"])
        self.assertFalse(res["na81"]["approval_authority_granted"])
        self.assertEqual(
            res["na81"]["authority_boundary"],
            {"merge_authority_granted": False, "deployment_authority_granted": False, "production_authority_granted": False},
        )


if __name__ == "__main__":
    unittest.main()
