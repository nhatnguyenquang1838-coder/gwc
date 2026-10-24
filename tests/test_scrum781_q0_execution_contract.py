"""SCRUM-781: executable Q0 contract cannot silently regress into read-only PLAN."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
def test_q0_execution_plan_stays_executable_and_scoped():
    d=json.loads((ROOT/"core/node-architect/scrum781-q0-fresh-execution-plan-r2.json").read_text())
    assert d["contract_mode"]=="EXECUTE"
    assert d["scope"]["writable_targets"]
    assert "modify_approved_files" in d["scope"]["allowed_actions"]
    assert "run_sandboxed_validation" in d["scope"]["allowed_actions"]
    assert "merge_approved_pr" in d["scope"]["denied_actions"]
    assert "deploy_approved_release" in d["scope"]["denied_actions"]
    assert len(d["work_packages"])>=5
    assert "ALL_ACCEPTANCE_CRITERIA_PASS" in d["continue_until"]

def test_q0_recursive_g1_has_atomic_leaves():
    d=json.loads((ROOT/"core/node-architect/scrum781-q0-fresh-execution-plan-r2.json").read_text())
    def visit(node):
        kids=node.get("children",[])
        if node.get("atomic"): assert not kids; return 1
        assert kids
        return sum(visit(k) for k in kids)
    assert visit(d["recursive_plan"])>=6
