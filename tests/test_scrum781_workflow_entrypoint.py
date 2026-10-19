"""Loop-to-real-graph wiring; not observer admission or browser delivery."""
import argparse
import pytest
from scripts import scrum781_engineering_loop as cli


def test_workflow_invokes_real_graph_and_reads_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setattr(cli, 'inspect', lambda args: {
        'outcome': 'ENGINEERING_PREFLIGHT_PASS', 'run_id': 'scrum781-q0-fresh-20261010-r1',
        'code_head': cli.build_q0_operation(cli.ROOT, activity_id='test')[0]['head_sha'], 'native_loop': {'ticks_fired': 99}})
    result = cli.workflow(argparse.Namespace(command='workflow', session='test-session', tick=None,
        workflow_mode='PROTECTED_TYPED_CE', controller_url='https://chatgpt.com/c/fixture'))
    assert result['workflow']['verdict'] == {
        'status': 'HOLD', 'reason_code': 'OBSERVER_UNQUALIFIED', 'current_activity': 'M1'}
    assert result['workflow']['checkpoint_readback'] == 'PASS'
    assert result['workflow']['executed_effects'] == []
    assert result['trigger'] == 'EXPLICIT_USER_REQUEST_NOT_NATIVE_TICK'


def test_existing_checkpoint_is_not_replaced_when_head_changes(tmp_path):
    import sqlite3
    root=tmp_path/'host';old=root/'old'
    old.mkdir(parents=True)
    p=old/'checkpoint.sqlite'
    with sqlite3.connect(p) as db:
        db.execute('CREATE TABLE workflow (run TEXT PRIMARY KEY)');db.execute('INSERT INTO workflow VALUES (?)',('run',))
    assert cli.select_workflow_checkpoint(root,'run')==p


def test_preflight_denial_never_invokes_graph(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setattr(cli, 'inspect', lambda args: {'outcome': 'BLOCKED', 'reason_code': 'HOST_OWNER_UNVERIFIED'})
    with pytest.raises(ValueError, match='HOST_OWNER_UNVERIFIED'):
        cli.workflow(argparse.Namespace(command='workflow', session='test-session', tick=99))
    assert not list(tmp_path.rglob('checkpoint.json'))
