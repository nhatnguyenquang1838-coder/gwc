from __future__ import annotations

import json
import unittest
from pathlib import Path
from xml.sax.handler import feature_external_ges

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
        'task_id': 'SCRUM-139',
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
            'status': 'STALE',
            'base_graph': 'EMPTY',
            'source_paths': ['.ua/meta.json', '.ua/knowledge-graph.json'],
            'source_hashes': ['sha256:' + '0' * 64],
            'synthetic_nodes_generated': False,
        },
        'options': [
            {
                'id': 'OPT-1',
                'title': 'Build deterministic renderer',
                'selected': True,
                'recommendation': 'recommended',
                'scores': {'value': 8, 'complexity': 6, 'effort': 5, 'risk': 4, 'blast_radius': 3},
                'impact': {
                    'summary': 'Add renderer and template.',
                    'files': ['tools/generate_g01_human_review.py'],
                    'symbols': ['render_human_review'],
                    'components': ['tools'],
                    'dependencies': [],
                    'tests': ['tests/test_g01_human_review_renderer.py'],
                    'rollback': 'Revert renderer and template.',
                },
                'graph_delta': {
                    'nodes_added': ['G01HumanReviewRenderer'],
                    'nodes_changed': [],
                    'edges_added': ['TaskMe->Renderer'],
                },
            }
        ],
    }


def sample_review() -> dict:
    return {
        'schema_version': '1.0',
        'artifact_type': 'g01-human-review',
        'task_id': 'SCRUM-139',
        'repository': 'nhatnguyenquang1838-coder/gwc',
        'base_sha': '43daebcffbd71cf0339c4de8c82d3c91db95be1d',
        'generated_at_utc': '2026-07-26T07:30:00Z',
        'gates': {'g0': 'READY', 'g1': 'PASS', 'g2': 'AWAITING_APPROVAL'},
        'impact_ref': {
            'path': '.gwc/tasks/SCRUM-139/g1/g1-option-impact.yaml',
            'sha256': 'sha256:' + '1' * 64,
        },
        'html': {
            'template_version': '1.0',
            'title': 'SCRUM-139 Human Review',
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


class G01HumanReviewRendererTests(unittest.TestCase):
    def test_deterministic_output_for_same_input(self) -> None:
        impact = write_temp(ROOT / '.gwc/tmp/impact.json', json.dumps(sample_impact()))
        review = write_temp(ROOT / '.gwc/tmp/review.json', json.dumps(sample_review()))
        out1 = ROOT / '.gwc/tmp/out1.html'
        out2 = ROOT / '.gwc/tmp/out2.html'
        render_human_review(impact, json.loads(review.read_text(encoding='utf-8')))
        # The function returns HTML string; we call it directly
        html1 = render_human_review(impact, json.loads(review.read_text(encoding='utf-8')))
        html2 = render_human_review(impact, json.loads(review.read_text(encoding='utf-8')))
        self.assertEqual(html1, html2)

    def test_missing_ua_state_is_exposed(self) -> None:
        payload = sample_impact()
        payload['ua_knowledge']['status'] = 'MISSING'
        payload['ua_knowledge']['base_graph'] = 'MISSING'
        impact = write_temp(ROOT / '.gwc/tmp/impact-missing.json', json.dumps(payload))
        review = sample_review()
        html_text = render_human_review(impact, review)
        self.assertIn('MISSING', html_text)

    def test_stale_ua_state_is_exposed(self) -> None:
        payload = sample_impact()
        payload['ua_knowledge']['status'] = 'STALE'
        impact = write_temp(ROOT / '.gwc/tmp/impact-stale.json', json.dumps(payload))
        review = sample_review()
        html_text = render_human_review(impact, review)
        self.assertIn('STALE', html_text)

    def test_xss_payloads_are_neutralized(self) -> None:
        payload = sample_impact()
        payload['options'][0]['title'] = '<script>alert(1)</script>'
        payload['options'][0]['impact']['summary'] = '<img src=x onerror=alert(1)>'
        impact = write_temp(ROOT / '.gwc/tmp/impact-xss.json', json.dumps(payload))
        review = sample_review()
        html_text = render_human_review(impact, review)
        self.assertNotIn('<script>', html_text)
        self.assertNotIn('<img', html_text)
        self.assertIn('&lt;script&gt;', html_text)
        self.assertIn('&lt;img', html_text)

    def test_self_contained_no_remote_assets(self) -> None:
        payload = sample_impact()
        impact = write_temp(ROOT / '.gwc/tmp/impact-remote.json', json.dumps(payload))
        review = sample_review()
        html_text = render_human_review(impact, review)
        self.assertNotIn('http://', html_text)
        self.assertNotIn('https://', html_text)
        self.assertIn('<style>', html_text)

    def test_mobile_first_meta_tags(self) -> None:
        payload = sample_impact()
        impact = write_temp(ROOT / '.gwc/tmp/impact-mobile.json', json.dumps(payload))
        review = sample_review()
        html_text = render_human_review(impact, review)
        self.assertIn('<meta name="viewport"', html_text)


if __name__ == '__main__':
    unittest.main()
