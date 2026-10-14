"""Q0 reconstructed fixture cannot be mistaken for original DWO replay."""
import copy

import pytest

from scripts.scrum781_q0_fixture_replay import (
    DEFAULT_FIXTURE, ROOT, FixtureError, load_fixture, run_fixture,
    validate_fixture,
)


def synthetic_contract_response(**_kwargs):
    return {
        "outcome": "UNIVERSAL_CONTINUES", "needs_exact_hitl": False,
        "advance_beyond_old_failure": True,
        "first_state_beyond_failure": "UR.G1_TYPED_CONTROLLER_NEXT",
    }


def test_reconstructed_subcase_executable_but_never_authentic():
    fixture, checksum = load_fixture(DEFAULT_FIXTURE)
    assert checksum.startswith("sha256:")
    result = run_fixture(fixture, root=ROOT, executor=synthetic_contract_response)
    assert result["result"] == "RECONSTRUCTED_SUBCASE_PASS"
    assert result["authentic_dwo_login_replay"] is False
    assert result["q0_l3_qualified"] is False
    assert result["native_gate_receipt"] is None


def test_exact_actual_source_semantics():
    fixture, _ = load_fixture(DEFAULT_FIXTURE)
    result = run_fixture(fixture)
    assert result["observed"]["needs_exact_hitl"] is False
    assert result["observed"]["advance_beyond_old_failure"] is True


@pytest.mark.parametrize("field,value", [
    ("provenance_class", "ORIGINAL_RECOVERED"),
    ("original_trace_status", "RECOVERED"),
    ("parent_id", "DWO-UNKNOWN"),
])
def test_provenance_upgrade_fails_closed(field, value):
    fixture, _ = load_fixture(DEFAULT_FIXTURE)
    modified = copy.deepcopy(fixture)
    modified["incident"][field] = value
    with pytest.raises(FixtureError, match="PROVENANCE_INVALID"):
        validate_fixture(modified)


def test_oracle_tamper_fails_closed():
    fixture, _ = load_fixture(DEFAULT_FIXTURE)
    fixture["replay"]["expected"]["needs_exact_hitl"] = True
    with pytest.raises(FixtureError, match="ORACLE_INVALID"):
        validate_fixture(fixture)


def test_runtimeplan_digest_drift_fails_closed(tmp_path):
    fixture, _ = load_fixture(DEFAULT_FIXTURE)
    target = tmp_path / "core/node-architect/scrum781-q0-fresh-execution-plan-r2.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}")
    with pytest.raises(FixtureError, match="PLAN_DRIFT"):
        validate_fixture(fixture, root=tmp_path)


def test_old_blocker_recurrence_fails_closed():
    fixture, _ = load_fixture(DEFAULT_FIXTURE)

    def regression(**_kwargs):
        return {"outcome": "NEEDS_EXACT_HITL", "needs_exact_hitl": True}

    with pytest.raises(FixtureError, match="REPLAY_MISMATCH"):
        run_fixture(fixture, executor=regression)


def test_unknown_graph_engine_fails_closed():
    fixture, _ = load_fixture(DEFAULT_FIXTURE)
    with pytest.raises(FixtureError, match="ENGINE_UNKNOWN"):
        run_fixture(fixture, engine="invented", executor=synthetic_contract_response)


def test_langgraph_backend_is_optional_but_fail_closed_when_missing():
    fixture, _ = load_fixture(DEFAULT_FIXTURE)
    try:
        import langgraph  # noqa: F401
    except ImportError:
        with pytest.raises(FixtureError, match="LANGGRAPH_BACKEND_UNAVAILABLE"):
            run_fixture(fixture, engine="langgraph", executor=synthetic_contract_response)
    else:
        result = run_fixture(fixture, engine="langgraph", executor=synthetic_contract_response)
        assert result["checkpoint_class"] == "EPHEMERAL_MECHANICS_ONLY"
        assert result["q0_l3_qualified"] is False

def test_baseline_rebinding_fails_closed():
    fixture, _ = load_fixture(DEFAULT_FIXTURE)
    fixture["source_binding"]["baseline_sha"] = "a" * 40
    with pytest.raises(FixtureError, match="SOURCE_BINDING_INVALID"):
        validate_fixture(fixture)


def test_observed_authority_claim_fails_closed():
    fixture, _ = load_fixture(DEFAULT_FIXTURE)
    def unexpected_effect(**_kwargs):
        return {**synthetic_contract_response(), "authority_granted": True}
    with pytest.raises(FixtureError, match="UNAUTHORIZED_EFFECT_CLAIM"):
        run_fixture(fixture, executor=unexpected_effect)

