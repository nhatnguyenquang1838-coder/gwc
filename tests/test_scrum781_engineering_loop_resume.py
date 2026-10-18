"""Resume preparation is not observer qualification or effect authority."""
from pathlib import Path
import unittest

from tools.node_architect.q0_engineering_loop import assess_engineering_resume, engineering_prompt

SID = '20261014_021304_0dc728'
RUN = 'scrum781-q0-fresh-20261010-r1'
HEAD = '0' * 40


class EngineeringResumeTests(unittest.TestCase):
    def context(self, **changes):
        out = dict(expected={'session_id': SID, 'run_id': RUN, 'head_sha': HEAD},
                   observed={'session_id': SID, 'run_id': RUN, 'head_sha': HEAD},
                   loop_role='ENGINEERING_WORK', execute_contract_current=True,
                   user_paused=True, run_hold=False, awaiting_response=False,
                   owner_verified=True, observer_qualified=False, prepare_only=True)
        out.update(changes)
        return out

    def test_prepare_for_user_resume_without_observer(self):
        result = assess_engineering_resume(**self.context())
        self.assertEqual(result['outcome'], 'ENGINEERING_LOOP_RESUME_READY')
        self.assertFalse(result['auto_resume_allowed'])
        self.assertFalse(result['typed_ce_allowed'])
        self.assertFalse(result['effect_authority_granted'])
        self.assertTrue(result['requires_user_resume'])

    def test_current_execution_cannot_ignore_user_pause(self):
        result = assess_engineering_resume(**self.context(prepare_only=False))
        self.assertEqual(result['reason_code'], 'USER_PAUSED')

    def test_engineering_without_observer_is_not_automatically_blocked(self):
        result = assess_engineering_resume(**self.context(user_paused=False, prepare_only=False))
        self.assertEqual(result['outcome'], 'ENGINEERING_PREFLIGHT_PASS')
        self.assertFalse(result['typed_ce_allowed'])
        self.assertFalse(result['effect_authority_granted'])

    def test_boundaries(self):
        for change, reason in [
            ({'run_hold': True}, 'RUN_HOLD'),
            ({'execute_contract_current': False}, 'EXECUTE_CONTRACT_NOT_CURRENT'),
            ({'awaiting_response': True}, 'FIRING_IN_FLIGHT'),
            ({'owner_verified': False}, 'HOST_OWNER_UNVERIFIED'),
            ({'loop_role': 'MAILBOX_OBSERVER'}, 'ENGINEERING_ROLE_REQUIRED'),
        ]:
            with self.subTest(change=change):
                self.assertEqual(assess_engineering_resume(**self.context(**change))['reason_code'], reason)

    def test_identity_drift_is_closed(self):
        for field in ['session_id', 'run_id', 'head_sha']:
            context = self.context()
            context['observed'][field] = 'wrong'
            self.assertEqual(assess_engineering_resume(**context)['reason_code'], 'BINDING_MISMATCH')

    def test_missing_boolean_is_not_truthy_admission(self):
        with self.assertRaises(ValueError):
            assess_engineering_resume(**self.context(execute_contract_current='true'))

    def test_real_owner_firing_can_be_inspected_without_clearing_it(self):
        result = assess_engineering_resume(**self.context(user_paused=False, awaiting_response=True,
                                                         owned_firing_verified=True, prepare_only=False))
        self.assertEqual(result['outcome'], 'ENGINEERING_PREFLIGHT_PASS')
        self.assertEqual(result['effects_executed'], [])

    def test_cli_is_runnable(self):
        import subprocess
        import sys
        script = Path(__file__).resolve().parents[1] / 'scripts/scrum781_engineering_loop.py'
        result = subprocess.run([sys.executable, str(script), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('prepare', result.stdout)
        self.assertIn('inspect', result.stdout)

    def test_prompt_does_not_ask_to_poll_or_resume(self):
        prompt = engineering_prompt(run_id=RUN, session_id=SID,
                                    repository_root=Path('repo'), controller_url='https://chatgpt.com/c/example')
        self.assertIn('ENGINEERING_WORK', prompt)
        self.assertIn('C/E polling and dispatch remain BLOCKED', prompt)
        self.assertIn('Do not change M1 HOLD to PASS', prompt)
        self.assertIn('Do not auto-resume', prompt)
        self.assertIn('one bounded', prompt)
