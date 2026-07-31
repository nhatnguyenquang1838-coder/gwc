from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_workflow(name: str) -> dict[str, object]:
    path = ROOT / '.github' / 'workflows' / name
    return yaml.safe_load(path.read_text(encoding='utf-8'))


class ReleasePublishGuardTests(unittest.TestCase):
    def test_publish_power_yml_blocks_main_push_by_default(self) -> None:
        workflow = load_workflow('publish-power.yml')
        on = workflow.get('on', {})
        if not on:
            on = workflow.get(True, {})
        triggers = on if isinstance(on, list) else [on]
        has_push = any(
            isinstance(trigger, dict) and trigger.get('push') and trigger.get('push', {}).get('branches') == ['main']
            for trigger in triggers
            if isinstance(trigger, dict)
        )
        self.assertFalse(has_push, 'publish-power.yml must not trigger on push to main by default')

    def test_publish_release_yml_requires_workflow_dispatch_only(self) -> None:
        workflow = load_workflow('publish-release.yml')
        on = workflow.get('on', {})
        if not on:
            on = workflow.get(True, {})
        self.assertIn('workflow_dispatch', on)
        self.assertEqual(len(on), 1)

    def test_publish_power_yml_requires_explicit_approval_inputs(self) -> None:
        workflow = load_workflow('publish-power.yml')
        on = workflow.get('on', {})
        if not on:
            on = workflow.get(True, {})
        dispatch = on.get('workflow_dispatch', {})
        self.assertIn('publish_release', dispatch.get('inputs', {}))
        self.assertIn('publish_distribution_branch', dispatch.get('inputs', {}))

    def test_publish_power_yml_no_auto_publish_on_push(self) -> None:
        text = (ROOT / '.github' / 'workflows' / 'publish-power.yml').read_text(encoding='utf-8')
        self.assertNotIn("github.event_name == 'push'", text)
        self.assertNotIn('github.event_name == "push"', text)


if __name__ == '__main__':
    unittest.main()
