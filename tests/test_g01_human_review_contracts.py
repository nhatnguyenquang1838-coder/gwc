from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def load_schema(name: str) -> dict:
    with (ROOT / "schemas" / name).open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return schema


def validate(schema_name: str, instance: dict) -> list[str]:
    validator = Draft202012Validator(load_schema(schema_name))
    return [
        error.message
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    ]


def sample_impact() -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "g1-option-impact",
        "task_id": "SCRUM-138",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "base_sha": "43daebcffbd71cf0339c4de8c82d3c91db95be1d",
        "generated_at_utc": "2026-07-26T07:30:00Z",
        "analysis_source": {
            "method": "task_me",
            "task_me": {
                "applicable": True,
                "available": True,
                "invoked": True,
                "run_id": "gwc-scrum-136-20260726-r1",
                "plan_revision": "sha256:4103e38b3d77aa428f9ecb2bd0c6cb9e9114d2e257b2fb6fee1febe46450a432",
            },
        },
        "ua_knowledge": {
            "status": "STALE",
            "base_graph": "EMPTY",
            "source_paths": [".ua/meta.json", ".ua/knowledge-graph.json"],
            "source_hashes": ["sha256:" + "0" * 64],
            "synthetic_nodes_generated": False,
        },
        "options": [
            {
                "id": "OPT-1",
                "title": "Derived impact and review contracts",
                "selected": True,
                "recommendation": "recommended",
                "scores": {"value": 8, "complexity": 6, "effort": 5, "risk": 4, "blast_radius": 3},
                "impact": {
                    "summary": "Add derived contracts without changing canonical gate authority.",
                    "files": ["schemas/g1-option-impact.schema.json"],
                    "symbols": ["g1-option-impact"],
                    "dependencies": ["Task Me", "UA"],
                    "tests": ["python -m unittest tests.test_g01_human_review_contracts"],
                    "rollback": "Remove the added schemas and tests from the branch.",
                },
                "graph_delta": {
                    "nodes_added": ["G01HumanReview"],
                    "nodes_changed": [],
                    "edges_added": ["TaskMe->G1"],
                },
            }
        ],
    }


def sample_human_review(notice: str | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "g01-human-review",
        "task_id": "SCRUM-138",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "base_sha": "43daebcffbd71cf0339c4de8c82d3c91db95be1d",
        "generated_at_utc": "2026-07-26T07:30:00Z",
        "gates": {"g0": "READY", "g1": "PASS", "g2": "AWAITING_APPROVAL"},
        "impact_ref": {
            "path": ".gwc/tasks/SCRUM-138/g1/g1-option-impact.yaml",
            "sha256": "sha256:" + "1" * 64,
        },
        "html": {
            "template_version": "1.0",
            "title": "SCRUM-138 Human Review",
            "sections": ["summary", "task_me", "ua", "options", "authority"],
            "self_contained": True,
            "remote_assets_allowed": False,
        },
        "presentation": {
            "chat_summary": "G0/G1 review is ready.",
            "slack_summary": "G0/G1 review ready in the task thread.",
            "html_ref": "g01-human-review.html",
            "slack_thread_required": True,
        },
        "authority_notice": notice
        or "This derived review does not grant G2, G3, G4, G5, or G6 authority.",
    }


class G01HumanReviewContractTests(unittest.TestCase):
    def test_g1_option_impact_accepts_task_me_and_stale_ua(self) -> None:
        self.assertEqual(validate("g1-option-impact.schema.json", sample_impact()), [])

    def test_g1_option_impact_rejects_synthetic_ua_nodes(self) -> None:
        payload = sample_impact()
        payload["ua_knowledge"]["synthetic_nodes_generated"] = True
        self.assertTrue(validate("g1-option-impact.schema.json", payload))

    def test_g1_option_impact_requires_task_me_when_available(self) -> None:
        payload = sample_impact()
        payload["analysis_source"]["task_me"]["invoked"] = False
        self.assertTrue(validate("g1-option-impact.schema.json", payload))

    def test_g01_human_review_accepts_authority_separated_projection(self) -> None:
        self.assertEqual(validate("g01-human-review.schema.json", sample_human_review()), [])

    def test_g01_human_review_rejects_missing_authority_warning(self) -> None:
        for notice in ("approve this", "G2 granted by HTML"):
            with self.subTest(notice=notice):
                self.assertTrue(validate("g01-human-review.schema.json", sample_human_review(notice)))


if __name__ == "__main__":
    unittest.main()
