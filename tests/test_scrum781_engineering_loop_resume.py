"""Resume preparation is not observer qualification or effect authority."""
from pathlib import Path
import unittest

from tools.node_architect.q0_engineering_loop import assess_engineering_resume, engineering_prompt

SID = '20261014_021304_0dc728'
RUN = 'scrum781-q0-fresh-20261010-r1'
HEAD = '0' * 40


def _foreign_site_packages(prefix='/opt/lib'):
    import sys
    major, minor = sys.version_info[:2]
    other_minor = minor + 1 if minor < 20 else minor - 1
    return f'{prefix}/python{major}.{other_minor}/site-packages'


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

    def test_prompt_routes_engineering_read_inside_graph_not_protected_observer(self):
        prompt=engineering_prompt(run_id=RUN,session_id=SID,repository_root=Path('repo'),controller_url='https://chatgpt.com/c/example')
        self.assertIn('--workflow-mode Q0_ENGINEERING_COORDINATION',prompt)
        self.assertIn('Engineering M1 owns the one-shot #595 read',prompt)
        self.assertIn('PROTECTED_TYPED_CE',prompt)

    def test_prompt_does_not_ask_to_poll_or_resume(self):
        prompt = engineering_prompt(run_id=RUN, session_id=SID,
                                    repository_root=Path('repo'), controller_url='https://chatgpt.com/c/example')
        self.assertIn('ENGINEERING_WORK', prompt)
        self.assertIn('C/E polling and dispatch remain BLOCKED', prompt)
        self.assertIn('Do not change M1 HOLD to PASS', prompt)
        self.assertIn('Do not auto-resume', prompt)
        self.assertIn('one bounded', prompt)


class Q0BrowserBindingTests(unittest.TestCase):
    def setUp(self):
        import hashlib
        import json
        import tempfile
        from tools.node_architect.q0_browser_binding import current_binding_path
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.home = Path(self._temp.name)
        self.run_dir = self.home / 'loop-checkpoints' / RUN
        self.run_dir.mkdir(parents=True)
        self.historical = {
            'run_id': RUN, 'session_id': SID, 'send_outcome': 'SENT_VERIFIED',
            'conversation_url': 'https://chatgpt.com/g/g-p-project-dw/c/old-chat',
            'marker': 'DWA781-R39-039e1f6',
        }
        self.historical_bytes = json.dumps(self.historical, sort_keys=True).encode()
        self.receipt_path = self.run_dir / 'browser-report39-039e1f6-delivery.json'
        self.receipt_path.write_bytes(self.historical_bytes)
        self.parent_digest = hashlib.sha256(self.historical_bytes).hexdigest()
        self.binding_path = current_binding_path(self.home, RUN)

    def current(self, **changes):
        binding = {
            'run_id': RUN, 'session_id': SID,
            'conversation_url': 'https://chatgpt.com/g/g-p-project-dw/c/new-chat',
            'marker': 'DWA781-Q0-CURRENT-001', 'report_ref': 'report-001',
            'in_app_delivered': True, 'user_turn_observed': True,
            'previous_receipt_path': str(self.receipt_path),
            'previous_receipt_sha256': self.parent_digest,
        }
        binding.update(changes)
        return binding

    def test_legacy_receipt_still_accepted(self):
        from tools.node_architect.q0_browser_binding import resolve_binding
        self.historical['conversation_url'] = 'https://chatgpt.com/g/g-p-project-dw/c/old-chat'
        self.receipt_path.write_text(__import__('json').dumps(self.historical))
        result = resolve_binding(self.home, run_id=RUN, session_id=SID,
                                 controller_url=self.historical['conversation_url'])
        self.assertEqual(result['mode'], 'LEGACY')

    def test_new_url_without_current_binding_fails_closed(self):
        from tools.node_architect.q0_browser_binding import BrowserBindingError, resolve_binding
        with self.assertRaises(BrowserBindingError) as raised:
            resolve_binding(self.home, run_id=RUN, session_id=SID,
                            controller_url=self.current()['conversation_url'])
        self.assertEqual(raised.exception.code, 'CURRENT_BINDING_MISSING')

    def test_chained_binding_accepted(self):
        from tools.node_architect.q0_browser_binding import resolve_binding
        self.binding_path.parent.mkdir(parents=True)
        self.binding_path.write_text(__import__('json').dumps(self.current()))
        result = resolve_binding(self.home, run_id=RUN, session_id=SID,
                                 controller_url=self.current()['conversation_url'])
        self.assertEqual(result, {'mode': 'CHAINED', 'marker': 'DWA781-Q0-CURRENT-001',
                                  'conversation_url': self.current()['conversation_url']})

    def test_chained_binding_rejects_parent_digest_mismatch(self):
        from tools.node_architect.q0_browser_binding import BrowserBindingError, validate_binding_chain
        with self.assertRaises(BrowserBindingError) as raised:
            validate_binding_chain(self.historical, self.current(previous_receipt_sha256='wrong'),
                                   run_id=RUN, session_id=SID,
                                   controller_url=self.current()['conversation_url'])
        self.assertEqual(raised.exception.code, 'BINDING_PARENT_DIGEST_MISMATCH')

    def test_chained_binding_rejects_marker_reuse(self):
        from tools.node_architect.q0_browser_binding import BrowserBindingError, validate_binding_chain
        with self.assertRaises(BrowserBindingError) as raised:
            validate_binding_chain(self.historical, self.current(marker=self.historical['marker']),
                                   run_id=RUN, session_id=SID,
                                   controller_url=self.current()['conversation_url'])
        self.assertEqual(raised.exception.code, 'BINDING_MARKER_REUSED')

    def test_chained_binding_rejects_other_project(self):
        from tools.node_architect.q0_browser_binding import BrowserBindingError, validate_binding_chain
        other = self.current(conversation_url='https://chatgpt.com/g/g-p-other-dw/c/new-chat')
        with self.assertRaises(BrowserBindingError) as raised:
            validate_binding_chain(self.historical, other, run_id=RUN, session_id=SID,
                                   controller_url=other['conversation_url'])
        self.assertEqual(raised.exception.code, 'BINDING_PROJECT_MISMATCH')

    def test_chained_binding_requires_in_app_delivery_evidence(self):
        from tools.node_architect.q0_browser_binding import BrowserBindingError, validate_binding_chain
        with self.assertRaises(BrowserBindingError) as raised:
            validate_binding_chain(self.historical, self.current(in_app_delivered=False),
                                   run_id=RUN, session_id=SID,
                                   controller_url=self.current()['conversation_url'])
        self.assertEqual(raised.exception.code, 'BINDING_NOT_DELIVERED')


class Q0PythonEnvTests(unittest.TestCase):
    def test_foreign_site_packages_entries_detected(self):
        from tools.node_architect.q0_python_env import foreign_pythonpath_entries
        foreign = _foreign_site_packages()
        self.assertEqual(foreign_pythonpath_entries({'PYTHONPATH': foreign}), [foreign])

    def test_same_version_site_packages_entry_kept(self):
        import sys
        from tools.node_architect.q0_python_env import foreign_pythonpath_entries
        major, minor = sys.version_info[:2]
        entry = f'/opt/lib/python{major}.{minor}/site-packages'
        self.assertEqual(foreign_pythonpath_entries({'PYTHONPATH': entry}), [])

    def test_sanitize_removes_foreign_entry_from_syspath_and_environ(self):
        import os
        import sys
        from tools.node_architect.q0_python_env import sanitize_python_path
        foreign = _foreign_site_packages()
        old_env = os.environ.get('PYTHONPATH')
        old_path = list(sys.path)
        try:
            os.environ['PYTHONPATH'] = os.pathsep.join([foreign, '/keep/me'])
            sys.path.insert(0, foreign)
            self.assertEqual(sanitize_python_path(), [foreign])
            self.assertNotIn(foreign, sys.path)
            self.assertEqual(os.environ['PYTHONPATH'], '/keep/me')
        finally:
            sys.path[:] = old_path
            if old_env is None:
                os.environ.pop('PYTHONPATH', None)
            else:
                os.environ['PYTHONPATH'] = old_env

    def test_clean_env_sets_path_and_drops_foreign_pythonpath(self):
        import os
        from tools.node_architect.q0_python_env import clean_env
        foreign = _foreign_site_packages()
        result = clean_env({'PATH': os.pathsep.join(['/usr/bin', '/bin']),
                            'PYTHONPATH': os.pathsep.join([foreign, '/keep'])})
        self.assertNotIn(foreign, result.get('PYTHONPATH', ''))
        py = __import__('tools.node_architect.q0_python_env', fromlist=['canonical_python']).canonical_python()
        self.assertEqual(result['PATH'].split(os.pathsep)[0], str(py.parent))
        self.assertEqual(result['PATH'].split(os.pathsep).count(str(py.parent)), 1)

    def test_canonical_python_prefers_env_var_then_venv_then_sys_executable(self):
        import os
        from pathlib import Path
        from unittest.mock import patch
        from tools.node_architect import q0_python_env as envmod
        custom = Path.cwd() / ('custom-python.exe' if os.name == 'nt' else 'custom-python')
        with patch.dict(os.environ, {'Q0_PYTHON': str(custom)}):
            with patch.object(Path, 'is_file', autospec=True, side_effect=lambda self: self == custom), patch('os.access', side_effect=lambda path, mode: Path(path) == custom):
                self.assertEqual(envmod.canonical_python(), custom)
        expected_venv = envmod._canonical_venv() / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        with patch.dict(os.environ, {'Q0_PYTHON': ''}):
            with patch.object(Path, 'exists', autospec=True, side_effect=lambda self: self == expected_venv):
                with patch.object(Path, 'is_file', return_value=True), patch('os.access', return_value=True):
                    self.assertEqual(envmod.canonical_python(), expected_venv)
            with patch.object(Path, 'exists', return_value=False):
                self.assertEqual(envmod.canonical_python(), Path(__import__('sys').executable))

    def test_cli_help_survives_foreign_pythonpath(self):
        import os
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            foreign = Path(_foreign_site_packages(prefix=f'{directory}/lib'))
            foreign.mkdir(parents=True)
            env = os.environ.copy()
            env['PYTHONPATH'] = str(foreign)
            script = Path(__file__).resolve().parents[1] / 'scripts/scrum781_engineering_loop.py'
            result = subprocess.run([sys.executable, str(script), '--help'], env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
