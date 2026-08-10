from pathlib import Path

WORKFLOW = Path('.github/workflows/g5-preprod-evidence.yml').read_text(encoding='utf-8')
VALIDATOR = Path('tools/node_architect/validate_g5_ci_verification.py').read_text(encoding='utf-8')
VALIDATE_WORKFLOW = Path('.github/workflows/validate-instructions.yml').read_text(encoding='utf-8')
BUILD_WORKFLOW = Path('.github/workflows/build-packages.yml').read_text(encoding='utf-8')


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


def test_required_g5_producers_run_on_preprod_pushes():
    for producer in (VALIDATE_WORKFLOW, BUILD_WORKFLOW):
        assert '      - main\n      - pre-prod' in producer


def test_push_comment_resolution_is_target_branch_aware():
    for producer in (VALIDATE_WORKFLOW, BUILD_WORKFLOW):
        assert "['refs/heads/main', 'refs/heads/pre-prod']" in producer
        assert "event_label: `push:${targetBranch}`" in producer
        assert "context.ref === 'refs/heads/main'" not in producer


def test_partial_exact_sha_observation_is_pending_not_incomplete():
    assert "const pendingStatuses = ['queued', 'waiting', 'requested', 'in_progress']" in WORKFLOW
    assert "? 'CI_PENDING'" in WORKFLOW
    assert "checkpoint_required: classification === 'CI_PENDING'" in WORKFLOW
    assert "next required workflow_run completion" in WORKFLOW


def test_autonomous_preprod_g5_is_explicitly_non_blocking():
    assert "post-merge G5 is NOT REQUIRED for task completion or dependency unlock" in WORKFLOW
    assert "core.setOutput('applicable', 'false')" in WORKFLOW
    assert "core.setOutput('classification', 'NOT_REQUIRED_AUTONOMOUS_PREPROD')" in WORKFLOW
