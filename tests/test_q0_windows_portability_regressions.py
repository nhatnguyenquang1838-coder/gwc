"""Portable safety regressions; capabilities are tested, never inferred from OS."""
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import scrum781_q0_replay_fixture as replay
from tools.node_architect import node_evidence_ledger as ledger
from tools.node_architect import engineering_host_adapter as host


def test_windows_append_lock_uses_one_fixed_byte_after_file_growth(tmp_path, monkeypatch):
    positions = []
    def locking(fd, action, count):
        positions.append((action, os.lseek(fd, 0, os.SEEK_CUR), count))
    fake = SimpleNamespace(LK_LOCK=1, LK_UNLCK=2, locking=locking)
    monkeypatch.setattr(ledger, 'fcntl', None)
    monkeypatch.setattr(ledger, 'msvcrt', fake, raising=False)
    path = tmp_path / 'events.jsonl'
    path.write_bytes(b'old\n')
    ledger.NodeEvidenceLedger._locked_write(path, 'first')
    ledger.NodeEvidenceLedger._locked_write(path, 'second')
    assert positions == [(1, 0, 1), (2, 0, 1), (1, 0, 1), (2, 0, 1)]
    assert path.read_text().splitlines() == ['old', 'first', 'second']


@pytest.mark.parametrize('reader', ['artifact', 'cli'])
def test_replay_without_race_safe_primitives_refuses_before_any_path_read(tmp_path, monkeypatch, reader):
    path = tmp_path / 'tests' / 'input.json'
    path.parent.mkdir()
    raw = b'{}'
    path.write_bytes(raw)
    monkeypatch.setattr(replay.os, 'supports_dir_fd', set())
    reads = []
    original = Path.read_bytes
    def track(p):
        reads.append(p)
        return original(p)
    monkeypatch.setattr(Path, 'read_bytes', track)
    with pytest.raises(replay.ReplayFixtureError, match='RACE_SAFE_READ_UNAVAILABLE'):
        if reader == 'artifact':
            replay._read_artifact({'path': 'tests/input.json', 'sha256': replay.digest(raw)}, tmp_path)
        else:
            replay._read_cli_json(str(path))
    assert reads == []


def test_engineering_frontier_rejects_crlf_source_drift_before_policy_parse(tmp_path, monkeypatch):
    from test_engineering_work_frontier import setup_frontier
    c, _ = setup_frontier(tmp_path)
    path = tmp_path / 'policy.json'
    path.write_bytes(b'{"items":[]}\r\n')
    c['repository'].update(worktree=str(tmp_path), head_sha='a' * 40)
    c['workflow']['checkpoint_ref'] = str(tmp_path / 'absent.sqlite')
    def git_output(argv, **kw):
        return 'a' * 40 + '\n' if 'rev-parse' in argv else b'{"items":[]}\n'
    monkeypatch.setattr(host.subprocess, 'check_output', git_output)
    with pytest.raises(ValueError, match='ENGINEERING_FRONTIER_SOURCE_DRIFT'):
        host.read_source_bound_frontier(c, profile_ref='policy.json', guard=lambda: True)


# The repository's canonical validate job uses unittest discovery. Keep these
# safety regressions active there as well as in the focused pytest invocation.
import tempfile
import unittest


class TestPortableSafetyCI(unittest.TestCase):
    def exercise(self, check, *args):
        with tempfile.TemporaryDirectory() as tmp, pytest.MonkeyPatch.context() as mp:
            check(Path(tmp), mp, *args)

    def test_fixed_lock_byte(self):
        self.exercise(test_windows_append_lock_uses_one_fixed_byte_after_file_growth)

    def test_readers_fail_closed(self):
        for reader in ('artifact', 'cli'):
            with self.subTest(reader=reader):
                self.exercise(test_replay_without_race_safe_primitives_refuses_before_any_path_read, reader)

    def test_exact_source_bytes(self):
        self.exercise(test_engineering_frontier_rejects_crlf_source_drift_before_policy_parse)

    @unittest.skipUnless(os.open in os.supports_dir_fd and hasattr(os, 'O_NOFOLLOW'), 'requires POSIX race-safe read backend')
    def test_posix_artifact_read_is_bounded_and_digest_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'tests' / 'input.json'
            path.parent.mkdir()
            raw = b'{}'
            path.write_bytes(raw)
            ref = {'path': 'tests/input.json', 'sha256': replay.digest(raw)}
            self.assertEqual(raw, replay._read_artifact(ref, root))
            self.assertEqual({}, replay._read_cli_json(str(path)))
            with path.open('wb') as stream:
                stream.truncate(replay.MAX_BYTES + 1)
            with self.assertRaisesRegex(replay.ReplayFixtureError, 'NOT_BOUNDED_FILE'):
                replay._read_artifact(ref, root)
            with self.assertRaisesRegex(replay.ReplayFixtureError, 'NOT_BOUNDED_FILE'):
                replay._read_cli_json(str(path))

    @unittest.skipUnless(os.open in os.supports_dir_fd and hasattr(os, 'O_NOFOLLOW'), 'requires POSIX race-safe read backend')
    def test_posix_parent_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'outside').mkdir()
            (root / 'outside' / 'input.json').write_bytes(b'{}')
            (root / 'tests').symlink_to(root / 'outside', target_is_directory=True)
            with self.assertRaisesRegex(replay.ReplayFixtureError, 'ARTIFACT_UNREADABLE'):
                replay._read_artifact({'path': 'tests/input.json', 'sha256': replay.digest(b'{}')}, root)

    @unittest.skipUnless(os.name == 'nt', 'native Windows byte-range locking')
    def test_native_writer_waits_for_fixed_lock(self):
        import msvcrt
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            lock_path = path.with_suffix('.jsonl.lock')
            with lock_path.open('a+b') as held:
                held.seek(0)
                msvcrt.locking(held.fileno(), msvcrt.LK_LOCK, 1)
                process = None
                error = ''
                try:
                    code = ('from pathlib import Path; '
                            'from tools.node_architect.node_evidence_ledger import NodeEvidenceLedger; '
                            'import sys; print("ready", flush=True); '
                            'NodeEvidenceLedger._locked_write(Path(sys.argv[1]), "record")')
                    process = subprocess.Popen([sys.executable, '-c', code, str(path)],
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    self.assertEqual('ready', process.stdout.readline().strip())
                    with self.assertRaises(subprocess.TimeoutExpired):
                        process.wait(timeout=0.3)
                    self.assertFalse(path.exists(), 'writer entered while another process held its lock')
                finally:
                    held.seek(0)
                    msvcrt.locking(held.fileno(), msvcrt.LK_UNLCK, 1)
                    if process is not None:
                        try:
                            _, error = process.communicate(timeout=15)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.communicate()
                            raise
                self.assertEqual(0, process.returncode, error)
                self.assertEqual(['record'], path.read_text().splitlines())
