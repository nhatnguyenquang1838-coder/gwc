"""SCRUM-781 M1 regressions for New Runtime instruction convergence."""
from pathlib import Path

from tools.node_architect.gate_node_routes import select_route_pack

ROOT = Path(__file__).resolve().parents[1]


PROSE_LURES = [
    "autonomous",
    "continue",
    "Human only merges main",
    "legacy compatibility",
    "historical envelope",
    "Slack MVP",
]


def test_route_pack_selector_ignores_prose_and_accepts_only_exact_structured_scenario():
    for lure in PROSE_LURES:
        assert select_route_pack(lure) is None
    assert select_route_pack("ci_failure") == "RP-03"


def test_fresh_instruction_package_declares_universal_default_and_compatibility_boundary():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    project = (ROOT / "projects/gwc/project-instructions.md").read_text(encoding="utf-8")
    extension = (ROOT / "projects/gwc/project-extension.md").read_text(encoding="utf-8")
    hermes = (ROOT / "agents/hermes/agent-instructions.md").read_text(encoding="utf-8")
    autonomous = (ROOT / "agents/autonomous-agent/agent-instructions.md").read_text(encoding="utf-8")
    executor = (ROOT / "skills/executor/SKILL.md").read_text(encoding="utf-8")

    for text in (agents, project, extension, hermes, autonomous, executor):
        assert "UNIVERSAL_RUN_NEW_RUNTIME" in text
        assert "compatibility" in text.lower()
        assert "explicit" in text.lower()

    assert "Hermes Universal Runtime Execution Provider" in hermes
    assert "Slack MVP" not in hermes.splitlines()[0]
    assert "CONTINUE | WAIT_CONTROLLER | TERMINAL" not in hermes
    assert "At `WAIT_CONTROLLER`, stop" not in hermes
    assert "Slack is an optional compatibility adapter" in autonomous
    assert "Slack protocol is an explicit compatibility overlay" in executor


def test_historical_markers_do_not_enable_shadow_compatibility_replay():
    from tests.test_shadow_orchestrator import activation, event, registry
    from tools.node_architect.shadow_orchestrator import run_shadow_event

    replay_event = event()
    replay_event["input_payload"] = {
        "route": "autonomous",
        "history": "old pre-prod evidence / Slack MVP / old loop",
    }
    out = run_shadow_event(
        replay_event,
        registry(),
        activation(),
        observed_revision="abc",
        compatibility_replay=False,
    )
    assert out["status"] == "SHADOW_DISABLED_FAIL_CLOSED"
    assert out["reason_code"] == "SHADOW_RUNTIME_CONTEXT_MISSING"
    assert out["results"] == []
    assert out["authoritative_effect"] == "NONE"
    assert out["authority_granted"] is False
