"""Regression: Universal v2 native mode must not implicitly import Slack MVP."""
from tools.node_architect.hermes_bootstrap_route import resolve_hermes_bootstrap_route as route


def test_native_default_is_not_slack():
    r = route(runtime_epoch="UNIVERSAL_V2_DEVELOPMENT", working_mode=None)
    assert r["status"] == "ROUTE_RESOLVED"
    assert r["role_overlays"] == ["agents/hermes/native-universal-v2.md"]
    assert r["effect_admission"] is False


def test_slack_requires_explicit_verified_binding():
    r = route(runtime_epoch="UNIVERSAL_V2_DEVELOPMENT", working_mode="slack_controller_executor",
              slack_binding_verified=True)
    assert r["status"] == "ROUTE_RESOLVED"
    assert "agents/hermes/agent-instructions.md" in r["role_overlays"]
    r = route(runtime_epoch="UNIVERSAL_V2_DEVELOPMENT", working_mode="slack_controller_executor")
    assert r["status"] == "ROUTE_UNRESOLVED"
    assert r["role_overlays"] == []


def test_ambiguous_or_legacy_fails_closed():
    for epoch, mode, binding in [
        ("LEGACY_GWC_V1", "native_universal_v2", False),
        ("", None, False),
        ("UNIVERSAL_V2_DEVELOPMENT", "unexpected", False),
        ("UNIVERSAL_V2_DEVELOPMENT", "native_universal_v2", True),
    ]:
        r = route(runtime_epoch=epoch, working_mode=mode, slack_binding_verified=binding)
        assert r["status"] == "ROUTE_UNRESOLVED"
        assert r["read_only_allowed"] is True
        assert r["effect_admission"] is False
