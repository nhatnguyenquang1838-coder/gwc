"""CR-03: explicit additive source reconciliation, never silent context reuse."""
from contextlib import closing
from copy import deepcopy
import sqlite3,json
import pytest
from test_task_context_binding import context
from tools.node_architect.task_context_binding import digest
from tools.node_architect.task_m1_m7_runner import reconcile_source_head


def checkpoint(c):
    db=sqlite3.connect(c['workflow']['checkpoint_ref'])
    db.execute('CREATE TABLE workflow (run TEXT PRIMARY KEY, context_digest TEXT,state TEXT)')
    db.execute('INSERT INTO workflow VALUES (?,?,?)',(c['run']['id'],digest(c),json.dumps({'verdict':{'current_activity':'M1','status':'HOLD','reason_code':'OBSERVER_UNQUALIFIED'},'checkpoint_projection':{'head_sha':c['repository']['head_sha'],'base_sha':c['repository']['head_sha']},'graph_state':{'executed_effects':[]}})))
    db.commit();db.close()


def test_reconciliation_rejects_any_non_head_context_change(tmp_path):
    c=context();c['workflow']['checkpoint_ref']=str(tmp_path/'cp');checkpoint(c)
    new=deepcopy(c);new['repository']['head_sha']='b'*40;new['task']['objective']='other'
    with pytest.raises(ValueError,match='SOURCE_RECONCILE_NON_HEAD_DRIFT'):
        reconcile_source_head(c,new,repository_root=tmp_path,reason='additive repair')


def test_reconciliation_reuses_checkpoint_after_real_additive_commits(tmp_path):
    import subprocess
    def git(*args):
        return subprocess.check_output(['git','-C',str(tmp_path),*args],text=True).strip()
    git('init','-b','fix/test');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-m','base')
    c=context();c['repository']['head_sha']=git('rev-parse','HEAD');c['repository']['worktree']=str(tmp_path)
    c['workflow']['checkpoint_ref']=str(tmp_path/'cp');checkpoint(c)
    git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-m','repair')
    new=deepcopy(c);new['repository']['head_sha']=git('rev-parse','HEAD')
    r=reconcile_source_head(c,new,repository_root=tmp_path,reason='fixture additive commit')
    assert r['checkpoint_readback']=='PASS' and r['native_state_modified'] is False
    with closing(sqlite3.connect(c['workflow']['checkpoint_ref'])) as db:
        with db:
            assert db.execute('SELECT context_digest FROM workflow').fetchone()[0]==digest(new)
            assert db.execute('SELECT count(*) FROM source_reconciliations').fetchone()[0]==1


def test_reconciliation_requires_real_additive_git_ancestry(tmp_path):
    c=context();c['workflow']['checkpoint_ref']=str(tmp_path/'cp');checkpoint(c)
    new=deepcopy(c);new['repository']['head_sha']='b'*40
    with pytest.raises(ValueError,match='SOURCE_RECONCILE_GIT_BINDING_REQUIRED'):
        reconcile_source_head(c,new,repository_root=tmp_path,reason='repair')
