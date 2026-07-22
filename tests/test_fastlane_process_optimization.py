from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_e2e_allows_autonomous_steps_after_g2_but_blocks_merge():
    text = read("core/E2E_DRAFT_PR_DELIVERY_RULE.md")
    assert "After valid approval, the agent may proceed without requesting confirmation" in text
    assert "The agent must provide concise progress updates" in text
    assert "Mark the Draft PR ready for review after G3 `PASS`" in text
    assert "G4 remains a separate human decision" in text
    assert "Merge or enable auto-merge" in text


def test_fastlane_limits_g2_to_branch_files_pr_and_blocks_higher_gates():
    text = read("core/workflows/GWC_FASTLANE_BOOTSTRAP_WORKFLOW_v0.1.md")
    assert "Allowed connector actions after G2 approval" in text
    assert "create a dedicated guarded branch" in text
    assert "create or update scoped files" in text
    assert "open or update a Draft Pull Request" in text
    assert "merge;" in text
    assert "auto-merge;" in text
    assert "production data" in text


def test_chatgpt_overlay_requires_auto_ready_when_supported_then_g4_token():
    text = read("agents/chatgpt-agent/agent-instructions.md")
    assert "metadata transition from Draft to Ready for review after G3 `PASS`" in text
    assert "G4 merge remains a separate exact human approval" in text
    assert "G3 PASS | G4 merge approval request after marking Draft PR ready for review when supported" in text


def test_dwc_contract_keeps_ready_for_review_as_g3_metadata_only():
    text = read("agents/dwc/agent-instructions.md")
    assert "Ready-for-review connector action contract" in text
    assert "This action grants no merge permission" in text
    assert "Upon G3 `PASS`, mark the Draft PR ready for review" in text
    assert "G4 merge, G5 deploy, and G6 production operations always require a separate" in text
