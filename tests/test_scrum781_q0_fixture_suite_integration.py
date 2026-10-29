"""Both reconstructed fixture classes run through one shared harness, separately.

The C91/E52 class exercises the Universal v2 control-plane replay adapter; the DWO
Login class exercises the requirements-bound auth oracle. They are never merged into
a single claim, and neither authenticates the original DWO incident.
"""
from __future__ import annotations

import copy

import pytest

from scripts.scrum781_q0_fixture_replay import (
    DEFAULT_FIXTURE,
    FixtureError,
    SUITE_C91_E52,
    SUITE_DWO_LOGIN,
    load_dwo_login_suite,
    load_fixture,
    load_suite_fixture,
    run_dwo_login_fixture,
    run_fixture,
    run_suite,
)


def _native_login_route(**kwargs):
    assert kwargs["runtime_epoch"] == "UNIVERSAL_V2_DEVELOPMENT"
    assert kwargs["requested_gate"] == "UR.G2"
    return {"outcome": "UNIVERSAL_ROUTE_ALLOWED", "legacy_route": False, "gate": "UR.G2"}


def test_both_fixture_classes_are_loadable_and_separately_digestable():
    c91, c91_digest = load_fixture(DEFAULT_FIXTURE)
    login, login_digest = load_dwo_login_suite()
    assert c91["fixture_id"] == "SCRUM-781-Q0-C91-E52-RECONSTRUCTED-V1"
    assert login["manifest"]["suite_id"] == "DWO-LOGIN-AUTH-R1-RECONSTRUCTED-V1"
    assert c91_digest != login_digest
    assert c91["incident"]["provenance_class"] == "RECONSTRUCTED_SOURCE_BOUND"
    assert login["manifest"]["incident"]["provenance_class"] == "RECONSTRUCTED_REQUIREMENTS_BOUND"


def test_load_suite_fixture_dispatches_both_classes():
    c91, _ = load_suite_fixture(SUITE_C91_E52)
    login, _ = load_suite_fixture(SUITE_DWO_LOGIN)
    assert c91["fixture_id"].endswith("C91-E52-RECONSTRUCTED-V1")
    assert login["manifest"]["suite_id"] == "DWO-LOGIN-AUTH-R1-RECONSTRUCTED-V1"


def test_unknown_suite_name_fails_closed():
    with pytest.raises(FixtureError, match="FIXTURE_SUITE_UNKNOWN"):
        load_suite_fixture("does-not-exist")


def test_dwo_login_native_run_through_shared_pipeline(monkeypatch):
    from tools.node_architect import universal_run_epoch
    suite, _ = load_dwo_login_suite()
    real_route = universal_run_epoch.route_universal_request
    calls = []

    def observed_real_route(**kwargs):
        calls.append(kwargs)
        return real_route(**kwargs)

    monkeypatch.setattr(universal_run_epoch, "route_universal_request", observed_real_route)
    result = run_dwo_login_fixture(suite, engine="native")
    assert calls == [{"runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT", "requested_gate": "UR.G2", "requested_action": "q0_execute_probe"}]
    assert result["result"] == "RECONSTRUCTED_LOGIN_CONTRACT_PASS"
    assert result["fixture_id"] == "DWO-LOGIN-AUTH-R1-RECONSTRUCTED-V1"
    assert result["authentic_dwo_login_replay"] is False
    assert result["q0_l3_qualified"] is False
    assert result["native_gate_receipt"] is None
    assert result["executed_effects"] == []


def test_run_suite_dispatch_runs_each_class_with_its_own_semantics():
    c91 = run_suite(SUITE_C91_E52)
    login = run_suite(SUITE_DWO_LOGIN)
    assert c91["fixture_id"] == "SCRUM-781-Q0-C91-E52-RECONSTRUCTED-V1"
    assert c91["result"] == "RECONSTRUCTED_SUBCASE_PASS"
    assert login["fixture_id"] == "DWO-LOGIN-AUTH-R1-RECONSTRUCTED-V1"
    assert login["result"] == "RECONSTRUCTED_LOGIN_CONTRACT_PASS"
    assert c91["authentic_dwo_login_replay"] is False
    assert login["authentic_dwo_login_replay"] is False


def test_c91_regression_still_passes_through_shared_pipeline():
    fixture, _ = load_fixture(DEFAULT_FIXTURE)
    result = run_fixture(fixture)
    assert result["result"] == "RECONSTRUCTED_SUBCASE_PASS"
    assert result["authentic_dwo_login_replay"] is False
    assert result["q0_l3_qualified"] is False


def test_dwo_login_provenance_upgrade_fails_closed():
    suite, _ = load_dwo_login_suite()
    modified = copy.deepcopy(suite)
    modified["manifest"]["incident"]["provenance_class"] = "ORIGINAL_RECOVERED"
    with pytest.raises(FixtureError, match="LOGIN_FIXTURE_BINDING_INVALID"):
        run_dwo_login_fixture(modified, engine="native")


def test_dwo_login_unauthorized_effect_claim_fails_closed():
    suite, _ = load_dwo_login_suite()

    def wrong_route(**kwargs):
        return {**_native_login_route(**kwargs), "authority_granted": True}

    import scripts.scrum781_q0_login_fixture as login_mod
    with pytest.raises(login_mod.LoginFixtureError, match="LOGIN_GWC_UNAUTHORIZED_EFFECT_CLAIM"):
        login_mod.run_login_suite(suite, route=wrong_route)


def test_dwo_login_langgraph_optional_parity():
    pytest.importorskip("langgraph.graph")
    suite, _ = load_dwo_login_suite()
    native = run_dwo_login_fixture(suite, engine="native")
    graph = run_dwo_login_fixture(suite, engine="langgraph")
    assert graph["result"] == native["result"]
    assert graph["checkpoint_class"] == "EPHEMERAL_GRAPH_MECHANICS_ONLY"
    assert graph["authentic_dwo_login_replay"] is False


def test_dwo_login_unknown_engine_fails_closed():
    suite, _ = load_dwo_login_suite()
    with pytest.raises(FixtureError, match="LOGIN_ENGINE_UNSUPPORTED"):
        run_dwo_login_fixture(suite, engine="invented")


def test_shared_pipeline_never_merges_classes_into_one_claim():
    c91 = run_suite(SUITE_C91_E52)
    login = run_suite(SUITE_DWO_LOGIN)
    assert c91["suite"] == SUITE_C91_E52
    assert login["suite"] == SUITE_DWO_LOGIN
    assert c91["incident_provenance"] != login["incident_provenance"]
    assert c91["authentic_dwo_login_replay"] is False
    assert login["authentic_dwo_login_replay"] is False