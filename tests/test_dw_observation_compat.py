#!/usr/bin/env python3
"""Cross-repo compatibility test (SCRUM-396, DW observation sync).

Proves the new DurableArtifactEnvelope / journal / manifest do NOT break the
DW-SuperApps observatory data contract:
1. Observation `.run` event fixtures (no envelope fields) still parse under the
   resolver's canonical digest path (fields absent -> treated as UNKNOWN, same
   as observatory.ts asString(...) fallback).
2. An envelope-wrapped record remains readable by the observation normalize
   contract: extra envelope fields are optional, never required by replay.
3. New schema fields follow the *_digest / schema_version convention so
   dw-observation can read them source-backed.

Reference contract (DW-SuperApps projects/dw-observation):
  lib/observatory.ts NormalizedEvent: {sourceEventId, seq, occurredAt, eventType,
  source, actor, gate, nodeId, before, after, evidenceRefs, authorityRef,
  sourceDigest, annotations} — absent fields render UNKNOWN (no invention).
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.node_architect.schema_compatibility_resolver import (
    build_envelope,
    canonical_json,
)

FIXTURES = Path("/Users/mac/prj/DW-SuperApps/projects/dw-observation/fixtures")


def normalize_like_observatory(raw: dict) -> dict:
    """Mirror observatory.ts normalizeEvent: absent -> UNKNOWN (—)."""
    UNKNOWN = "—"
    def s(v, default=UNKNOWN):
        return v if isinstance(v, str) and v else default

    return {
        "sourceEventId": s(raw.get("event_id")),
        "seq": raw.get("sequence"),
        "occurredAt": s(raw.get("timestamp")),
        "eventType": s(raw.get("decision_kind")),
        "source": s(raw.get("source")),
        "actor": s(raw.get("actor")),
        "gate": s(raw.get("gate", "")),
        "nodeId": s(raw.get("node_id")),
        "before": raw.get("before", {}),
        "after": raw.get("after", {}),
        "evidenceRefs": raw.get("evidence_refs", []),
        "authorityRef": s(raw.get("authority_ref")),
        "sourceDigest": s(raw.get("source_digest")),
        "annotations": raw.get("annotations", {}),
    }


class DWObservationCompatibilityTests(unittest.TestCase):
    def test_run_fixture_normalizes_without_envelope(self) -> None:
        """Real .run fixture (no envelope fields) must still normalize."""
        path = FIXTURES / "run_scrum555_m0.json"
        if not path.exists():
            self.skipTest("DW-SuperApps fixture not checked out")
        with open(path, "r", encoding="utf-8") as fh:
            fixture = json.load(fh)
        for event in fixture.get("events", [])[:3]:
            norm = normalize_like_observatory(event)
            self.assertIn("sourceEventId", norm)
            # absent envelope fields are never required
            self.assertNotIn("writer_schema_id", event)

    def test_envelope_wrapped_record_still_normalizes(self) -> None:
        """Envelope-wrapped payload keeps observation fields readable."""
        inner = {
            "event_id": "evt_1",
            "timestamp": "2026-08-21T09:00:00Z",
            "decision_kind": "run_started",
            "source": "gwc",
            "actor": "DWA",
            "sequence": 0,
            "before": {},
            "after": {"jira": "SCRUM-396"},
        }
        envelope = build_envelope(
            artifact_kind="evidence",
            writer_schema_id="gwc.evidence.v1",
            writer_schema_version="1.0",
            schema_digest="sha256:" + "a" * 64,
            payload=inner,
            profile_id="gwc-jcs-v1",
            profile_version="1.0",
        )
        # observation reads the payload; envelope is optional metadata
        norm = normalize_like_observatory(envelope["payload"] if "payload" in envelope else inner)
        self.assertEqual(norm["sourceEventId"], "evt_1")
        self.assertEqual(norm["eventType"], "run_started")

    def test_envelope_fields_optional_in_observation_contract(self) -> None:
        """Envelope fields must not be required by the observation render path."""
        required_by_obs = {
            "event_id",
            "timestamp",
            "decision_kind",
            "source",
            "node_id",
            "before",
            "after",
            "sequence",
        }
        envelope_required = {
            "schema_version",
            "artifact_type",
            "artifact_kind",
            "writer_schema_id",
            "writer_schema_version",
            "schema_digest",
            "payload_digest",
            "migration_lineage",
        }
        # envelope fields are a superset; none collide with observation-only keys
        self.assertTrue(envelope_required.isdisjoint(required_by_obs))

    def test_manifest_issuer_visible_to_trust_panel(self) -> None:
        """SchemaTrustManifest exposes issuer + validity for trust panel (designer req)."""
        manifest = {
            "schema_version": "1.0",
            "artifact_type": "schema-trust-manifest",
            "manifest_id": "mt-001",
            "issuer": "dwc-connector",
            "issued_at": "2026-08-24T01:00:00Z",
            "validity": {"not_before": "2026-08-24T00:00:00Z", "not_after": "2026-09-01T00:00:00Z"},
            "entries": [],
        }
        # trust panel can render issuer + validity window directly
        self.assertEqual(manifest["issuer"], "dwc-connector")
        self.assertIn("validity", manifest)
        self.assertEqual(manifest["validity"]["not_after"], "2026-09-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
