"""Task-aware coordination: fixtures are unit evidence, never native admission."""
import copy
import pytest
from tools.node_architect.task_context_binding import validate_task_context


def context(task='TASK-A'):
    return {'schema_version': 1, 'task': {'id': task, 'objective': 'Review runtime', 'acceptance_criteria': ['Exact readback'], 'source_ref': 'plan.json'},
            'run': {'id': 'run-'+task, 'runtime_epoch': 'UNIVERSAL_V2_DEVELOPMENT', 'runtime_plan_ref': 'plan.json', 'runtime_plan_digest': 'sha256:'+'a'*64},
            'repository': {'name': 'owner/repo', 'branch': 'fix/test', 'head_sha': 'a'*40, 'worktree': '/fixture'},
            'controller': {'type': 'GPT', 'conversation_url': 'https://chatgpt.com/c/fixture', 'interaction_mode': 'hermes_skill'},
            'executor': {'type': 'hermes', 'session_id': 'session'},
            'workflow': {'id': 'generic-m1-m7', 'checkpoint_ref': '/fixture/checkpoint', 'activities': ['M1','M2','M3','M4','M5','M6','M7']},
            'capabilities': {'controller_exchange': {'provider': 'hermes_skills', 'skill_ref': 'dwa-gpt-exchange', 'transport': 'browser', 'receipt_type': 'BROWSER_EXCHANGE_VERIFIED'}}}


@pytest.mark.parametrize('task', ['TASK-A','TASK-B'])
def test_context_is_task_generic(task):
    assert validate_task_context(context(task))['task']['id'] == task


def test_missing_objective_is_rejected():
    c = context(); c['task']['objective'] = ''
    with pytest.raises(ValueError, match='TASK_OBJECTIVE_REQUIRED'):
        validate_task_context(c)


def test_browser_cannot_claim_typed_admission():
    c = context(); c['capabilities']['controller_exchange']['receipt_type'] = 'TYPED_CE_ADMITTED'
    with pytest.raises(ValueError, match='BROWSER_CAPABILITY_INVALID'):
        validate_task_context(c)
