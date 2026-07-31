from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.generate_g01_human_review import render_human_review

ROOT = Path(__file__).resolve().parents[1]


def write_temp(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return path


def sample_impact() -> dict:
    return {
        'schema_version': '1.0',
        'artifact_type': 'g1-option-impact',
        'task_id': 'SCRUM-140',
        'repository': 'nhatnguyenquang1838-coder/gwc',
        'base_sha': '43daebcffbd71cf0339c4de8c82d3c91db95be1d',
        'generated_at_utc': '2026-07-26T07:30:00Z',
        'analysis_source': {
            'method': 'task_me',
            'task_me': {
                'applicable': True,
                'available': True,
                'invoked': True,
                'run_id': 'gwc-scrum-136-20260726-r1',
                'plan_revision': 'sha256:4103e38b3d77aa428f9ecb2bd0c6cb9e9114d2e257b2fb6fee1febe46450a432',
            },
        },
        'ua_knowledge': {
            'status': 'CURRENT',
            'base_graph': 'AVAILABLE',
            'source_paths': ['.ua/meta.json', '.ua/knowledge-graph.json'],
            'source_hashes': ['sha256:' + '1' * 64],
            'synthetic_nodes_generated': False,
        },
        'options': [
            {
                'id': 'OPT-1',
                'title': 'Integrate G1 presentation and package export',
                'selected': True,
                'recommendation': 'recommended',
                'scores': {'value': 8, 'complexity': 6, 'effort': 5, 'risk': 4, 'blast_radius': 3},
                'impact': {
                    'summary': 'Update skill, runbook, and package.',
                    'files': ['skills/gwc-g1/SKILL.md'],
                    'symbols': ['gwc-g1'],
                    'components': ['skills'],
                    'dependencies': [],
                    'tests': ['tests/test_g01_human_review.py'],
                    'rollback': 'Revert skill and package changes.',
                },
                'graph_delta': {
                    'nodes_added': [],
                    'nodes_changed': ['G1Skill'],
                    'edges_added': ['G1Skill->Package'],
                },
            }
        ],
    }


def sample_review() -> dict:
    return {
        'schema_version': '1.0',
        'artifact_type': 'g01-human-review',
        'task_id': 'SCRUM-140',
        'repository': 'nhatnguyenquang1838-coder/gwc',
        'base_sha': '43daebcffbd71cf0339c4de8c82d3c91db95be1d',
        'generated_at_utc': '2026-07-26T07:30:00Z',
        'gates': {'g0': 'READY', 'g1': 'PASS', 'g2': 'APPROVED'},
        'impact_ref': {
            'path': '.gwc/tasks/SCRUM-140/g1/g1-option-impact.yaml',
            'sha256': 'sha256:' + '2' * 64,
        },
        'html': {
            'template_version': '1.0',
            'title': 'SCRUM-140 Human Review',
            'sections': ['summary', 'task_me', 'ua', 'options', 'authority'],
            'self_contained': True,
            'remote_assets_allowed': False,
        },
        'presentation': {
            'chat_summary': 'G0/G1 review is ready.',
            'slack_summary': 'G0/G1 review ready in the task thread.',
            'html_ref': 'g01-human-review.html',
            'slack_thread_required': True,
        },
        'presentation_state': 'CURRENT',
        'authority_notice': 'This derived review does not grant G2, G3, G4, G5, or G6 authority.',
    }


class G01HumanReviewIntegrationTests(unittest.TestCase):
    def test_end_to_end_generates_html_file(self) -> None:
        impact = write_temp(ROOT / '.gwc/tmp/impact-e2e.json', json.dumps(sample_impact()))
        review = write_temp(ROOT / '.gwc/tmp/review-e2e.json', json.dumps(sample_review()))
        output = ROOT / '.gwc/tmp/review-e2e.html'
        html_text = render_human_review(impact, json.loads(review.read_text(encoding='utf-8')))
        output.write_text(html_text, encoding='utf-8')
        self.assertTrue(output.exists())
        self.assertIn('SCRUM-140 Human Review', output.read_text(encoding='utf-8'))

    def test_presentation_payload_structure(self) -> None:
        review = sample_review()
        presentation = review['presentation']
        self.assertIn('chat_summary', presentation)
        self.assertIn('slack_summary', presentation)
        self.assertIn('html_ref', presentation)
        self.assertTrue(presentation['slack_thread_required'])

    def test_authority_notice_present(self) -> None:
        review = sample_review()
        self.assertIn('does not grant', review['authority_notice'])


if __name__ == '__main__':
    unittest.main()
