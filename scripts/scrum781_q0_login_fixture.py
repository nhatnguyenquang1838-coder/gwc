#!/usr/bin/env python3
"""Reconstructed DWO Login/Auth requirements regression under GWC Universal v2.

Uses actual GWC v2 epoch router when run inside gwc checkout, but auth behavior
is a deterministic *requirements model*, not a Supabase server or original DWO
incident. LangGraph is optional and never becomes the GWC authority plane.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SUITE_DIR = ROOT / '.gwc/tasks/SCRUM-781/fixtures/dwo-login-auth-r1'
MANIFEST = SUITE_DIR / 'manifest-v1.json'
CASES = SUITE_DIR / 'scenarios-v1.json'
PLAN = ROOT / 'core/node-architect/scrum781-q0-fresh-execution-plan-r2.json'
RUN = 'scrum781-q0-fresh-20261010-r1'
BRANCH = 'fix/SCRUM-781-q0-fresh-20261010-r1'
PROFILE = 'UNIVERSAL_V2_DEVELOPMENT'
PLAN_DIGEST = 'ac8e8b855d5564ec9e503f965cd73deb60b546caf70a7304c43140a315422500'
REQUIRED_EVENTS = {'sign_in', 'visit_runs', 'visit_login', 'logout'}
SCENARIO_ID_RE = re.compile(r'^LOGIN-[0-9]{2}$')


class LoginFixtureError(ValueError):
    """Stable fail-closed fixture validation error."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise LoginFixtureError('LOGIN_FIXTURE_SOURCE_UNREADABLE:' + str(path)) from exc


def load_suite(root: Path = ROOT) -> Dict[str, Any]:
    base = root / '.gwc/tasks/SCRUM-781/fixtures/dwo-login-auth-r1'
    return {'manifest': _read_json(base / 'manifest-v1.json'),
            'scenarios': _read_json(base / 'scenarios-v1.json')}


def validate_suite(suite: Dict[str, Any], root: Path = ROOT) -> None:
    manifest, scenarios = suite.get('manifest', {}), suite.get('scenarios', {})
    if not isinstance(manifest, dict) or not isinstance(scenarios, dict):
        raise LoginFixtureError('LOGIN_FIXTURE_SCHEMA_INVALID')
    binding = manifest.get('source_binding', {})
    incident = manifest.get('incident', {})
    if not all((
        manifest.get('schema_id') == 'gwc.q0.dwo-login-fixture-suite/v1',
        manifest.get('suite_id') == 'DWO-LOGIN-AUTH-R1-RECONSTRUCTED-V1',
        manifest.get('run_id') == RUN,
        manifest.get('runtime_epoch') == PROFILE,
        manifest.get('gate') == 'UR.G2',
        manifest.get('auth_contract') == 'DWO_LOGIN_AUTH_V1_REQUIREMENTS',
        manifest.get('dwo_projection_mode') == 'READ_ONLY',
        binding.get('repository') == 'nhatnguyenquang1838-coder/gwc',
        binding.get('branch') == BRANCH,
        binding.get('runtimeplan_path') == PLAN.relative_to(ROOT).as_posix(),
        binding.get('runtimeplan_sha256') == PLAN_DIGEST,
        incident.get('original_trace_status') == 'MISSING',
        incident.get('provenance_class') == 'RECONSTRUCTED_REQUIREMENTS_BOUND',
        incident.get('authentic_incident_replay') is False,
        isinstance(manifest.get('oracle_sources'), list),
        len(manifest.get('oracle_sources', [])) >= 2,
    )):
        raise LoginFixtureError('LOGIN_FIXTURE_BINDING_INVALID')
    if not all(isinstance(s, dict) and s.get('id') and s.get('url')
               for s in manifest['oracle_sources']):
        raise LoginFixtureError('LOGIN_FIXTURE_ORACLE_SOURCE_INVALID')
    try:
        actual_plan = (root / binding['runtimeplan_path']).read_bytes()
    except OSError as exc:
        raise LoginFixtureError('LOGIN_RUNTIMEPLAN_MISSING') from exc
    if _sha(actual_plan) != PLAN_DIGEST:
        raise LoginFixtureError('LOGIN_RUNTIMEPLAN_DRIFT')
    if scenarios.get('schema_id') != 'gwc.q0.dwo-login-scenarios/v1':
        raise LoginFixtureError('LOGIN_SCENARIO_SCHEMA_INVALID')
    entries = scenarios.get('cases')
    if not isinstance(entries, list) or len(entries) < 10:
        raise LoginFixtureError('LOGIN_SCENARIOS_INCOMPLETE')
    if manifest.get('scenario_count') != len(entries):
        raise LoginFixtureError('LOGIN_SCENARIO_COUNT_MISMATCH')
    if manifest.get('scenarios_sha256') != _sha(_canonical_json(scenarios)):
        raise LoginFixtureError('LOGIN_SCENARIO_DIGEST_INVALID')
    seen = set()
    sources = {s['id'] for s in manifest['oracle_sources']}
    for case in entries:
        if not isinstance(case, dict) or not SCENARIO_ID_RE.fullmatch(str(case.get('id', ''))):
            raise LoginFixtureError('LOGIN_SCENARIO_ID_INVALID')
        if case['id'] in seen:
            raise LoginFixtureError('LOGIN_SCENARIO_DUPLICATE')
        seen.add(case['id'])
        if (case.get('event') not in REQUIRED_EVENTS
            or not isinstance(case.get('input'), dict)
            or not isinstance(case.get('expected'), dict)
            or case.get('oracle_class') != 'REQUIREMENTS_DERIVED'
            or case.get('oracle_source') not in sources
            or case.get('observed_product_behavior') is not False):
            raise LoginFixtureError('LOGIN_SCENARIO_CONTRACT_INVALID:' + case['id'])
        if 'password' in case['input'] or 'token' in case['input'] or 'cookie' in case['input']:
            raise LoginFixtureError('LOGIN_SECRET_INPUT_PROHIBITED')
        if set(case['expected']) != {'decision', 'location', 'session', 'error'}:
            raise LoginFixtureError('LOGIN_ORACLE_FIELDS_INVALID:' + case['id'])
        if case['expected']['session'] not in {'NONE', 'SSR_EXPECTED', 'REVOKED_EXPECTED'}:
            raise LoginFixtureError('LOGIN_ORACLE_SESSION_INVALID')


def safe_next(candidate: Any) -> str:
    """Allow only literal /runs paths; refuse encoded, traversal or external redirects."""
    if not isinstance(candidate, str) or not candidate or len(candidate) > 1024:
        return '/runs'
    if any(ord(c) < 33 or ord(c) == 127 for c in candidate):
        return '/runs'
    if ('\\' in candidate or '%' in candidate or '#' in candidate or
        candidate.startswith('//') or not candidate.startswith('/')):
        return '/runs'
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or not (parsed.path == '/runs' or parsed.path.startswith('/runs/')):
        return '/runs'
    if any(part in {'.', '..'} for part in parsed.path.split('/')):
        return '/runs'
    return candidate


def _email_well_formed(value: Any) -> bool:
    return (isinstance(value, str) and 3 <= len(value) <= 254 and
            value.count('@') == 1 and '.' in value.split('@')[-1] and
            not any(ch.isspace() for ch in value))


def evaluate_login_contract(case: Dict[str, Any]) -> Dict[str, str]:
    """Deterministic requirements oracle *model*: never talks to Supabase/DWO."""
    event = case['event']
    data = case['input']
    if event == 'sign_in':
        if not _email_well_formed(data.get('email')) or data.get('password_present') is not True:
            return {'decision': 'VALIDATION_ERROR', 'location': '/login', 'session': 'NONE', 'error': 'INPUT_REQUIRED'}
        if data.get('credential_verdict') != 'ACCEPT':
            return {'decision': 'AUTH_ERROR', 'location': '/login', 'session': 'NONE', 'error': 'INVALID_LOGIN_GENERIC'}
        return {'decision': 'REDIRECT', 'location': safe_next(data.get('next')), 'session': 'SSR_EXPECTED', 'error': 'NONE'}
    if event == 'visit_runs':
        target = safe_next(data.get('path', '/runs'))
        if data.get('server_session') == 'VERIFIED':
            return {'decision': 'ALLOW', 'location': target, 'session': 'SSR_EXPECTED', 'error': 'NONE'}
        return {'decision': 'REDIRECT', 'location': '/login?next=' + quote(target, safe=''), 'session': 'NONE', 'error': 'NONE'}
    if event == 'visit_login':
        if data.get('server_session') == 'VERIFIED':
            return {'decision': 'REDIRECT', 'location': '/runs', 'session': 'SSR_EXPECTED', 'error': 'NONE'}
        return {'decision': 'ALLOW', 'location': '/login', 'session': 'NONE', 'error': 'NONE'}
    if event == 'logout':
        return {'decision': 'REDIRECT', 'location': '/login', 'session': 'REVOKED_EXPECTED', 'error': 'NONE'}
    raise LoginFixtureError('LOGIN_EVENT_UNSUPPORTED')


def gwc_native_route_probe(route: Callable[..., Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Calls real GWC Universal v2 epoch router unless test adapter is injected."""
    if route is None:
        from tools.node_architect.universal_run_epoch import route_universal_request
        route = route_universal_request
    result = route(runtime_epoch=PROFILE, requested_gate='UR.G2', requested_action='q0_execute_probe')
    if (result.get('outcome') != 'UNIVERSAL_ROUTE_ALLOWED' or result.get('legacy_route') is not False
        or result.get('gate') != 'UR.G2'):
        raise LoginFixtureError('LOGIN_GWC_NATIVE_ROUTE_INVALID')
    if result.get('authority_granted') is True or result.get('executed_effects'):
        raise LoginFixtureError('LOGIN_GWC_UNAUTHORIZED_EFFECT_CLAIM')
    return {'outcome': result['outcome'], 'legacy_route': False, 'gate': 'UR.G2'}


def run_login_suite(suite: Dict[str, Any], *, root: Path = ROOT,
                    engine: str = 'native', route: Callable[..., Dict[str, Any]] | None = None,
                    model: Callable[[Dict[str, Any]], Dict[str, str]] | None = None) -> Dict[str, Any]:
    validate_suite(suite, root=root)
    route_result = gwc_native_route_probe(route)
    cases = suite['scenarios']['cases']
    evaluator = model or evaluate_login_contract
    if engine == 'native':
        actuals = [evaluator(c) for c in cases]
        checkpoint = 'NONE'
    elif engine == 'langgraph':
        try:
            from langgraph.graph import StateGraph, START, END
            from langgraph.checkpoint.memory import MemorySaver
        except ImportError as exc:
            raise LoginFixtureError('LOGIN_LANGGRAPH_BACKEND_UNAVAILABLE') from exc
        from typing import TypedDict
        class State(TypedDict, total=False):
            case: Dict[str, Any]
            observed: Dict[str, str]
        def execute(state: State) -> State:
            return {'observed': evaluator(state['case'])}
        graph = StateGraph(State)
        graph.add_node('evaluate', execute)
        graph.add_edge(START, 'evaluate')
        graph.add_edge('evaluate', END)
        compiled = graph.compile(checkpointer=MemorySaver())
        actuals = [compiled.invoke({'case': c}, {'configurable': {'thread_id': RUN + ':' + c['id']}})['observed'] for c in cases]
        checkpoint = 'EPHEMERAL_GRAPH_MECHANICS_ONLY'
    else:
        raise LoginFixtureError('LOGIN_ENGINE_UNSUPPORTED')
    failures = [c['id'] for c, a in zip(cases, actuals) if c['expected'] != a]
    if failures:
        raise LoginFixtureError('LOGIN_ORACLE_MISMATCH:' + ','.join(failures))
    return {
        'schema_id': 'gwc.q0.login-replay-result/v1',
        'suite_id': suite['manifest']['suite_id'],
        'run_id': RUN, 'runtime_epoch': PROFILE, 'gate': 'UR.G2',
        'route_probe': route_result, 'engine': engine,
        'result': 'RECONSTRUCTED_LOGIN_CONTRACT_PASS',
        'scenario_count': len(cases), 'pass_count': len(cases),
        'scenario_ids': [c['id'] for c in cases],
        'scenarios_sha256': suite['manifest']['scenarios_sha256'],
        'checkpoint_class': checkpoint,
        'provenance_class': 'RECONSTRUCTED_REQUIREMENTS_BOUND',
        'dwo_product_live': False, 'authentic_dwo_login_replay': False,
        'q0_l3_qualified': False, 'native_gate_receipt': None,
        'executed_effects': [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('native', 'langgraph'), default='native')
    args = parser.parse_args()
    try:
        result = run_login_suite(load_suite(), engine=args.engine)
    except (LoginFixtureError, OSError, ValueError, ImportError) as exc:
        print(json.dumps({'result': 'BLOCKED', 'reason_code': str(exc),
                          'native_gate_receipt': None, 'q0_l3_qualified': False}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
