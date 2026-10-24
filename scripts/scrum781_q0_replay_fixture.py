#!/usr/bin/env python3
"""Sandbox-only, OFFLINE Q0 fixture capture/verification (never executes a seam).

JSON uses sorted UTF-8 keys, compact separators, finite numbers, no duplicate
keys; this is a local canonical format, not a claim of RFC-8785 compliance.
Artifacts use SHA-256 of exact bytes. Policies must be independently pinned by
caller: a fixture's own asserted refs are NOT a source of trust. This module
cannot authenticate an incident or qualify CF-RED/CF-LOAD/Q0 L3.
"""
from __future__ import annotations

import ast
import argparse
import copy
import hashlib
import json
import math
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = 'gwc.q0.sandbox-replay-fixture/v1'
CLOSED = {'original_dwo_reproduced': False, 'q0_l3_qualified': False}
SPEC_FIELDS = {'binding', 'command', 'environment', 'dependencies', 'input', 'prestate', 'snapshots'}
FIXTURE_FIELDS = SPEC_FIELDS | {'schema_id', 'sandbox_only', *CLOSED,
    'scenario_status', 'observation_status', 'red', 'input_sha256', 'prestate_sha256',
    'snapshot_manifest', 'snapshot_manifest_sha256', 'scenario_digest'}
HEX40 = re.compile(r'[0-9a-f]{40}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
SECRET_KEY = re.compile(r'password|passwd|secret|authorization|cookie|credential|apikey|privatekey|accesstoken|refreshtoken|accesskey')
SECRET_TEXT = re.compile(r'Bearer\s+\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]+|AKIA[A-Z0-9]{16}|[a-z]+://[^\s/:]+:[^\s/@]+@|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', re.I)
MAX_BYTES = 1024 * 1024


class ReplayFixtureError(ValueError):
    """Fail-closed contract violation; messages never echo artifact contents."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ReplayFixtureError(reason)


def canonical_json(value: Any) -> bytes:
    def check(item: Any, depth: int = 0) -> None:
        _require(depth <= 64, 'JSON_DEPTH_EXCEEDED')
        if type(item) is dict:
            _require(all(type(k) is str for k in item), 'JSON_KEY_INVALID')
            for child in item.values():
                check(child, depth + 1)
        elif type(item) is list:
            for child in item:
                check(child, depth + 1)
        else:
            _require(item is None or type(item) in (str, bool, int, float), 'JSON_TYPE_INVALID')
            if type(item) is float:
                _require(math.isfinite(item), 'JSON_NUMBER_INVALID')
    check(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ReplayFixtureError('CANONICAL_JSON_INVALID') from exc


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_digest(value: Any) -> str:
    return digest(canonical_json(value))


def _fields(value: Any, names: set[str], reason: str) -> None:
    _require(type(value) is dict and set(value) == names, reason)


def _nonsecret(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _require(not SECRET_KEY.search(re.sub(r'[^a-z]', '', key.lower())), 'SECRET_FIELD_PROHIBITED')
            _nonsecret(child)
    elif isinstance(value, list):
        for child in value:
            _nonsecret(child)
    elif isinstance(value, str):
        _require(not SECRET_TEXT.search(value), 'SECRET_CONTENT_PROHIBITED')


def _decode_json(raw: bytes) -> Any:
    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            _require(key not in result, 'JSON_DUPLICATE_KEY')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
        canonical_json(value)
        _nonsecret(value)
        return value
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ReplayFixtureError('JSON_ARTIFACT_INVALID') from exc


def _ref(ref: Any, *, seam: bool = False) -> None:
    _fields(ref, {'path', 'sha256', 'symbol'} if seam else {'path', 'sha256'}, 'ARTIFACT_REF_INVALID')
    path = ref['path']
    _require(type(path) is str and 0 < len(path) <= 512 and
             re.fullmatch(r'[A-Za-z0-9_./-]+', path) is not None, 'ARTIFACT_PATH_INVALID')
    parts = path.split('/')
    _require(not PurePosixPath(path).is_absolute() and all(p and not p.startswith('.')
             for p in parts if p != '.gwc') and all(p not in {'.', '..'} for p in parts),
             'ARTIFACT_PATH_ESCAPE')
    _require(path.startswith(('sandbox/', 'tools/node_architect/', 'core/node-architect/',
                             'tests/', 'scripts/scrum781_', '.gwc/tasks/SCRUM-781/fixtures/')),
             'ARTIFACT_PATH_NOT_ALLOWLISTED')
    _require(type(ref['sha256']) is str and HEX64.fullmatch(ref['sha256']) is not None,
             'ARTIFACT_DIGEST_INVALID')
    if seam:
        _require(path.endswith('.py') and type(ref['symbol']) is str and
                 ref['symbol'].isidentifier(), 'EXECUTABLE_SEAM_MISSING')


def _read_artifact(ref: dict, root: Path) -> bytes:
    _ref(ref)
    # Directory-relative O_NOFOLLOW reads prohibit symlink races at every level.
    fd = None
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        parts = ref['path'].split('/')
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        os.close(fd)
        fd = child
        info = os.fstat(fd)
        _require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES, 'ARTIFACT_NOT_BOUNDED_FILE')
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            raw = stream.read(MAX_BYTES + 1)
        _require(len(raw) <= MAX_BYTES, 'ARTIFACT_TOO_LARGE')
    except OSError as exc:
        raise ReplayFixtureError('ARTIFACT_UNREADABLE') from exc
    finally:
        if fd is not None:
            os.close(fd)
    _require(digest(raw) == ref.get('sha256'), 'ARTIFACT_DIGEST_MISMATCH')
    try:
        _nonsecret(raw.decode('utf-8'))
    except UnicodeError as exc:
        raise ReplayFixtureError('ARTIFACT_NOT_TEXT') from exc
    if ref['path'].endswith('.json'):
        _decode_json(raw)
    return raw


def _source(ref: dict, root: Path) -> None:
    _ref(ref, seam=True)
    try:
        tree = ast.parse(_read_artifact({k: ref[k] for k in ('path', 'sha256')}, root))
    except SyntaxError as exc:
        raise ReplayFixtureError('EXECUTABLE_SEAM_INVALID') from exc
    functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == ref['symbol']]
    _require(len(functions) == 1, 'EXECUTABLE_SEAM_MISSING')
    body = [n for n in functions[0].body if not (isinstance(n, ast.Expr) and
            isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
    _require(bool(body) and not all(isinstance(n, (ast.Pass, ast.Raise)) or
             isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and
             n.value.value is Ellipsis for n in body), 'EXECUTABLE_SEAM_MISSING')


def _validate_spec(spec: dict, root: Path, policy: dict) -> None:
    _fields(spec, SPEC_FIELDS, 'SPEC_FIELDS_INVALID')
    _fields(policy, {'binding', 'command', 'environment', 'dependencies', 'expected_result',
                     'legal_next_states', 'max_age_seconds'}, 'POLICY_FIELDS_INVALID')
    canonical_json(spec)
    canonical_json(policy)
    _nonsecret(spec)
    _nonsecret(policy)
    for key in ('binding', 'command', 'environment', 'dependencies'):
        _require(canonical_json(spec[key]) == canonical_json(policy[key]), 'POLICY_BINDING_MISMATCH')
    b = spec['binding']
    _fields(b, {'repository', 'branch', 'run_id', 'head', 'candidate_id', 'mandatory_entry',
                'runtime_epoch', 'gate', 'plan', 'profile', 'route', 'route_id', 'seam'}, 'BINDING_FIELDS_INVALID')
    _require(b['repository'] == 'nhatnguyenquang1838-coder/gwc' and
             b['branch'] == 'fix/SCRUM-781-q0-fresh-20261010-r1' and
             b['run_id'] == 'scrum781-q0-fresh-20261010-r1' and
             b['runtime_epoch'] == 'UNIVERSAL_V2_DEVELOPMENT' and b['gate'] == 'UR.G2', 'Q0_BINDING_INVALID')
    _require(type(b['head']) is str and HEX40.fullmatch(b['head']) is not None and
             type(b['candidate_id']) is str and IDENTIFIER.fullmatch(b['candidate_id']) is not None,
             'SOURCE_IDENTITY_INVALID')
    for key in ('plan', 'profile', 'route'):
        _ref(b[key])
    plan, profile, route = [_decode_json(_read_artifact(b[k], root)) for k in ('plan', 'profile', 'route')]
    _require(all(type(x) is dict for x in (plan, profile, route)), 'SOURCE_CONTRACT_INVALID')
    _require(all(plan.get(k) == b[v] for k, v in (
        ('source_repo', 'repository'), ('branch', 'branch'), ('run_id', 'run_id'),
        ('runtime_epoch', 'runtime_epoch'), ('current_gate', 'gate'))), 'PLAN_BINDING_INVALID')
    entries = profile.get('mandatory_qualification_entries')
    _require(type(entries) is list and len(entries) == 13 and all(type(e) is str for e in entries)
             and len(set(entries)) == 13 and b['mandatory_entry'] in entries,
             'MANDATORY_ENTRY_INVALID')
    qualification_nodes = profile.get('qualification_nodes')
    _require(type(qualification_nodes) is dict, 'PROFILE_QUALIFICATION_NODES_INVALID')
    gate_entry = qualification_nodes.get(b['gate'])
    _require(type(gate_entry) is dict, 'PROFILE_GATE_ENTRY_INVALID')
    _require(profile.get('runtime_epoch') == b['runtime_epoch'] and
             gate_entry.get('action') == b['route_id'] and
             route.get('runtime_epoch') == b['runtime_epoch'] and
             route.get('runtime_family') == 'UNIVERSAL_V2' and
             route.get('q0_qualification_profile_ref') == b['profile']['path'], 'ROUTE_BINDING_INVALID')
    _source(b['seam'], root)
    _require(spec['command'] == ['python', b['seam']['path'], '--sandbox', '--offline'], 'COMMAND_NOT_ALLOWLISTED')
    _require(spec['environment'] == {'Q0_SANDBOX': '1', 'Q0_OFFLINE': '1', 'PYTHONHASHSEED': '0'},
             'ENVIRONMENT_NOT_ALLOWLISTED')
    for key in ('dependencies', 'snapshots'):
        _require(type(spec[key]) is list and len(spec[key]) <= 64, 'SNAPSHOT_LIST_INVALID')
        for ref in spec[key]:
            _ref(ref)
    _require(type(policy['max_age_seconds']) is int and 0 < policy['max_age_seconds'] <= 86400,
             'FRESHNESS_POLICY_INVALID')
    _fields(policy['expected_result'], {'next_state', 'poststate'}, 'RESULT_ORACLE_INVALID')
    _require(type(policy['expected_result']['next_state']) is str and
             type(policy['expected_result']['poststate']) is dict, 'RESULT_ORACLE_INVALID')
    _require(type(policy['legal_next_states']) is list and bool(policy['legal_next_states']) and
             all(s in {'UR.G3', 'UR.G2'} for s in policy['legal_next_states']) and
             policy['expected_result']['next_state'] in policy['legal_next_states'], 'LEGAL_NEXT_STATE_INVALID')


def _manifest(spec: dict) -> list[dict]:
    binding = spec['binding']
    refs = [binding[k] for k in ('plan', 'profile', 'route', 'seam')]
    refs += spec['dependencies'] + spec['snapshots']
    unique = {}
    for ref in refs:
        item = {k: ref[k] for k in ('path', 'sha256')}
        _require(ref['path'] not in unique or unique[ref['path']] == item,
                 'SNAPSHOT_CONFLICT')
        unique[ref['path']] = item
    return sorted(unique.values(), key=lambda r: r['path'])


def _scenario_digest(fixture: dict) -> str:
    return _json_digest({k: v for k, v in fixture.items() if k not in {
        'scenario_digest', 'scenario_status', 'observation_status', 'red'}})


def capture_fixture(spec: dict, *, root: Path, policy: dict) -> dict:
    """Return a detached proposal. No log, receipt, or failure is manufactured."""
    _validate_spec(spec, root, policy)
    fixture = copy.deepcopy(spec)
    fixture.update(schema_id=SCHEMA, sandbox_only=True, **CLOSED,
                   scenario_status='PROPOSAL_ONLY', observation_status='UNOBSERVED', red=None)
    fixture['input_sha256'] = _json_digest(fixture['input'])
    fixture['prestate_sha256'] = _json_digest(fixture['prestate'])
    fixture['snapshot_manifest'] = _manifest(fixture)
    fixture['snapshot_manifest_sha256'] = _json_digest(fixture['snapshot_manifest'])
    fixture['scenario_digest'] = _scenario_digest(fixture)
    validate_fixture(fixture, root=root, policy=policy)
    return fixture


def validate_fixture(fixture: dict, *, root: Path, policy: dict) -> str:
    """Verify policy and artifact shape/digests; a RED ref here is not authenticated."""
    _fields(fixture, FIXTURE_FIELDS, 'FIXTURE_FIELDS_INVALID')
    _validate_spec({k: fixture[k] for k in SPEC_FIELDS}, root, policy)
    _require(fixture.get('schema_id') == SCHEMA and fixture.get('sandbox_only') is True,
             'SCHEMA_INVALID')
    _require(all(fixture.get(k) is False for k in CLOSED), 'QUALIFICATION_CLOSED')
    for field in ('binding', 'command', 'environment', 'dependencies'):
        _require(fixture.get(field) == policy.get(field), 'POLICY_BINDING_MISMATCH')
    for field in ('input', 'prestate'):
        _require(fixture.get(field + '_sha256') == _json_digest(fixture[field]),
                 'CANONICAL_DIGEST_MISMATCH')
    _require(fixture.get('snapshot_manifest') == _manifest(fixture), 'SNAPSHOT_MANIFEST_MISMATCH')
    for ref in fixture['snapshot_manifest']:
        _read_artifact(ref, root)
    _require(fixture.get('snapshot_manifest_sha256') == _json_digest(fixture['snapshot_manifest']),
             'SNAPSHOT_MANIFEST_DIGEST_MISMATCH')
    _require(fixture.get('scenario_digest') == _scenario_digest(fixture), 'SCENARIO_DIGEST_MISMATCH')
    _require(fixture.get('scenario_status') == 'PROPOSAL_ONLY'
             and fixture.get('observation_status') == 'UNOBSERVED' and
             (fixture.get('red') is None or type(fixture.get('red')) is dict),
             'OBSERVATION_INVALID')
    if fixture.get('red') is not None:
        _validate_recorded_red_shape(fixture, fixture['red'], root)
    return fixture['scenario_digest']


def reconstruct_prestate(fixture: dict, *, root: Path, policy: dict) -> dict:
    """Reconstruct in memory only; never touches a checkpoint or restores files."""
    validate_fixture(fixture, root=root, policy=policy)
    return {'prestate': copy.deepcopy(fixture['prestate']),
            'snapshots': {ref['path']: _read_artifact(ref, root) for ref in fixture['snapshots']}}


RECEIPT_SCHEMA = 'gwc.q0.sandbox-runtime-observation/v1'
RECEIPT_FIELDS = {'schema_id', 'stage', 'scenario_digest', 'binding', 'input_sha256',
                  'prestate_sha256', 'snapshot_manifest_sha256', 'runtime', 'observed_at',
                  'exit_code', 'reason_code', 'execution_prestate_sha256', 'idempotency_key',
                  'result', 'result_sha256', 'executed_effects', 'sandbox_only',
                  'original_dwo_reproduced', 'q0_l3_qualified', 'evidence'}
STAGES = ('RED', 'LOAD', 'REPLAY', 'REPEAT', 'IDEMPOTENCY')


def _trust_anchor(anchor: Any, stages: tuple[str, ...]) -> dict:
    _fields(anchor, {'authority_id', 'receipt_digests'}, 'TRUST_ANCHOR_REQUIRED')
    _require(type(anchor['authority_id']) is str and
             IDENTIFIER.fullmatch(anchor['authority_id']) is not None,
             'TRUST_ANCHOR_INVALID')
    digests = anchor['receipt_digests']
    _require(type(digests) is dict and all(stage in digests for stage in stages) and
             all(type(k) is str and k in STAGES and type(v) is str and HEX64.fullmatch(v)
                 for k, v in digests.items()), 'TRUST_ANCHOR_INVALID')
    return digests


def _receipt(ref: Any, stage: str, *, fixture: dict, root: Path, policy: dict,
             trust_digests: dict, now: int | float) -> dict:
    _ref(ref)
    _require(trust_digests.get(stage) == ref['sha256'], 'RECEIPT_NOT_EXTERNALLY_ANCHORED')
    doc = _decode_json(_read_artifact(ref, root))
    _fields(doc, RECEIPT_FIELDS, 'RECEIPT_SCHEMA_INVALID')
    _require(doc['schema_id'] == RECEIPT_SCHEMA and doc['stage'] == stage,
             'RECEIPT_SCHEMA_INVALID')
    _require(doc['scenario_digest'] == fixture['scenario_digest'] and
             doc['binding'] == fixture['binding'] and doc['input_sha256'] == fixture['input_sha256'] and
             doc['prestate_sha256'] == fixture['prestate_sha256'] and
             doc['snapshot_manifest_sha256'] == fixture['snapshot_manifest_sha256'],
             'RECEIPT_SCENARIO_BINDING_MISMATCH')
    _require(type(doc['sandbox_only']) is bool and doc['sandbox_only'] is True and
             doc['original_dwo_reproduced'] is False and doc['q0_l3_qualified'] is False and
             doc['executed_effects'] == [], 'RECEIPT_EFFECT_OR_QUALIFICATION_PROHIBITED')
    observed = doc['observed_at']
    _require(type(observed) in (int, float) and math.isfinite(observed) and
             type(now) in (int, float) and math.isfinite(now) and observed <= now and
             now - observed <= policy['max_age_seconds'], 'RECEIPT_TIME_INVALID_OR_STALE')
    _require(type(doc['reason_code']) is str and IDENTIFIER.fullmatch(doc['reason_code']) is not None,
             'RECEIPT_REASON_REQUIRED')
    _require(type(doc['exit_code']) is int and type(doc['execution_prestate_sha256']) is str and
             HEX64.fullmatch(doc['execution_prestate_sha256']) is not None and
             type(doc['idempotency_key']) is str and
             doc['idempotency_key'] == fixture['scenario_digest'], 'RECEIPT_RESULT_INVALID')
    expected_prestate = (_json_digest(policy['expected_result']['poststate'])
                         if stage == 'IDEMPOTENCY' else fixture['prestate_sha256'])
    _require(doc['execution_prestate_sha256'] == expected_prestate,
             'EXECUTION_PRESTATE_MISMATCH')
    _require((doc['result'] is None and doc['result_sha256'] is None) or
             (type(doc['result']) is dict and type(doc['result_sha256']) is str and
              HEX64.fullmatch(doc['result_sha256']) is not None and
              doc['result_sha256'] == _json_digest(doc['result'])), 'RECEIPT_RESULT_INVALID')
    _ref(doc['evidence'])
    _read_artifact(doc['evidence'], root)
    _validate_runtime(doc['runtime'], stage, fixture, root)
    if stage == 'RED':
        _require(doc['exit_code'] != 0 and doc['result'] is None and doc['result_sha256'] is None,
                 'RED_OBSERVATION_INVALID')
        runtime = doc['runtime']
        _require(runtime['loaded_source_sha'] == fixture['binding']['head'] and
                 runtime['source'] == fixture['binding']['seam'], 'RED_SOURCE_BINDING_INVALID')
    elif stage == 'LOAD':
        _require(doc['exit_code'] == 0 and doc['result'] is None and doc['result_sha256'] is None,
                 'LOAD_OBSERVATION_INVALID')
    else:
        expected = policy['expected_result']
        _require(doc['exit_code'] == 0 and doc['result'] == expected and
                 doc['result_sha256'] == _json_digest(expected) and
                 expected['next_state'] in policy['legal_next_states'],
                 'REPLAY_RESULT_INVALID')
        if stage == 'IDEMPOTENCY':
            _require(doc['execution_prestate_sha256'] == _json_digest(expected['poststate']),
                     'IDEMPOTENCY_PRESTATE_INVALID')
    return doc


def _validate_runtime(runtime: Any, stage: str, fixture: dict, root: Path) -> None:
    _fields(runtime, {'activation_id', 'process_or_session_id', 'loaded_source_sha', 'source',
                      'profile', 'instructions', 'modules'}, 'RUNTIME_IDENTITY_INVALID')
    for key in ('activation_id', 'process_or_session_id'):
        _require(type(runtime[key]) is str and IDENTIFIER.fullmatch(runtime[key]) is not None,
                 'RUNTIME_IDENTITY_INVALID')
    _require(type(runtime['loaded_source_sha']) is str and
             HEX40.fullmatch(runtime['loaded_source_sha']) is not None, 'RUNTIME_SOURCE_INVALID')
    _ref(runtime['source'], seam=True)
    _require(runtime['profile'] == fixture['binding']['profile'], 'RUNTIME_PROFILE_INVALID')
    # Parse the exact source, but never execute it. A digest-valid stub is not a seam.
    _source(runtime['source'], root)
    for key in ('instructions', 'modules'):
        items = runtime[key]
        _require(type(items) is list and 0 < len(items) <= 64, 'RUNTIME_SURFACE_MISSING')
        for item in items:
            _ref(item)
            _read_artifact(item, root)
    _require(any(item['path'] == runtime['source']['path'] and
                 item['sha256'] == runtime['source']['sha256'] for item in runtime['modules']),
             'RUNTIME_SOURCE_NOT_LOADED')
    if stage != 'RED':
        _require(runtime['loaded_source_sha'] != fixture['binding']['head'] and
                 runtime['source'] != fixture['binding']['seam'], 'FRESH_LOAD_REQUIRED')


def _validate_recorded_red_shape(fixture: dict, ref: dict, root: Path) -> None:
    """Check a recorded RED pointer's schema/digest without trust authentication."""
    _ref(ref)
    doc = _decode_json(_read_artifact(ref, root))
    _fields(doc, RECEIPT_FIELDS, 'RECEIPT_SCHEMA_INVALID')
    _require(doc['schema_id'] == RECEIPT_SCHEMA and doc['stage'] == 'RED' and
             doc['scenario_digest'] == fixture['scenario_digest'] and
             doc['binding'] == fixture['binding'] and
             doc['input_sha256'] == fixture['input_sha256'] and
             doc['prestate_sha256'] == fixture['prestate_sha256'] and
             doc['snapshot_manifest_sha256'] == fixture['snapshot_manifest_sha256'],
             'RECORDED_RED_SHAPE_INVALID')
    _require(doc['sandbox_only'] is True and doc['original_dwo_reproduced'] is False and
             doc['q0_l3_qualified'] is False and doc['executed_effects'] == [],
             'RECORDED_RED_CLOSED_FLAGS_INVALID')
    _ref(doc['evidence'])
    _read_artifact(doc['evidence'], root)


def record_red(fixture: dict, red_ref: dict, *, root: Path, policy: dict,
               trust_anchor: dict, now: int | float) -> dict:
    """Attach a caller-anchored RED receipt as offline consistency evidence only."""
    proposal = copy.deepcopy(fixture)
    validate_fixture(proposal, root=root, policy=policy)
    trusted = _trust_anchor(trust_anchor, ('RED',))
    _receipt(red_ref, 'RED', fixture=proposal, root=root, policy=policy,
             trust_digests=trusted, now=now)
    observed = copy.deepcopy(proposal)
    # A caller-supplied digest anchor permits consistency checking only; it is
    # not a signature or proof that this document came from a runtime.
    observed['red'] = copy.deepcopy(red_ref)
    _require(observed['scenario_digest'] == proposal['scenario_digest'], 'SCENARIO_DIGEST_MISMATCH')
    return observed


def verify_replay(fixture: dict, receipt_refs: dict, *, root: Path, policy: dict,
                  trust_anchor: dict, expected_runtime: dict, now: int | float) -> dict:
    """Check a complete externally anchored receipt chain; never executes runtime code."""
    _fields(fixture, FIXTURE_FIELDS, 'FIXTURE_FIELDS_INVALID')
    _require(fixture['scenario_status'] == 'PROPOSAL_ONLY' and
             fixture['observation_status'] == 'UNOBSERVED' and
             type(fixture['red']) is dict, 'OBSERVED_RED_REQUIRED')
    validate_fixture(fixture, root=root, policy=policy)
    observed = copy.deepcopy(fixture)
    _require(_scenario_digest(fixture) == fixture['scenario_digest'], 'SCENARIO_DIGEST_MISMATCH')
    _fields(receipt_refs, set(STAGES) - {'RED'}, 'RECEIPT_CHAIN_INVALID')
    trusted = _trust_anchor(trust_anchor, STAGES)
    docs = {'RED': _receipt(fixture['red'], 'RED', fixture=observed, root=root,
                            policy=policy, trust_digests=trusted, now=now)}
    for stage in STAGES[1:]:
        docs[stage] = _receipt(receipt_refs[stage], stage, fixture=observed, root=root,
                               policy=policy, trust_digests=trusted, now=now)
    times = [docs[s]['observed_at'] for s in STAGES]
    _require(all(left < right for left, right in zip(times, times[1:])), 'RECEIPT_ORDER_INVALID')
    red_runtime, loaded = docs['RED']['runtime'], docs['LOAD']['runtime']
    _require(loaded == expected_runtime and
             loaded['activation_id'] != red_runtime['activation_id'] and
             loaded['process_or_session_id'] != red_runtime['process_or_session_id'],
             'FRESH_LOAD_IDENTITY_MISMATCH')
    for stage in STAGES[2:]:
        _require(docs[stage]['runtime'] == loaded, 'REPLAY_RUNTIME_MISMATCH')
    # The same oracle and idempotency key must hold across two independent replays.
    _require(docs['REPLAY']['result'] == docs['REPEAT']['result'] ==
             docs['IDEMPOTENCY']['result'], 'DETERMINISM_MISMATCH')
    expected = policy['expected_result']
    return {'result': 'OFFLINE_REPLAY_EVIDENCE_CONSISTENT',
            'result_sha256': _json_digest(expected), 'next_state': expected['next_state'],
            'original_dwo_reproduced': False, 'q0_l3_qualified': False,
            'executed_effects': [], 'assurance': 'CONDITIONAL_ON_CALLER_SUPPLIED_TRUST_ANCHOR'}


def _read_cli_json(path: str) -> Any:
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(fd)
        _require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES, 'CLI_INPUT_NOT_BOUNDED_FILE')
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            raw = stream.read(MAX_BYTES + 1)
        _require(len(raw) <= MAX_BYTES, 'CLI_INPUT_TOO_LARGE')
    except OSError as exc:
        raise ReplayFixtureError('CLI_INPUT_UNREADABLE') from exc
    finally:
        if fd is not None:
            os.close(fd)
    return _decode_json(raw)


class _CLIParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        reason = 'CLI_OPERATION_REQUIRED' if 'operation' in message else 'CLI_ARGUMENTS_INVALID'
        raise ReplayFixtureError(reason)


def _parser() -> argparse.ArgumentParser:
    parser = _CLIParser(description='Offline sandbox Q0 fixture consistency utility; never executes a seam.')
    parser.add_argument('--sandbox', action='store_true', required=True)
    parser.add_argument('--offline', action='store_true', required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--policy', required=True)
    subs = parser.add_subparsers(dest='operation', required=True)
    capture = subs.add_parser('capture', help='validate source-bound spec and print proposal JSON')
    capture.add_argument('--spec', required=True)
    for name in ('validate', 'reconstruct'):
        command = subs.add_parser(name, help='validate a fixture or reconstruct its prestate in memory')
        command.add_argument('--fixture', required=True)
    red = subs.add_parser('record-red', help='attach externally anchored RED receipt consistency')
    red.add_argument('--fixture', required=True); red.add_argument('--receipt', required=True)
    red.add_argument('--trust-anchor', required=True); red.add_argument('--now', required=True, type=float)
    replay = subs.add_parser('verify-replay', help='verify externally anchored replay chain consistency')
    replay.add_argument('--fixture', required=True); replay.add_argument('--receipts', required=True)
    replay.add_argument('--trust-anchor', required=True); replay.add_argument('--expected-runtime', required=True)
    replay.add_argument('--now', required=True, type=float)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        _require(args.sandbox and args.offline, 'OFFLINE_SANDBOX_REQUIRED')
        root = Path(args.root)
        policy = _read_cli_json(args.policy)
        if args.operation == 'capture':
            result = capture_fixture(_read_cli_json(args.spec), root=root, policy=policy)
        else:
            fixture = _read_cli_json(args.fixture)
            if args.operation == 'validate':
                result = {'status': 'OK', 'scenario_digest': validate_fixture(fixture, root=root, policy=policy)}
            elif args.operation == 'reconstruct':
                value = reconstruct_prestate(fixture, root=root, policy=policy)
                result = {'status': 'OK', 'prestate': value['prestate'],
                          'snapshot_paths': sorted(value['snapshots'])}
            elif args.operation == 'record-red':
                result = record_red(fixture, _read_cli_json(args.receipt), root=root, policy=policy,
                                    trust_anchor=_read_cli_json(args.trust_anchor), now=args.now)
            else:
                result = verify_replay(fixture, _read_cli_json(args.receipts), root=root, policy=policy,
                                       trust_anchor=_read_cli_json(args.trust_anchor),
                                       expected_runtime=_read_cli_json(args.expected_runtime), now=args.now)
        sys.stdout.buffer.write(canonical_json(result) + b'\n')
        return 0
    except ReplayFixtureError as exc:
        reason = str(exc)
        if not re.fullmatch(r'[A-Z0-9_]{1,80}', reason):
            reason = 'VALIDATION_BLOCKED'
        sys.stdout.buffer.write(canonical_json({'status': 'BLOCKED', 'reason': reason}) + b'\n')
        return 2
    except (OSError, TypeError, KeyError, ValueError, AttributeError, RecursionError, OverflowError):
        sys.stdout.buffer.write(canonical_json({'status': 'BLOCKED', 'reason': 'INPUT_OR_SCHEMA_INVALID'}) + b'\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
