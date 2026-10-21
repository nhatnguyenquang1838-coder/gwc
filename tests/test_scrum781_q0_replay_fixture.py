"""Synthetic sandbox validator tests, NEVER authentic Q0 runtime CF-RED."""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = 'scripts.scrum781_q0_replay_fixture'
PLAN = 'core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json'
PROFILE = 'core/node-architect/q0-live-qualification-profile.json'
ROUTE = 'core/node-architect/universal-runtime-default-profile.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def put(root, path, data):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {'path': path, 'sha256': sha(data)}


@pytest.fixture
def sandbox(tmp_path):
    refs = {p: put(tmp_path, p, (ROOT / p).read_bytes()) for p in (PLAN, PROFILE, ROUTE)}
    seam = put(tmp_path, 'tools/node_architect/synthetic_q0_probe.py',
               b'def probe(state):\n    return dict(state)\n')
    dep = put(tmp_path, 'sandbox/dependency.json', b'{"mode":"synthetic-only"}')
    binding = {
        'repository': 'nhatnguyenquang1838-coder/gwc',
        'branch': 'fix/SCRUM-781-q0-fresh-20261010-r1',
        'run_id': 'scrum781-q0-fresh-20261010-r1',
        'head': '47e5d2486efdea6d91be62d60864bbf80305fa0d',
        'candidate_id': 'SYNTHETIC-VALIDATOR-ONLY',
        'mandatory_entry': 'self_fix_replay',
        'runtime_epoch': 'UNIVERSAL_V2_DEVELOPMENT', 'gate': 'UR.G2',
        'plan': refs[PLAN], 'profile': refs[PROFILE], 'route': refs[ROUTE],
        'route_id': 'q0_execute_probe', 'seam': {**seam, 'symbol': 'probe'},
    }
    policy = {
        'binding': binding,
        'command': ['python', seam['path'], '--sandbox', '--offline'],
        'environment': {'Q0_SANDBOX': '1', 'Q0_OFFLINE': '1', 'PYTHONHASHSEED': '0'},
        'dependencies': [dep],
        'expected_result': {'next_state': 'UR.G3', 'poststate': {'seen': [1]}},
        'legal_next_states': ['UR.G3'], 'max_age_seconds': 3600,
    }
    spec = {'binding': copy.deepcopy(binding), 'command': policy['command'][:],
            'environment': dict(policy['environment']), 'dependencies': [dep],
            'input': {'event': 'synthetic'}, 'prestate': {'seen': []},
            'snapshots': [put(tmp_path, 'sandbox/snapshot.json', b'{"seen":[]}')]}
    return tmp_path, policy, spec


def test_capture_roundtrip_canonical_hashes_closed_claims(sandbox):
    # Import inside the test so absent implementation is an explicit feature RED.
    api = importlib.import_module(MODULE)
    root, policy, spec = sandbox
    fixture = api.capture_fixture(spec, root=root, policy=policy)
    second = api.capture_fixture(json.loads(canonical(spec)), root=root, policy=policy)
    assert fixture == second
    assert fixture['input_sha256'] == sha(canonical(spec['input']))
    assert fixture['prestate_sha256'] == sha(canonical(spec['prestate']))
    assert fixture['scenario_status'] == 'PROPOSAL_ONLY'
    assert fixture['observation_status'] == 'UNOBSERVED'
    assert fixture['red'] is None
    assert fixture['original_dwo_reproduced'] is False
    assert fixture['q0_l3_qualified'] is False
    assert api.validate_fixture(fixture, root=root, policy=policy) == fixture['scenario_digest']
    restored = api.reconstruct_prestate(fixture, root=root, policy=policy)
    assert restored['prestate'] == spec['prestate']
    assert restored['snapshots'] == {'sandbox/snapshot.json': b'{"seen":[]}'}
    restored['prestate']['seen'].append('not-shared')
    assert fixture['prestate'] == {'seen': []}


@pytest.mark.parametrize('field', [
    'repository', 'branch', 'run_id', 'head', 'candidate_id', 'mandatory_entry',
    'runtime_epoch', 'gate', 'route_id', 'plan', 'profile', 'route', 'seam',
])
def test_rejects_mismatched_exact_bindings(sandbox, field):
    api = importlib.import_module(MODULE)
    root, policy, spec = sandbox
    spec['binding'][field] = 'untrusted-assertion'
    with pytest.raises(api.ReplayFixtureError):
        api.capture_fixture(spec, root=root, policy=policy)


@pytest.mark.parametrize('field,value', [
    ('repository', 'other/repository'), ('head', 'not-a-sha'),
    ('mandatory_entry', 'invented-entry'), ('route_id', 'legacy_execute'),
    ('runtime_epoch', 'LEGACY'), ('gate', 'G2_EXECUTION'),
])
def test_policy_itself_cannot_authorize_invalid_q0_binding(sandbox, field, value):
    api = importlib.import_module(MODULE)
    root, policy, spec = sandbox
    spec['binding'][field] = value
    policy['binding'][field] = value
    with pytest.raises(api.ReplayFixtureError):
        api.capture_fixture(spec, root=root, policy=policy)


@pytest.mark.parametrize('path', ['../outside.json', '/etc/hosts', 'sandbox/../outside.json',
                                  'sandbox//snapshot.json', 'sandbox/%2e%2e/x',
                                  'sandbox\\snapshot.json', 'sandbox/.env',
                                  '.gwc/checkpoint.sqlite', 'sandbox/link.json'])
def test_rejects_path_escape_even_with_matching_content_digest(sandbox, path):
    api = importlib.import_module(MODULE)
    root, policy, spec = sandbox
    outside = root.parent / 'outside.json'
    outside.write_bytes(b'{}')
    (root / 'sandbox/link.json').symlink_to(outside)
    spec['snapshots'] = [{'path': path, 'sha256': sha(b'{}')}]
    with pytest.raises(api.ReplayFixtureError):
        api.capture_fixture(spec, root=root, policy=policy)


@pytest.mark.parametrize('payload', [
    {'password': 'fake'}, {'nested': [{'ACCESS_TOKEN': 'fake'}]},
    {'authorization': 'fake'}, {'cookie': 'fake'},
    {'note': 'Bearer syntheticcredential'}, {'note': '-----BEGIN PRIVATE KEY-----'},
    {'note': 'ghp_' + 'a' * 36}, {'note': 'postgres://user:pass@db.invalid/name'},
])
def test_rejects_secrets_in_input(sandbox, payload):
    api = importlib.import_module(MODULE)
    root, policy, spec = sandbox
    spec['input'] = payload
    with pytest.raises(api.ReplayFixtureError):
        api.capture_fixture(spec, root=root, policy=policy)


@pytest.mark.parametrize('command', [
    ['sh', '-c', 'rm -rf /'], ['python', '-c', 'print(1)'],
    ['python', 'tools/node_architect/synthetic_q0_probe.py', '--production'],
    ['python', 'tools/node_architect/synthetic_q0_probe.py', '--sandbox', '--offline', ';rm'],
    ['git', 'push', 'origin', 'main'], ['terraform', 'destroy'],
    ['curl', 'https://example.invalid'], ['python', 'sandbox/other.py', '--sandbox', '--offline'],
])
def test_allowlist_cannot_enable_production_destructive_or_shell_commands(sandbox, command):
    api = importlib.import_module(MODULE)
    root, policy, spec = sandbox
    policy['command'] = spec['command'] = command
    with pytest.raises(api.ReplayFixtureError):
        api.capture_fixture(spec, root=root, policy=policy)


@pytest.mark.parametrize('environment', [
    {'Q0_SANDBOX': '0'}, {'Q0_SANDBOX': '1', 'AWS_SECRET_ACCESS_KEY': 'fake'},
    {'Q0_SANDBOX': '1', 'Q0_OFFLINE': '1', 'PYTHONPATH': '/production'},
])
def test_rejects_unsafe_environment_even_if_allowlisted(sandbox, environment):
    api = importlib.import_module(MODULE)
    root, policy, spec = sandbox
    policy['environment'] = spec['environment'] = environment
    with pytest.raises(api.ReplayFixtureError):
        api.capture_fixture(spec, root=root, policy=policy)


@pytest.mark.parametrize('source', [b'probe = "claimed-ref"\n', b'def probe(state):\n    pass\n',
                                    b'def probe(state):\n    raise NotImplementedError\n'])
def test_missing_executable_seam_fails_even_when_digest_matches(sandbox, source):
    api = importlib.import_module(MODULE)
    root, policy, spec = sandbox
    ref = put(root, spec['binding']['seam']['path'], source)
    for binding in (spec['binding'], policy['binding']):
        binding['seam'] = {**ref, 'symbol': 'probe'}
    with pytest.raises(api.ReplayFixtureError):
        api.capture_fixture(spec, root=root, policy=policy)


@pytest.mark.parametrize('kind', ['snapshot', 'dependency', 'plan', 'profile', 'route', 'seam'])
def test_materialized_artifact_missing_or_tampered(sandbox, kind):
    api = importlib.import_module(MODULE)
    root, policy, spec = sandbox
    fixture = api.capture_fixture(spec, root=root, policy=policy)
    ref = (spec['snapshots'][0] if kind == 'snapshot' else spec['dependencies'][0]
           if kind == 'dependency' else spec['binding'][kind])
    target = root / ref['path']
    target.write_bytes(b'tampered')
    with pytest.raises(api.ReplayFixtureError):
        api.validate_fixture(fixture, root=root, policy=policy)
    target.unlink()
    with pytest.raises(api.ReplayFixtureError):
        api.validate_fixture(fixture, root=root, policy=policy)


def test_dependency_and_snapshot_contents_must_be_nonsecret(sandbox):
    api = importlib.import_module(MODULE)
    root, policy, spec = sandbox
    ref = put(root, 'sandbox/dependency.json', b'{"password":"synthetic-secret"}')
    policy['dependencies'] = spec['dependencies'] = [ref]
    with pytest.raises(api.ReplayFixtureError):
        api.capture_fixture(spec, root=root, policy=policy)


@pytest.mark.parametrize('payload', [float('nan'), {1: 'not-json-key'}, ('not-json-array',), {'x': float('inf')}])
def test_rejects_noncanonical_json_types(sandbox, payload):
    api = importlib.import_module(MODULE)
    root, policy, spec = sandbox
    spec['input'] = payload
    with pytest.raises(api.ReplayFixtureError):
        api.capture_fixture(spec, root=root, policy=policy)


@pytest.mark.parametrize('change', ['input', 'prestate', 'snapshot_manifest', 'scenario_digest',
                                    'original_dwo_reproduced', 'q0_l3_qualified', 'red', 'extra'])
def test_rejects_forged_fixture_fields(sandbox, change):
    api = importlib.import_module(MODULE)
    root, policy, spec = sandbox
    fixture = api.capture_fixture(spec, root=root, policy=policy)
    fixture[change] = True
    with pytest.raises(api.ReplayFixtureError):
        api.validate_fixture(fixture, root=root, policy=policy)


def runtime_identity(root, binding, *, fixed=False):
    source = binding['seam']
    if fixed:
        source = {**put(root, 'sandbox/fixed_source.py',
                       b'def probe(state):\n    return {**state, "fixed": True}\n'), 'symbol': 'probe'}
    return {'activation_id': 'synthetic-fixed' if fixed else 'synthetic-baseline',
            'process_or_session_id': 'synthetic-session-2' if fixed else 'synthetic-session-1',
            'loaded_source_sha': 'a' * 40 if fixed else binding['head'],
            'source': copy.deepcopy(source), 'profile': copy.deepcopy(binding['profile']),
            'instructions': [copy.deepcopy(binding['plan'])],
            'modules': [{k: source[k] for k in ('path', 'sha256')}]}


def receipt_document(fixture, runtime, stage, when, result=None):
    result_digest = sha(canonical(result)) if result is not None else None
    return {'schema_id': 'gwc.q0.sandbox-runtime-observation/v1', 'stage': stage,
            'scenario_digest': fixture['scenario_digest'], 'binding': copy.deepcopy(fixture['binding']),
            'input_sha256': fixture['input_sha256'], 'prestate_sha256': fixture['prestate_sha256'],
            'snapshot_manifest_sha256': fixture['snapshot_manifest_sha256'],
            'runtime': runtime, 'observed_at': when, 'exit_code': 7 if stage == 'RED' else 0,
            'reason_code': 'SYNTHETIC_RED_BOUNDARY' if stage == 'RED' else 'SYNTHETIC_PASS',
            'execution_prestate_sha256': (sha(canonical(result['poststate'])) if stage == 'IDEMPOTENCY'
                                         else fixture['prestate_sha256']),
            'idempotency_key': fixture['scenario_digest'],
            'result': result, 'result_sha256': result_digest, 'executed_effects': [],
            'sandbox_only': True, 'original_dwo_reproduced': False, 'q0_l3_qualified': False}


def write_receipt(root, doc):
    doc = copy.deepcopy(doc)
    doc['evidence'] = put(root, 'sandbox/' + doc['stage'].lower() + '.log',
                          ('SYNTHETIC VALIDATOR ONLY: ' + doc['reason_code'] + '\n').encode())
    return put(root, 'sandbox/' + doc['stage'].lower() + '.json', canonical(doc))


def synthetic_observations(sandbox):
    api = importlib.import_module(MODULE)
    root, policy, spec = sandbox
    fixture = api.capture_fixture(spec, root=root, policy=policy)
    before = runtime_identity(root, spec['binding'])
    after = runtime_identity(root, spec['binding'], fixed=True)
    # The unchanged plan module is a valid retained dependency after the new activation.
    after['modules'].append(copy.deepcopy(spec['binding']['plan']))
    docs = {'RED': receipt_document(fixture, before, 'RED', 1000)}
    for i, stage in enumerate(('LOAD', 'REPLAY', 'REPEAT', 'IDEMPOTENCY'), start=1):
        result = None if stage == 'LOAD' else copy.deepcopy(policy['expected_result'])
        docs[stage] = receipt_document(fixture, after, stage, 1000 + i, result)
    refs = {stage: write_receipt(root, doc) for stage, doc in docs.items()}
    trust = {'authority_id': 'SYNTHETIC-TEST-ANCHOR-NOT-Q0-AUTHORITY',
             'receipt_digests': {stage: ref['sha256'] for stage, ref in refs.items()}}
    return api, root, policy, fixture, after, docs, refs, trust


def test_offline_observed_red_and_replay_consistency_never_qualifies(sandbox):
    api, root, policy, fixture, after, docs, refs, trust = synthetic_observations(sandbox)
    original = copy.deepcopy(fixture)
    observed = api.record_red(fixture, refs['RED'], root=root, policy=policy, trust_anchor=trust, now=1010)
    assert original == fixture
    assert observed['scenario_status'] == 'PROPOSAL_ONLY'
    assert observed['observation_status'] == 'UNOBSERVED'
    assert observed['red'] == refs['RED']
    assert observed['scenario_digest'] == original['scenario_digest']
    result = api.verify_replay(observed, {k: refs[k] for k in refs if k != 'RED'},
                               root=root, policy=policy, trust_anchor=trust,
                               expected_runtime=after, now=1010)
    assert result['result'] == 'OFFLINE_REPLAY_EVIDENCE_CONSISTENT'
    assert result['original_dwo_reproduced'] is False
    assert result['q0_l3_qualified'] is False
    assert result['executed_effects'] == []
    assert result['result_sha256'] == sha(canonical(policy['expected_result']))
    assert result == api.verify_replay(observed, {k: refs[k] for k in refs if k != 'RED'},
                                      root=root, policy=policy, trust_anchor=trust,
                                      expected_runtime=after, now=1010)


def test_asserted_receipt_refs_without_external_trust_are_not_proof(sandbox):
    api, root, policy, fixture, after, docs, refs, trust = synthetic_observations(sandbox)
    with pytest.raises(api.ReplayFixtureError):
        api.record_red(fixture, refs['RED'], root=root, policy=policy, trust_anchor=None, now=1010)


@pytest.mark.parametrize('source', [
    b'def probe(state):\n    pass\n',
    b'def probe(state):\n    raise NotImplementedError\n',
    b'probe = 7\n',
])
def test_fixed_runtime_source_must_be_an_executable_seam_without_execution(sandbox, source):
    api, root, policy, fixture, after, docs, refs, trust = synthetic_observations(sandbox)
    fixed = put(root, 'sandbox/fixed_source.py', source)
    after['source'] = {**fixed, 'symbol': 'probe'}
    after['modules'][0] = fixed
    for stage in ('LOAD', 'REPLAY', 'REPEAT', 'IDEMPOTENCY'):
        docs[stage]['runtime'] = copy.deepcopy(after)
        refs[stage] = write_receipt(root, docs[stage])
        trust['receipt_digests'][stage] = refs[stage]['sha256']
    observed = api.record_red(fixture, refs['RED'], root=root, policy=policy,
                              trust_anchor=trust, now=1010)
    with pytest.raises(api.ReplayFixtureError, match='EXECUTABLE_SEAM_MISSING'):
        api.verify_replay(observed, {k: refs[k] for k in refs if k != 'RED'}, root=root,
                          policy=policy, trust_anchor=trust, expected_runtime=after, now=1010)


def test_recorded_red_reference_roundtrips_shape_only_and_tampering_blocks(sandbox):
    api, root, policy, fixture, _after, _docs, refs, trust = synthetic_observations(sandbox)
    observed = api.record_red(fixture, refs['RED'], root=root, policy=policy,
                              trust_anchor=trust, now=1010)
    assert api.validate_fixture(observed, root=root, policy=policy) == fixture['scenario_digest']
    reconstructed = api.reconstruct_prestate(observed, root=root, policy=policy)
    assert reconstructed['prestate'] == fixture['prestate']
    assert reconstructed['snapshots']['sandbox/snapshot.json'] == b'{"seen":[]}'
    policy_path = write_json(root / 'sandbox/recorded-policy.json', policy)
    fixture_path = write_json(root / 'sandbox/recorded-fixture.json', observed)
    for operation in ('validate', 'reconstruct'):
        result = cli('--root', root, '--policy', policy_path, operation, '--fixture', fixture_path)
        assert result.returncode == 0
        assert json.loads(result.stdout)['status'] == 'OK'
    tampered = copy.deepcopy(observed)
    tampered['red']['sha256'] = '0' * 64
    with pytest.raises(api.ReplayFixtureError, match='ARTIFACT_DIGEST_MISMATCH'):
        api.validate_fixture(tampered, root=root, policy=policy)
    forged_stage = copy.deepcopy(observed)
    forged_stage['red'] = refs['LOAD']
    with pytest.raises(api.ReplayFixtureError, match='RECORDED_RED_SHAPE_INVALID'):
        api.validate_fixture(forged_stage, root=root, policy=policy)
    (root / refs['RED']['path']).unlink()
    with pytest.raises(api.ReplayFixtureError, match='ARTIFACT_UNREADABLE'):
        api.reconstruct_prestate(observed, root=root, policy=policy)


@pytest.mark.parametrize('shape', ['qualification_nodes_list', 'gate_entry_list'])
def test_malformed_profile_nested_schema_is_api_error_and_sanitized_cli_block(sandbox, shape):
    api, root, policy, spec = (importlib.import_module(MODULE), *sandbox)
    profile_ref = spec['binding']['profile']
    profile_path = root / profile_ref['path']
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    if shape == 'qualification_nodes_list':
        profile['qualification_nodes'] = []
    else:
        profile['qualification_nodes']['UR.G2'] = []
    new_ref = put(root, profile_ref['path'], canonical(profile))
    for binding in (spec['binding'], policy['binding']):
        binding['profile'] = new_ref
    with pytest.raises(api.ReplayFixtureError):
        api.capture_fixture(spec, root=root, policy=policy)

    policy_path = write_json(root / 'sandbox/profile-policy.json', policy)
    spec_path = write_json(root / 'sandbox/profile-spec.json', spec)
    cli_result = cli('--root', root, '--policy', policy_path, 'capture', '--spec', spec_path)
    assert cli_result.returncode == 2
    blocked = json.loads(cli_result.stdout)
    assert blocked['status'] == 'BLOCKED'
    assert blocked['reason'].isupper()
    assert 'Traceback' not in cli_result.stdout + cli_result.stderr


@pytest.mark.parametrize('stage', ['RED', 'LOAD', 'REPLAY', 'REPEAT', 'IDEMPOTENCY'])
@pytest.mark.parametrize('mutation', [
    'missing', 'untrusted', 'tampered', 'stale', 'future', 'input', 'prestate',
    'binding', 'scenario', 'snapshots', 'evidence', 'secret', 'effects', 'qualified',
    'runtime', 'source', 'exit', 'empty_reason', 'execution_prestate', 'result',
])
def test_fail_closed_receipt_chain_even_with_reanchored_invalid_documents(sandbox, stage, mutation):
    api, root, policy, fixture, after, docs, refs, trust = synthetic_observations(sandbox)
    if mutation == 'missing':
        (root / refs[stage]['path']).unlink()
    elif mutation == 'untrusted':
        trust['receipt_digests'][stage] = '0' * 64
    elif mutation == 'tampered':
        (root / refs[stage]['path']).write_bytes(b'{}')
    else:
        doc = docs[stage]
        if mutation == 'stale': doc['observed_at'] = -5000
        elif mutation == 'future': doc['observed_at'] = 2000
        elif mutation == 'input': doc['input_sha256'] = '0' * 64
        elif mutation == 'prestate': doc['prestate_sha256'] = '0' * 64
        elif mutation == 'binding': doc['binding']['candidate_id'] = 'OTHER'
        elif mutation == 'scenario': doc['scenario_digest'] = '0' * 64
        elif mutation == 'snapshots': doc['snapshot_manifest_sha256'] = '0' * 64
        elif mutation == 'secret': doc['result'] = {'password': 'synthetic'}
        elif mutation == 'effects': doc['executed_effects'] = ['production-write']
        elif mutation == 'qualified': doc['q0_l3_qualified'] = True
        elif mutation == 'runtime': doc['runtime']['loaded_source_sha'] = '0' * 40
        elif mutation == 'source': doc['runtime']['source']['sha256'] = '0' * 64
        elif mutation == 'exit': doc['exit_code'] = 0 if stage == 'RED' else 7
        elif mutation == 'empty_reason': doc['reason_code'] = ''
        elif mutation == 'execution_prestate': doc['execution_prestate_sha256'] = '0' * 64
        elif mutation == 'result':
            doc['result'] = {'next_state': 'UR.G6', 'poststate': {'seen': [1, 1]}}
            doc['result_sha256'] = sha(canonical(doc['result']))
        refs[stage] = write_receipt(root, doc)
        trust['receipt_digests'][stage] = refs[stage]['sha256']
        if mutation == 'evidence':
            (root / ('sandbox/' + stage.lower() + '.log')).write_bytes(b'forged-log')
    with pytest.raises(api.ReplayFixtureError):
        observed = api.record_red(fixture, refs['RED'], root=root, policy=policy, trust_anchor=trust, now=1010)
        api.verify_replay(observed, {k: refs[k] for k in refs if k != 'RED'},
                          root=root, policy=policy, trust_anchor=trust, expected_runtime=after, now=1010)


def test_proposal_cannot_be_replayed_as_observed_runtime_evidence(sandbox):
    api, root, policy, fixture, after, docs, refs, trust = synthetic_observations(sandbox)
    with pytest.raises(api.ReplayFixtureError):
        api.verify_replay(fixture, {k: refs[k] for k in refs if k != 'RED'}, root=root,
                          policy=policy, trust_anchor=trust, expected_runtime=after, now=1010)


@pytest.mark.parametrize('mutation', ['same_activation', 'same_session', 'same_head', 'same_source',
                                     'no_modules', 'source_not_module', 'no_instructions', 'profile',
                                     'time_order', 'no_repeat'])
def test_requires_fresh_load_proof_and_independent_determinism_checks(sandbox, mutation):
    api, root, policy, fixture, after, docs, refs, trust = synthetic_observations(sandbox)
    if mutation == 'same_activation': after['activation_id'] = docs['RED']['runtime']['activation_id']
    elif mutation == 'same_session': after['process_or_session_id'] = docs['RED']['runtime']['process_or_session_id']
    elif mutation == 'same_head': after['loaded_source_sha'] = fixture['binding']['head']
    elif mutation == 'same_source': after['source'] = fixture['binding']['seam']
    elif mutation == 'no_modules': after['modules'] = []
    elif mutation == 'source_not_module': after['modules'] = [copy.deepcopy(fixture['binding']['plan'])]
    elif mutation == 'no_instructions': after['instructions'] = []
    elif mutation == 'profile': after['profile'] = fixture['binding']['route']
    elif mutation == 'time_order': docs['LOAD']['observed_at'] = 999
    for stage in refs:
        if mutation == 'source_not_module' and stage != 'RED':
            docs[stage]['runtime'] = copy.deepcopy(after)
        refs[stage] = write_receipt(root, docs[stage])
        trust['receipt_digests'][stage] = refs[stage]['sha256']
    if mutation == 'no_repeat': del refs['REPEAT']
    with pytest.raises(api.ReplayFixtureError):
        observed = api.record_red(fixture, refs['RED'], root=root, policy=policy, trust_anchor=trust, now=1010)
        api.verify_replay(observed, {k: refs[k] for k in refs if k != 'RED'}, root=root,
                          policy=policy, trust_anchor=trust, expected_runtime=after, now=1010)


def cli(*args):
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return subprocess.run([sys.executable, str(ROOT / 'scripts/scrum781_q0_replay_fixture.py'),
                           '--sandbox', '--offline', *map(str, args)], cwd=ROOT, env=env,
                          text=True, capture_output=True, check=False)


def write_json(path, value):
    path.write_bytes(canonical(value))
    return path


def test_cli_help_and_missing_operation_are_offline_and_fail_closed():
    help_result = subprocess.run([sys.executable, str(ROOT / 'scripts/scrum781_q0_replay_fixture.py'),
                                  '--help'], cwd=ROOT, text=True, capture_output=True, check=False)
    assert help_result.returncode == 0
    assert 'record-red' in help_result.stdout and 'verify-replay' in help_result.stdout
    missing = cli()
    assert missing.returncode == 2
    assert json.loads(missing.stdout)['status'] == 'BLOCKED'
    assert 'operation' in json.loads(missing.stdout)['reason'].lower()


def test_cli_explicit_file_flow_capture_validate_reconstruct_and_block_bad_json(sandbox):
    api, root, policy, spec = (importlib.import_module(MODULE), *sandbox)
    policy_path = write_json(root / 'sandbox/policy.json', policy)
    spec_path = write_json(root / 'sandbox/spec.json', spec)
    common = ['--root', root, '--policy', policy_path]
    captured = cli(*common, 'capture', '--spec', spec_path)
    assert captured.returncode == 0
    fixture = json.loads(captured.stdout)
    fixture_path = write_json(root / 'sandbox/fixture.json', fixture)
    for operation in ('validate', 'reconstruct'):
        result = cli(*common, operation, '--fixture', fixture_path)
        assert result.returncode == 0
        assert json.loads(result.stdout)['status'] == 'OK'
    malformed = root / 'sandbox/malformed.json'
    malformed.write_text('{"schema_id":', encoding='utf-8')
    blocked = cli(*common, 'validate', '--fixture', malformed)
    assert blocked.returncode == 2
    assert json.loads(blocked.stdout)['status'] == 'BLOCKED'
    assert 'Traceback' not in blocked.stdout + blocked.stderr


def test_cli_receipt_operations_require_explicit_trust_and_verify_chain(sandbox):
    api, root, policy, spec = (importlib.import_module(MODULE), *sandbox)
    policy_path = write_json(root / 'sandbox/policy.json', policy)
    spec_path = write_json(root / 'sandbox/spec.json', spec)
    common = ['--root', root, '--policy', policy_path]
    fixture = json.loads(cli(*common, 'capture', '--spec', spec_path).stdout)
    fixture_path = write_json(root / 'sandbox/fixture.json', fixture)
    _api, _root, _policy, _fixture, after, _docs, refs, trust = synthetic_observations(sandbox)
    trust_path = write_json(root / 'sandbox/trust.json', trust)
    receipts_path = write_json(root / 'sandbox/receipts.json',
                               {k: v for k, v in refs.items() if k != 'RED'})
    runtime_path = write_json(root / 'sandbox/runtime.json', after)
    red_ref_path = write_json(root / 'sandbox/red-ref.json', refs['RED'])
    no_trust = cli(*common, 'record-red', '--fixture', fixture_path,
                   '--receipt', red_ref_path)
    assert no_trust.returncode == 2
    assert json.loads(no_trust.stdout)['status'] == 'BLOCKED'
    red = cli(*common, 'record-red', '--fixture', fixture_path,
              '--receipt', red_ref_path, '--trust-anchor', trust_path, '--now', '1010')
    assert red.returncode == 0
    observed_path = write_json(root / 'sandbox/observed.json', json.loads(red.stdout))
    replay = cli(*common, 'verify-replay', '--fixture', observed_path, '--receipts', receipts_path,
                 '--trust-anchor', trust_path, '--expected-runtime', runtime_path, '--now', '1010')
    assert replay.returncode == 0
    result = json.loads(replay.stdout)
    assert result['result'] == 'OFFLINE_REPLAY_EVIDENCE_CONSISTENT'
    assert result['q0_l3_qualified'] is False
