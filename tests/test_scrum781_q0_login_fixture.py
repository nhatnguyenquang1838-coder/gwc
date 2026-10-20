"""DWO requirements-bound Login fixtures; never an authentic incident replay."""
from __future__ import annotations

import copy
import hashlib
import pytest

from scripts import scrum781_q0_login_fixture as login


def native_route(**kwargs):
    assert kwargs['runtime_epoch'] == 'UNIVERSAL_V2_DEVELOPMENT'
    assert kwargs['requested_gate'] == 'UR.G2'
    return {'outcome': 'UNIVERSAL_ROUTE_ALLOWED', 'legacy_route': False, 'gate': 'UR.G2'}


def suite():
    return login.load_suite()


def test_exact_q0_source_bound_fixture_and_case_catalog():
    fixture = suite()
    login.validate_suite(fixture)
    assert fixture['manifest']['incident']['original_trace_status'] == 'MISSING'
    assert fixture['manifest']['scenario_count'] == 16
    assert all(c['observed_product_behavior'] is False for c in fixture['scenarios']['cases'])


def test_dwo_login_native_requirements_regression():
    result = login.run_login_suite(suite(), route=native_route)
    assert result['scenario_count'] == result['pass_count'] == 16
    assert result['result'] == 'RECONSTRUCTED_LOGIN_CONTRACT_PASS'
    assert result['route_probe']['legacy_route'] is False
    assert result['dwo_product_live'] is False
    assert result['authentic_dwo_login_replay'] is False
    assert result['q0_l3_qualified'] is False
    assert result['native_gate_receipt'] is None
    assert result['executed_effects'] == []


@pytest.mark.parametrize('target', [
    '//evil.example', 'https://evil.example/', '/admin', '/runs/%2e%2e/admin',
    '/runs/../admin', '/runs\\evil', '/runs#injection', ' /runs',
    '/runs/%252f%252fevil', '/runs/\r\n', 'javascript:alert(1)',
])
def test_redirect_refuses_unsafe_paths(target):
    assert login.safe_next(target) == '/runs'


@pytest.mark.parametrize('target', ['/runs', '/runs/events', '/runs/jobs?filter=open'])
def test_redirect_preserves_literal_safe_runs_paths(target):
    assert login.safe_next(target) == target


def test_login_rejects_client_only_session_for_protected_route():
    case = {'event': 'visit_runs', 'input': {'path': '/runs/events', 'server_session': 'CLIENT_ONLY'}}
    actual = login.evaluate_login_contract(case)
    assert actual['decision'] == 'REDIRECT'
    assert actual['location'].startswith('/login?next=')


def test_model_is_not_the_independent_expected_oracle():
    fixture = suite()
    expected = fixture['scenarios']['cases'][0]['expected']
    assert expected == {'decision': 'REDIRECT', 'location': '/runs', 'session': 'SSR_EXPECTED', 'error': 'NONE'}
    # RED: injecting wrong adapter result must fail verification.
    def broken(_case):
        return {'decision': 'ALLOW', 'location': '/admin', 'session': 'NONE', 'error': 'NONE'}
    with pytest.raises(login.LoginFixtureError, match='LOGIN_ORACLE_MISMATCH'):
        login.run_login_suite(fixture, route=native_route, model=broken)
    # GREEN: requirements model respects immutable fixture expectations.
    assert login.run_login_suite(fixture, route=native_route)['pass_count'] == 16


def test_forged_original_provenance_rejected():
    fixture = copy.deepcopy(suite())
    fixture['manifest']['incident']['provenance_class'] = 'ORIGINAL_RECOVERED'
    with pytest.raises(login.LoginFixtureError, match='LOGIN_FIXTURE_BINDING_INVALID'):
        login.validate_suite(fixture)


def test_forged_scenario_oracle_digest_rejected():
    fixture = copy.deepcopy(suite())
    fixture['scenarios']['cases'][0]['expected']['location'] = '/admin'
    with pytest.raises(login.LoginFixtureError, match='LOGIN_SCENARIO_DIGEST_INVALID'):
        login.validate_suite(fixture)


def test_missing_secret_redaction_rejected():
    fixture = copy.deepcopy(suite())
    fixture['scenarios']['cases'][0]['input']['password'] = 'not-a-real-secret'
    fixture['manifest']['scenarios_sha256'] = hashlib.sha256(
        login._canonical_json(fixture['scenarios'])
    ).hexdigest()
    with pytest.raises(login.LoginFixtureError, match='LOGIN_SECRET_INPUT_PROHIBITED'):
        login.validate_suite(fixture)


def test_unauthorized_gwc_effect_claim_rejected():
    def wrong_route(**kwargs):
        return {**native_route(**kwargs), 'authority_granted': True}
    with pytest.raises(login.LoginFixtureError, match='LOGIN_GWC_UNAUTHORIZED_EFFECT_CLAIM'):
        login.run_login_suite(suite(), route=wrong_route)


def test_non_v2_route_rejected():
    def legacy_route(**kwargs):
        return {'outcome': 'UNIVERSAL_ROUTE_ALLOWED', 'legacy_route': True, 'gate': 'UR.G2'}
    with pytest.raises(login.LoginFixtureError, match='LOGIN_GWC_NATIVE_ROUTE_INVALID'):
        login.run_login_suite(suite(), route=legacy_route)


def test_langgraph_optional_parity_and_evidence_classification():
    pytest.importorskip('langgraph.graph')
    fixture = suite()
    native = login.run_login_suite(fixture, route=native_route)
    graph = login.run_login_suite(fixture, route=native_route, engine='langgraph')
    assert graph['pass_count'] == native['pass_count'] == 16
    assert graph['scenario_ids'] == native['scenario_ids']
    assert graph['scenarios_sha256'] == native['scenarios_sha256']
    assert graph['checkpoint_class'] == 'EPHEMERAL_GRAPH_MECHANICS_ONLY'
    assert graph['native_gate_receipt'] is None
    assert graph['dwo_product_live'] is False


def test_runtime_plan_digest_drift_rejected(tmp_path):
    fixture = suite()
    path = tmp_path / 'core/node-architect/scrum781-q0-fresh-execution-plan-r2.json'
    path.parent.mkdir(parents=True)
    path.write_text('{}', encoding='utf-8')
    with pytest.raises(login.LoginFixtureError, match='LOGIN_RUNTIMEPLAN_DRIFT'):
        login.validate_suite(fixture, root=tmp_path)
