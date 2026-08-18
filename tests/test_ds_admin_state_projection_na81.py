#!/usr/bin/env python3
"""NA81 DS Admin state projection tests for SCRUM-343 (NA81-F6-N01).

Exercises the SCRUM-343 (NA81-F6-N01) ``project_ds_admin_state_na81`` layer
over the existing sync_projection ds-admin-state-projection renderer. Maps
every current-brief requirement to code + tests:

* deterministic render
* stale source revision (projection must NOT render from non-current evidence)
* replay / idempotency
* privacy filtering (only allowed canonical keys leak to DS Admin)
* missing canonical source
* explicit non-authoritative semantics (read_only, no authority grants)

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
import node_architect.ds_admin_state_projection as dm  # noqa: E402

TASK_ID = "SCRUM-343"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
PROJECTION_TARGET = "ds-admin"
CANONICAL_REVISION = "cda2eef0000000000000000000000000000000000"


def _digest(payload):
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _source_authority_decision(status="VERIFIED", revision=CANONICAL_REVISION):
    sa = {
        "schema_version": "1.0",
        "artifact_type": "projection-source-authority-decision",
        "task_id": TASK_ID,
        "repository": REPOSITORY,
        "projection_target": PROJECTION_TARGET,
        "source_bindings": [
            {
                "source_type": "REPOSITORY",
                "authority_class": "CANONICAL",
                "ref": "refs/heads/pre-prod",
                "revision": revision,
                "content_digest": _digest({"head": revision}),
                "observed_at": "2026-08-18T00:00:00Z",
                "status": status,
            }
        ],
        "field_authority": [
            {
                "field_path": "task_status",
                "source_ref": "refs/heads/pre-prod",
                "source_revision": revision,
                "evidence_digest": _digest({"x": 1}),
                "derivation": "DIRECT",
                "derivation_rule_id": "canonical-scalar-v1",
            }
        ],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_SOURCE_AUTHORITY_CONFIRMED",
        "reason_codes": ["PROJECTION_SOURCE_AUTHORITY_CONFIRMED"],
        "observed_at": "2026-08-18T00:00:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    sa["decision_digest"] = _digest({k: v for k, v in sa.items() if k not in {"reason_codes", "decision_digest"}})
    return sa


def _evidence_linkset():
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-evidence-linkset",
        "task_id": TASK_ID,
        "repository": REPOSITORY,
        "projection_target": PROJECTION_TARGET,
        "outcome": "READY",
        "reason_code": "EVIDENCE_LINKSET_READY",
        "linkset_digest": _digest({"x": 1}),
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def _privacy_decision():
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-privacy-decision",
        "task_id": TASK_ID,
        "repository": REPOSITORY,
        "projection_target": PROJECTION_TARGET,
        "outcome": "READY",
        "reason_code": "PRIVACY_APPROVED",
        "decision_digest": _digest({"y": 2}),
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def _envelope(canonical_state=None):
    sa = _source_authority_decision()
    ls = _evidence_linkset()
    pr = _privacy_decision()
    if canonical_state is None:
        canonical_state = {
            "task_id": TASK_ID,
            "task_status": "In Progress",
            "repository_head": CANONICAL_REVISION,
            "source_authority_digest": sa["decision_digest"],
        }
    return {
        "source_authority_digest": sa["decision_digest"],
        "evidence_linkset_digest": ls["linkset_digest"],
        "privacy_boundary_digest": pr["decision_digest"],
        "canonical_state": canonical_state,
    }


def _project(**overrides):
    sa = _source_authority_decision()
    ls = _evidence_linkset()
    pr = _privacy_decision()
    env = _envelope()
    kwargs = dict(
        task_id=TASK_ID, repository=REPOSITORY, projection_target=PROJECTION_TARGET,
        source_authority_decision=sa, evidence_linkset=ls,
        privacy_boundary_decision=pr, envelope=env, projected_at="2026-08-18T01:00:00Z",
    )
    kwargs.update(overrides)
    return dm.project_ds_admin_state_na81(**kwargs)


class DsAdminStateProjectionNa81Tests(unittest.TestCase):
    # --- 1. deterministic render ----------------------------------------
    def test_deterministic_render(self):
        r1 = _project()
        r2 = _project()
        self.assertEqual(r1["outcome"], "READY")
        self.assertEqual(r2["outcome"], "READY")
        self.assertEqual(r1["projection_digest"], r2["projection_digest"])
        self.assertTrue(r1["na81"]["deterministic"])

    # --- 2. stale source revision --------------------------------------
    def test_stale_source_revision_blocked(self):
        sa = _source_authority_decision(status="STALE")
        res = _project(source_authority_decision=sa)
        self.assertTrue(res["na81"]["stale_source_detected"])
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["reason_code"], "DS_ADMIN_NA81_STALE_SOURCE_REVISION")
        self.assertIn("DS_ADMIN_NA81_STALE_SOURCE_REVISION", res["reason_codes"])

    def test_missing_source_binding_blocked(self):
        sa = _source_authority_decision(status="MISSING")
        res = _project(source_authority_decision=sa)
        self.assertTrue(res["na81"]["stale_source_detected"])
        self.assertEqual(res["outcome"], "BLOCKED")

    def test_ambiguous_source_binding_blocked(self):
        sa = _source_authority_decision(status="AMBIGUOUS")
        res = _project(source_authority_decision=sa)
        self.assertTrue(res["na81"]["stale_source_detected"])
        self.assertEqual(res["outcome"], "BLOCKED")

    def test_current_source_revision_allowed(self):
        sa = _source_authority_decision(status="VERIFIED")
        res = _project(source_authority_decision=sa)
        self.assertFalse(res["na81"]["stale_source_detected"])
        self.assertEqual(res["outcome"], "READY")

    # --- 3. replay / idempotency ---------------------------------------
    def test_replay_idempotent(self):
        res = _project()
        self.assertTrue(res["na81"]["idempotent"])
        # a changed canonical source head must change the digest (not idempotent across revisions)
        env = _envelope()
        env["canonical_state"]["repository_head"] = "ffffffffffffffffffffffffffffffffffffffff"
        changed = _project(envelope=env)
        self.assertNotEqual(res["projection_digest"], changed["projection_digest"])

    # --- 4. privacy filtering ------------------------------------------
    def test_privacy_filtering_allowed_only(self):
        res = _project()
        self.assertTrue(res["na81"]["privacy_filtered"])
        base = res["projection"]
        for key in base["canonical_state"]:
            self.assertIn(key, dm.ALLOWED_CANONICAL_KEYS)

    def test_privacy_filtering_drops_unauthorized_field(self):
        env = _envelope()
        env["canonical_state"]["secret_token"] = "leak"
        res = _project(envelope=env)
        base = res["projection"]
        # the unauthorized field must not reach the projected canonical state
        self.assertNotIn("secret_token", base["canonical_state"])
        self.assertTrue(res["na81"]["privacy_filtered"])
        # but the renderer still fails closed on the unauthorized input
        self.assertEqual(base["outcome"], "BLOCKED")

    # --- 5. missing canonical source -----------------------------------
    def test_missing_canonical_source_blocked(self):
        env = _envelope(canonical_state={"task_id": TASK_ID})
        # canonical_state present but incomplete (no repository_head etc.) is still
        # allowed-keys; instead test the envelope truly missing canonical_state
        env2 = _envelope()
        del env2["canonical_state"]
        res = _project(envelope=env2)
        self.assertFalse(res["na81"]["canonical_source_present"])
        self.assertEqual(res["projection"]["outcome"], "BLOCKED")
        self.assertEqual(res["outcome"], "BLOCKED")

    # --- 6. explicit non-authoritative semantics ------------------------
    def test_explicit_non_authoritative(self):
        res = _project()
        base = res["projection"]
        self.assertTrue(res["na81"]["non_authoritative"])
        self.assertTrue(base["read_only_projection"])
        self.assertFalse(base["write_authority_granted"])
        self.assertFalse(base["approval_authority_granted"])
        self.assertFalse(base["merge_authority_granted"])
        self.assertFalse(base["deployment_authority_granted"])
        self.assertFalse(base["production_authority_granted"])
        # the projection is bounded DS Admin visibility state only
        self.assertEqual(base["artifact_type"], "ds-admin-state-projection")


if __name__ == "__main__":
    unittest.main()
