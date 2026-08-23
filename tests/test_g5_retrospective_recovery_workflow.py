from pathlib import Path


WORKFLOW = Path('.github/workflows/g5-retrospective-recovery.yml')


def _permissions_block() -> str:
    text = WORKFLOW.read_text(encoding='utf-8')
    start = text.index('permissions:\n')
    end = text.index('\njobs:\n', start)
    return text[start:end]


def test_g5_retrospective_recovery_can_publish_pr_receipt_comments():
    permissions = _permissions_block()

    assert 'issues: write' in permissions
    assert 'pull-requests: write' in permissions
    assert 'pull-requests: read' not in permissions


def test_g5_retrospective_recovery_keeps_retrospective_receipt_guardrails():
    text = WORKFLOW.read_text(encoding='utf-8')

    assert '<!-- gwc:g5-retrospective-recovery' in text
    assert 'github.rest.issues.createComment' in text
    assert 'retrospective evidence-recovery receipt only' in text
    assert 'does not backdate G4 authority' in text
    assert 'does not authorize deployment' in text
    assert 'G6' in text
    assert 'artifact upload already completed' in text
