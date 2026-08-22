#!/usr/bin/env python3
"""SCRUM-350 (NA81-F6-N08) evidence-linking fail-closed maturity tests.

Exercises the ``build_projection_evidence_linkset`` evaluator in
``tools/node_architect/projection_evidence_linking.py`` for the two
currently-missing NA81 provenance defenses plus regression coverage of the
brief's required matrix (valid link, broken source, stale source digest,
circular link, projection-derived source, duplicate replay, no-authority
implication).

Mapping to the SCRUM-350 brief (NA81-F6-N08):

* valid link -> READY, read-only, no authority granted
* broken source -> fail closed (BROKEN)
* stale source digest -> fail closed (STALE)
* circular link -> fail closed (cycle over SUPERSEDES revisions)
* projection-derived source -> fail closed (link must never use a
  projection artifact as canonical provenance)
* duplicate replay -> identical linkset_digest (deterministic idempotency)
* no-authority implication -> outcome/link_status never grants authority

Imported via an absolute ``tools/`` path insertion so ``import
node_architect...`` resolves under ``python -m unittest discover`` from the
repository root (PEP 420 namespace packages).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import node_architect.projection_evidence_linking as link  # noqa: E402

LINK_SCHEMA = json.loads(Path("schemas/projection-evidence-linkset.schema.json").read_text(encoding="utf-8"))
try:
    from jsonschema import Draft202012Validator, FormatChecker

    _LINK_VALIDATOR = Draft202012Validator(LINK_SCHEMA, format_checker=FormatChecker())
except Exception:  # pragma: no cover - schema validation is best-effort in this suite
    _LINK_VALIDATOR = None

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
REVISION_A = "d9a89a002aae4348359cd88810a9d03926199597"
REVISION_B = "e9a89a002aae4348359cd88810a9d03926199598"
REVISION_C = "f9a89a002aae4348359cd88810a9d03926199599"


def _source_authority_digest(decision: dict[str, Any]) -> str:
    semantic = {
        key: value
        for key, value in decision.items()
        if key not in {"observed_at", "decision_digest"}
    }
    payload = json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def valid_authority_decision(projection_binding: bool = False) -> dict[str, Any]:
    decision: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": "projection-source-authority-decision",
        "task_id": "SCRUM-350",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "ds-admin",
        "source_bindings": [
            {
                "source_type": "TASK_RECORD",
                "authority_class": "CANONICAL",
                "ref": "jira:SCRUM-350",
                "revision": REVISION_A,
                "content_digest": DIGEST_A,
                "observed_at": "2026-08-18T17:00:00Z",
                "status": "VERIFIED",
            },
            {
                "source_type": "REPOSITORY",
                "authority_class": "CANONICAL",
                "ref": "github:gwc",
                "revision": REVISION_B,
                "content_digest": DIGEST_B,
                "observed_at": "2026-08-18T17:00:00Z",
                "status": "VERIFIED",
            },
        ],
        "field_authority": [
            {
                "field_path": "/task/status",
                "source_ref": "jira:SCRUM-350",
                "source_revision": REVISION_A,
                "evidence_digest": DIGEST_A,
                "derivation": "DIRECT",
            },
            {
                "field_path": "/repository/head",
                "source_ref": "github:gwc",
                "source_revision": REVISION_B,
                "evidence_digest": DIGEST_B,
                "derivation": "DIRECT",
            },
        ],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_SOURCE_AUTHORITY_CONFIRMED",
        "reason_codes": ["PROJECTION_SOURCE_AUTHORITY_CONFIRMED"],
        "observed_at": "2026-08-18T17:05:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    if projection_binding:
        decision["source_bindings"].append(
            {
                "source_type": "TASK_RECORD",
                "authority_class": "PROJECTION",
                "ref": "projection:ds-admin/SCRUM-350",
                "revision": REVISION_C,
                "content_digest": DIGEST_C,
                "observed_at": "2026-08-18T17:00:00Z",
                "status": "VERIFIED",
            }
        )
    decision["decision_digest"] = _source_authority_digest(decision)
    return decision


def valid_evidence_items() -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": "task-350",
            "source_type": "TASK_RECORD",
            "ref": "jira:SCRUM-350",
            "revision": REVISION_A,
            "content_digest": DIGEST_A,
            "relation": "SUPPORTS_FIELD",
            "field_paths": ["/task/status"],
            "display_url": "https://example.invalid/SCRUM-350",
            "verification_status": "VERIFIED",
        },
        {
            "evidence_id": "repo-head",
            "source_type": "REPOSITORY",
            "ref": "github:gwc",
            "revision": REVISION_B,
            "content_digest": DIGEST_B,
            "relation": "DERIVED_FROM",
            "field_paths": ["/repository/head"],
            "verification_status": "VERIFIED",
        },
    ]


class ProjectionEvidenceLinkingScrum350Tests(unittest.TestCase):
    def build(self, **overrides: Any) -> dict[str, Any]:
        payload = {
            "task_id": "SCRUM-350",
            "repository": "nhatino.example/gwc",
            "projection_target": "ds-admin",
            "source_authority_decision": valid_authority_decision(),
            "evidence_items": valid_evidence_items(),
            "projected_fields": ["/task/status", "/repository/head"],
            "linked_at": "2026-08-18T17:10:00Z",
        }
        payload.update(overrides)
        # the production repository value must match the authority decision
        payload["repository"] = "nhatnguyenquang1838-coder/gwc"
        result = link.build_projection_evidence_linkset(**payload)
        if _LINK_VALIDATOR is not None:
            errors = sorted(_LINK_VALIDATOR.iter_errors(result), key=lambda error: list(error.path))
            self.assertEqual(errors, [], [error.message for error in errors])
        return result

    def test_valid_link_is_ready_read_only_and_schema_valid(self):
        result = self.build()
        self.assertEqual(result["outcome"], "READY")
        self.assertEqual(result["reason_code"], "EVIDENCE_LINKSET_READY")
        self.assertEqual(result["covered_fields"], ["/repository/head", "/task/status"])
        self.assertEqual(result["uncovered_fields"], [])
        self.assertEqual(result["link_status"], "VERIFIED")
        self.assertTrue(result["read_only_projection"])
        for key in (
            "write_authority_granted",
            "approval_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(result[key])

    def test_broken_source_fails_closed(self):
        items = valid_evidence_items()
        items[0]["verification_status"] = "BROKEN"
        result = self.build(evidence_items=items)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertEqual(result["reason_code"], "EVIDENCE_LINK_BROKEN")

    def test_stale_source_digest_fails_closed(self):
        items = valid_evidence_items()
        items[1]["verification_status"] = "STALE"
        result = self.build(evidence_items=items)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertEqual(result["reason_code"], "EVIDENCE_LINK_STALE")

    def test_circular_link_over_supersedes_fails_closed(self):
        # A revision graph where A supersedes B and B supersedes A is a cycle.
        items = valid_evidence_items()
        items.append(
            {
                "evidence_id": "hist-a",
                "source_type": "TASK_RECORD",
                "ref": "jira:SCRUM-350",
                "revision": REVISION_A,
                "supersedes_revision": REVISION_B,
                "content_digest": DIGEST_A,
                "relation": "SUPERSEDES",
                "field_paths": [],
                "verification_status": "VERIFIED",
            }
        )
        items.append(
            {
                "evidence_id": "hist-b",
                "source_type": "TASK_RECORD",
                "ref": "jira:SCRUM-350",
                "revision": REVISION_B,
                "supersedes_revision": REVISION_A,
                "content_digest": DIGEST_B,
                "relation": "SUPERSEDES",
                "field_paths": [],
                "verification_status": "VERIFIED",
            }
        )
        result = self.build(evidence_items=items)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertEqual(result["reason_code"], "EVIDENCE_LINK_CONTRACT_INVALID")
        self.assertIn("EVIDENCE_LINK_CONTRACT_INVALID", result["reason_codes"])

    def test_acyclic_supersedes_chain_is_not_blocked(self):
        # A -> B -> C (linear) is a valid provenance history, not a cycle.
        items = valid_evidence_items()
        items.append(
            {
                "evidence_id": "hist-ab",
                "source_type": "TASK_RECORD",
                "ref": "jira:SCRUM-350",
                "revision": REVISION_A,
                "supersedes_revision": REVISION_B,
                "content_digest": DIGEST_A,
                "relation": "SUPERSEDES",
                "field_paths": [],
                "verification_status": "VERIFIED",
            }
        )
        items.append(
            {
                "evidence_id": "hist-bc",
                "source_type": "TASK_RECORD",
                "ref": "jira:SCRUM-350",
                "revision": REVISION_B,
                "supersedes_revision": REVISION_C,
                "content_digest": DIGEST_B,
                "relation": "SUPERSEDES",
                "field_paths": [],
                "verification_status": "VERIFIED",
            }
        )
        result = self.build(evidence_items=items)
        self.assertEqual(result["outcome"], "READY")
        self.assertEqual(result["reason_code"], "EVIDENCE_LINKSET_READY")

    def test_projection_derived_source_fails_closed(self):
        # A projection artifact (authority_class PROJECTION, VERIFIED) must
        # never be accepted as canonical provenance for an evidence link.
        decision = valid_authority_decision(projection_binding=True)
        items = valid_evidence_items()
        # the projection binding identity (ref/revision/digest) is reused as a link
        items.append(
            {
                "evidence_id": "proj-derived",
                "source_type": "TASK_RECORD",
                "ref": "projection:ds-admin/SCRUM-350",
                "revision": REVISION_C,
                "content_digest": DIGEST_C,
                "relation": "SUPPORTS_FIELD",
                "field_paths": ["/task/status"],
                "verification_status": "VERIFIED",
            }
        )
        result = self.build(source_authority_decision=decision, evidence_items=items)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertEqual(result["reason_code"], "EVIDENCE_LINK_CONTRACT_INVALID")
        self.assertIn("EVIDENCE_LINK_CONTRACT_INVALID", result["reason_codes"])

    def test_duplicate_replay_is_deterministic(self):
        first = self.build()
        replay_items = copy.deepcopy(valid_evidence_items())
        replay_items.append(copy.deepcopy(replay_items[0]))
        replay_items.reverse()
        second = self.build(evidence_items=replay_items)
        self.assertEqual(len(second["links"]), 2)
        self.assertEqual(first["linkset_digest"], second["linkset_digest"])

    def test_no_authority_implication_even_when_ready(self):
        result = self.build()
        self.assertEqual(result["outcome"], "READY")
        # a link proves provenance only; it must never grant authority
        self.assertTrue(result["read_only_projection"])
        self.assertFalse(any(result[key] for key in (
            "write_authority_granted",
            "approval_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        )))


if __name__ == "__main__":
    unittest.main(verbosity=2)
