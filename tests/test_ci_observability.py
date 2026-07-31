from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.resolve_g5_status import resolve

ROOT = Path(__file__).resolve().parents[1]


def build_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        'merge_commit_sha': 'a' * 40,
        'required_workflows': ['validate-instructions'],
        'candidates': [],
        'discovery': {'method': 'exact_push_lookup', 'exact_sha_lookup_attempted': True, 'fallbacks_attempted': []},
    }
    payload.update(overrides)
    return payload


class CIObservabilityClassificationTests(unittest.TestCase):
    def test_pr_workflow_run_classification(self) -> None:
        payload = build_payload(
            candidates=[
                {'workflow': 'validate-instructions', 'run_id': '1', 'head_sha': 'a' * 40, 'status': 'completed', 'conclusion': 'success', 'run_attempt': 1}
            ]
        )
        evidence = resolve(payload)
        self.assertEqual(evidence['classification'], 'success')

    def test_push_workflow_run_classification(self) -> None:
        payload = build_payload(
            candidates=[
                {'workflow': 'validate-instructions', 'run_id': '2', 'head_sha': 'a' * 40, 'status': 'completed', 'conclusion': 'failure', 'run_attempt': 1}
            ]
        )
        evidence = resolve(payload)
        self.assertEqual(evidence['classification'], 'failure')

    def test_connector_surface_unavailable(self) -> None:
        payload = build_payload(candidates=[])
        evidence = resolve(payload)
        self.assertEqual(evidence['classification'], 'CONNECTOR_OBSERVABILITY_INCOMPLETE')

    def test_sha_mismatch_rejected(self) -> None:
        payload = build_payload(
            candidates=[
                {'workflow': 'validate-instructions', 'run_id': '3', 'head_sha': 'b' * 40, 'status': 'completed', 'conclusion': 'success', 'run_attempt': 1}
            ]
        )
        evidence = resolve(payload)
        self.assertEqual(evidence['classification'], 'SHA_MISMATCH')

    def test_pending_status(self) -> None:
        payload = build_payload(
            candidates=[
                {'workflow': 'validate-instructions', 'run_id': '4', 'head_sha': 'a' * 40, 'status': 'in_progress', 'conclusion': None, 'run_attempt': 1}
            ]
        )
        evidence = resolve(payload)
        self.assertEqual(evidence['classification'], 'CI_PENDING')
        self.assertTrue(evidence['checkpoint_required'])

    def test_failed_status(self) -> None:
        payload = build_payload(
            candidates=[
                {'workflow': 'validate-instructions', 'run_id': '5', 'head_sha': 'a' * 40, 'status': 'completed', 'conclusion': 'failure', 'run_attempt': 1}
            ]
        )
        evidence = resolve(payload)
        self.assertEqual(evidence['classification'], 'failure')

    def test_pass_status(self) -> None:
        payload = build_payload(
            candidates=[
                {'workflow': 'validate-instructions', 'run_id': '6', 'head_sha': 'a' * 40, 'status': 'completed', 'conclusion': 'success', 'run_attempt': 1}
            ]
        )
        evidence = resolve(payload)
        self.assertEqual(evidence['classification'], 'success')


if __name__ == '__main__':
    unittest.main()
