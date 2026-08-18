#!/usr/bin/env python3
"""NA81 drift-classification tests for projection_drift_detection (SCRUM-347).

Exercises the SCRUM-347 (NA81-F6-N05) multi-target drift classifier
``classify_projection_drift_na81``:

* no drift                       -> NO_DRIFT
* material drift                 -> MATERIAL_DRIFT
* stale / out-of-order readback  -> STALE_READBACK
* conflicting target state      -> CONFLICT
* unavailable readback          -> UNAVAILABLE_READBACK
* deterministic digest / replay
* no back-write authority

The module is imported via an absolute ``tools/`` path insertion so that
``import node_architect...`` resolves under ``python -m unittest discover``
from the repository root (PEP 420 namespace packages).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import node_architect.projection_drift_detection as pdd  # noqa: E402

TASK_ID = "SCRUM-347"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
CANONICAL_REVISION = "d9a89a002aae4348359cd88810a9d03926199597"
STALE_REVISION = "0000000000000000000000000000000000000000"
OTHER_REVISION = "ffffffffffffffffffffffffffffffffffffffff"


def _digest(payload):
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def canonical_source(state=None, revision=CANONICAL_REVISION, content_digest=None):
    state = state if state is not None else {"status": "Done", "assignee": "hermes"}
    src = {"revision": revision, "state": state}
    if content_digest is not None:
        src["content_digest"] = content_digest
    return src


def readback(state=None, revision=CANONICAL_REVISION, content_digest=None):
    state = state if state is not None else {"status": "Done", "assignee": "hermes"}
    rb = {"revision": revision, "state": state}
    if content_digest is not None:
        rb["content_digest"] = content_digest
    return rb


def target(name, rb):
    return {"target": name, "readback": rb}


class ProjectionDriftClassificationTests(unittest.TestCase):
    # --- 1. no drift -----------------------------------------------------
    def test_no_drift(self):
        res = pdd.classify_projection_drift_na81(
            task_id=TASK_ID,
            repository=REPOSITORY,
            canonical_source=canonical_source(),
            projection_targets=[target("ds-admin", readback()), target("task-center", readback())],
        )
        self.assertEqual(res["classification"], "NO_DRIFT")
        self.assertEqual(res["target_count"], 2)
        self.assertEqual(res["unavailable_count"], 0)
        self.assertEqual(res["stale_count"], 0)
        self.assertEqual(res["material_drift_count"], 0)
        self.assertFalse(res["conflict"])
        for t in res["per_target"]:
            self.assertEqual(t["status"], "NO_DRIFT")

    # --- 2. material drift ----------------------------------------------
    def test_material_drift(self):
        drifted = readback(state={"status": "In Progress", "assignee": "hermes"})
        res = pdd.classify_projection_drift_na81(
            task_id=TASK_ID,
            repository=REPOSITORY,
            canonical_source=canonical_source(),
            projection_targets=[target("ds-admin", drifted)],
        )
        self.assertEqual(res["classification"], "MATERIAL_DRIFT")
        self.assertEqual(res["material_drift_count"], 1)
        self.assertIn("status", res["per_target"][0]["drift_fields"])

    # --- 3. stale / out-of-order readback -------------------------------
    def test_stale_readback(self):
        # identical state but older revision -> stale/out-of-order
        res = pdd.classify_projection_drift_na81(
            task_id=TASK_ID,
            repository=REPOSITORY,
            canonical_source=canonical_source(),
            projection_targets=[target("ds-admin", readback(revision=STALE_REVISION))],
        )
        self.assertEqual(res["classification"], "STALE_READBACK")
        self.assertEqual(res["stale_count"], 1)
        self.assertEqual(res["per_target"][0]["canonical_revision"], CANONICAL_REVISION)

    def test_out_of_order_readback(self):
        # readback at a different (not-older) revision than canonical
        res = pdd.classify_projection_drift_na81(
            task_id=TASK_ID,
            repository=REPOSITORY,
            canonical_source=canonical_source(),
            projection_targets=[target("ds-admin", readback(revision=OTHER_REVISION))],
        )
        self.assertEqual(res["classification"], "STALE_READBACK")
        self.assertEqual(res["stale_count"], 1)

    # --- 4. conflicting target state ------------------------------------
    def test_conflicting_target_state(self):
        a = readback(state={"status": "Done", "assignee": "hermes"})
        b = readback(state={"status": "In Progress", "assignee": "hermes"})
        res = pdd.classify_projection_drift_na81(
            task_id=TASK_ID,
            repository=REPOSITORY,
            canonical_source=canonical_source(),
            projection_targets=[target("ds-admin", a), target("task-center", b)],
        )
        self.assertEqual(res["classification"], "CONFLICT")
        self.assertTrue(res["conflict"])
        self.assertEqual(res["conflict_count"], 1)

    # --- 5. unavailable readback ----------------------------------------
    def test_unavailable_readback_none(self):
        res = pdd.classify_projection_drift_na81(
            task_id=TASK_ID,
            repository=REPOSITORY,
            canonical_source=canonical_source(),
            projection_targets=[target("ds-admin", None)],
        )
        self.assertEqual(res["classification"], "UNAVAILABLE_READBACK")
        self.assertEqual(res["unavailable_count"], 1)
        self.assertIsNone(res["per_target"][0]["readback_revision"])

    def test_unavailable_readback_malformed(self):
        res = pdd.classify_projection_drift_na81(
            task_id=TASK_ID,
            repository=REPOSITORY,
            canonical_source=canonical_source(),
            projection_targets=[target("ds-admin", {"foo": "bar"})],  # missing revision/state
        )
        self.assertEqual(res["classification"], "UNAVAILABLE_READBACK")
        self.assertEqual(res["unavailable_count"], 1)

    def test_unavailable_dominates_no_drift(self):
        # one target unavailable, another clean -> overall unavailable
        res = pdd.classify_projection_drift_na81(
            task_id=TASK_ID,
            repository=REPOSITORY,
            canonical_source=canonical_source(),
            projection_targets=[target("ds-admin", None), target("task-center", readback())],
        )
        self.assertEqual(res["classification"], "UNAVAILABLE_READBACK")

    # --- 6. deterministic digest / replay -------------------------------
    def test_deterministic_digest(self):
        args = dict(
            task_id=TASK_ID,
            repository=REPOSITORY,
            canonical_source=canonical_source(),
            projection_targets=[
                target("ds-admin", readback()),
                target("task-center", readback(state={"status": "In Progress", "assignee": "hermes"})),
            ],
        )
        d1 = pdd.classify_projection_drift_na81(**args)["decision_digest"]
        d2 = pdd.classify_projection_drift_na81(**args)["decision_digest"]
        self.assertEqual(d1, d2)
        self.assertTrue(d1.startswith("sha256:"))

    def test_order_independent(self):
        # reordering targets must not change the digest
        ordered = [
            target("ds-admin", readback()),
            target("task-center", readback(state={"status": "In Progress", "assignee": "hermes"})),
        ]
        reversed_order = list(reversed(ordered))
        d1 = pdd.classify_projection_drift_na81(
            task_id=TASK_ID, repository=REPOSITORY,
            canonical_source=canonical_source(), projection_targets=ordered,
        )["decision_digest"]
        d2 = pdd.classify_projection_drift_na81(
            task_id=TASK_ID, repository=REPOSITORY,
            canonical_source=canonical_source(), projection_targets=reversed_order,
        )["decision_digest"]
        self.assertEqual(d1, d2)
        self.assertEqual(d1, _digest({"status": "Done", "assignee": "hermes"}) and d1)

    def test_canonical_state_order_independent_digest(self):
        a = canonical_source(state={"status": "Done", "assignee": "hermes"})
        b = canonical_source(state={"assignee": "hermes", "status": "Done"})
        ra = pdd.classify_projection_drift_na81(
            task_id=TASK_ID, repository=REPOSITORY,
            canonical_source=a, projection_targets=[target("ds-admin", readback())],
        )["canonical_state_digest"]
        rb = pdd.classify_projection_drift_na81(
            task_id=TASK_ID, repository=REPOSITORY,
            canonical_source=b, projection_targets=[target("ds-admin", readback())],
        )["canonical_state_digest"]
        self.assertEqual(ra, rb)

    # --- 7. no back-write authority -------------------------------------
    def test_no_back_write_authority(self):
        res = pdd.classify_projection_drift_na81(
            task_id=TASK_ID,
            repository=REPOSITORY,
            canonical_source=canonical_source(),
            projection_targets=[target("ds-admin", readback())],
        )
        self.assertEqual(res["read_only_projection"], True)
        for field in (
            "write_authority_granted",
            "approval_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertEqual(res[field], False, field)
        self.assertEqual(res["schema_version"], "1.0")
        self.assertEqual(res["artifact_type"], "projection-drift-classification")

    # --- structural invariants ------------------------------------------
    def test_explicit_digest_override(self):
        # caller-supplied content_digest must be honored for canonical source
        res = pdd.classify_projection_drift_na81(
            task_id=TASK_ID,
            repository=REPOSITORY,
            canonical_source=canonical_source(content_digest="sha256:" + "a" * 64),
            projection_targets=[target("ds-admin", readback())],
        )
        # readback auto-digest != overridden canonical digest -> material drift
        self.assertEqual(res["classification"], "MATERIAL_DRIFT")

    def test_invalid_canonical_source_raises(self):
        with self.assertRaises(TypeError):
            pdd.classify_projection_drift_na81(
                task_id=TASK_ID, repository=REPOSITORY,
                canonical_source={"state": {}}, projection_targets=[],
            )
        with self.assertRaises(TypeError):
            pdd.classify_projection_drift_na81(
                task_id=TASK_ID, repository=REPOSITORY,
                canonical_source=canonical_source(), projection_targets="not-a-list",
            )


if __name__ == "__main__":
    unittest.main()
