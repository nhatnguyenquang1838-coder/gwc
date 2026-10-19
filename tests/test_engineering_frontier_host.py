
import pytest
from test_engineering_work_frontier import setup_frontier


def test_source_bound_host_frontier_loads_real_policy_and_trace_status(tmp_path):
    import json,subprocess
    from tools.node_architect.engineering_host_adapter import read_source_bound_frontier
    c,items=setup_frontier(tmp_path);c['repository']['worktree']=str(tmp_path)
    (tmp_path/'trace.json').write_text(json.dumps({'original_trace_status':'MISSING'}))
    (tmp_path/'code.py').write_text('# source-bound repair input\n')
    profile={'items':[{**items[0],'read_paths':['code.py'],'evidence_requirements':[{'path':'trace.json','field':'original_trace_status','equals':'RECOVERED','name':'original trace'}]},
                      {**items[1],'read_paths':['code.py']}]}
    (tmp_path/'profile.json').write_text(json.dumps(profile))
    def git(*args):return subprocess.check_output(['git','-C',str(tmp_path),*args],text=True).strip()
    git('init','-b','fix/test');git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','bound inputs')
    c['repository']['head_sha']=git('rev-parse','HEAD')
    r=read_source_bound_frontier(c,profile_ref='profile.json',guard=lambda:True)
    assert r['selected_work']['id']=='repair'
    assert next(i for i in r['items'] if i['id']=='trace')['status']=='BLOCKED_EXTERNAL_EVIDENCE'
    (tmp_path/'code.py').write_text('# drift\n')
    with pytest.raises(ValueError,match='ENGINEERING_FRONTIER_SOURCE_DRIFT'):
        read_source_bound_frontier(c,profile_ref='profile.json',guard=lambda:True)
