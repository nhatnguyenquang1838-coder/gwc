#!/usr/bin/env python3
"""Generate deterministic G0/G1 human-review HTML from canonical GWC artifacts."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / 'templates' / 'g01' / 'g01-human-review.template.html'


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _render_section(title: str, body: str) -> str:
    return f'<section>\n<h2>{_esc(title)}</h2>\n{body}\n</section>\n'


def _render_table(rows: list[dict[str, str]]) -> str:
    lines = ['<table>', '<tr>' + ''.join(f'<th>{_esc(k)}</th>' for k in rows[0].keys()) + '</tr>']
    for row in rows:
        lines.append('<tr>' + ''.join(f'<td>{_esc(v)}</td>' for v in row.values()) + '</tr>')
    lines.append('</table>')
    return '\n'.join(lines)


def _render_options(options: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for option in options:
        rows = [
            {'Field': 'ID', 'Value': option.get('id', '')},
            {'Field': 'Title', 'Value': option.get('title', '')},
            {'Field': 'Selected', 'Value': str(option.get('selected', False))},
            {'Field': 'Recommendation', 'Value': option.get('recommendation', '')},
            {'Field': 'Summary', 'Value': option.get('impact', {}).get('summary', '')},
            {'Field': 'Rollback', 'Value': option.get('impact', {}).get('rollback', '')},
        ]
        lines.append(_render_section(option.get('title', option.get('id', 'Option')), _render_table(rows)))
    return '\n'.join(lines)


def render_human_review(impact_path: Path | str, review_payload: dict[str, Any]) -> str:
    impact = json.loads(Path(impact_path).read_text(encoding='utf-8'))
    options = review_payload.get('options', impact.get('options', []))
    if not options:
        options = impact.get('options', [])

    sections: list[str] = []
    sections.append(_render_section('Summary', '<p>' + _esc(review_payload.get('presentation', {}).get('chat_summary', '')) + '</p>'))

    analysis = impact.get('analysis_source', {})
    task_me = analysis.get('task_me', {})
    task_me_rows = [
        {'Field': 'Method', 'Value': analysis.get('method', '')},
        {'Field': 'Applicable', 'Value': str(task_me.get('applicable', False))},
        {'Field': 'Available', 'Value': str(task_me.get('available', False))},
        {'Field': 'Invoked', 'Value': str(task_me.get('invoked', False))},
        {'Field': 'Fallback reason', 'Value': task_me.get('fallback_reason', '')},
        {'Field': 'Run ID', 'Value': task_me.get('run_id', '')},
        {'Field': 'Plan revision', 'Value': task_me.get('plan_revision', '')},
    ]
    sections.append(_render_section('Task Me', _render_table(task_me_rows)))

    ua = impact.get('ua_knowledge', {})
    ua_rows = [
        {'Field': 'Status', 'Value': ua.get('status', '')},
        {'Field': 'Base graph', 'Value': ua.get('base_graph', '')},
        {'Field': 'Source paths', 'Value': ', '.join(ua.get('source_paths', []))},
        {'Field': 'Source hashes', 'Value': ', '.join(ua.get('source_hashes', []))},
        {'Field': 'Synthetic nodes generated', 'Value': str(ua.get('synthetic_nodes_generated', False))},
    ]
    sections.append(_render_section('UA Knowledge', _render_table(ua_rows)))

    if options:
        sections.append(_render_section('Options', _render_options(options)))

    template = TEMPLATE_PATH.read_text(encoding='utf-8')
    html_output = template.replace('{{title}}', _esc(review_payload.get('html', {}).get('title', 'Human Review')))
    html_output = html_output.replace('{{task_id}}', _esc(review_payload.get('task_id', '')))
    html_output = html_output.replace('{{repository}}', _esc(review_payload.get('repository', '')))
    html_output = html_output.replace('{{base_sha}}', _esc(review_payload.get('base_sha', '')))
    html_output = html_output.replace('{{generated_at_utc}}', _esc(review_payload.get('generated_at_utc', '')))
    html_output = html_output.replace('{{sections}}', '\n'.join(sections))
    html_output = html_output.replace('{{authority_notice}}', _esc(review_payload.get('authority_notice', '')))
    return html_output


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description='Generate G01 human review HTML')
    parser.add_argument('--impact', required=True, help='Path to g1-option-impact artifact')
    parser.add_argument('--review', required=True, help='Path to g01-human-review JSON payload')
    parser.add_argument('--output', required=True, help='Output HTML path')
    args = parser.parse_args()

    review_payload = json.loads(Path(args.review).read_text(encoding='utf-8'))
    html_output = render_human_review(args.impact, review_payload)
    Path(args.output).write_text(html_output, encoding='utf-8')
    print(args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
