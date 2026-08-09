from pathlib import Path

WORKFLOW = Path('.github/workflows/g5-preprod-evidence.yml').read_text(encoding='utf-8')
VALIDATOR = Path('tools/node_architect/validate_g5_ci_verification.py').read_text(encoding='utf-8')


def test_preprod_handler_listens_to_preprod_workflow_runs():
    assert 'branches: [pre-prod]' in WORKFLOW
    assert "github.event.workflow_run.head_branch == 'pre-prod'" in WORKFLOW


def test_exact_sha_lookup_uses_actual_target_branch():
    assert 'branch: targetBranch' in WORKFLOW
    assert 'head_sha: mergeSha' in WORKFLOW
    assert "targetBranch !== 'pre-prod'" in WORKFLOW


def test_main_is_not_hardcoded_in_preprod_lookup():
    assert "branch: 'main'" not in WORKFLOW
    assert "head_branch == 'main'" not in WORKFLOW


def test_existing_g5_validator_is_branch_agnostic():
    assert 'run["head_sha"] != merge_sha' in VALIDATOR
    assert "head_branch == 'main'" not in VALIDATOR
