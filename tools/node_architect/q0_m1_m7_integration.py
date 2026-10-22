"""Source-bound, observation-only Q0 integration of the frozen M1-M7 library.

Successor activation preparation is a preflight contract, not an executor.

No scheduler, mailbox, browser, lease or authority writes. Execution Binding is
identity, NOT an approval. Native qualification remains a separate admission.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
import subprocess
from typing import Any, Mapping

PLAN_REF = 'core/node-architect/scrum781-q0-fresh-execution-plan-r2.json'
ROUTE_REF = 'core/node-architect/q0-engineering-coordination-route-r1.json'
ACTIVATION_RECEIPT_REF = '.gwc/tasks/SCRUM-781/activation/cf-plan-activation.json'


_ACTIVATION_EFFECTS = ('selector_write', 'checkpoint_write', 'cursor_advance')
_ACTIVATION_RECEIPT = 'activation-receipt.json'
_ACTIVATION_JOURNAL = 'activation-journal.json'
_ACTIVATION_LEASE = '.activation-lease.json'


def _activation_state_paths(root: Path) -> dict[str, Path]:
    return {name: root / filename for name, filename in {
        'selector_write': 'selector.json', 'checkpoint_write': 'checkpoint.json',
        'cursor_advance': 'cursor.json', 'outbox': 'outbox.json',
    }.items()}


def _state_read(path: Path) -> Any:
    # A missing sandbox copy is the defined empty state: JSON null.
    return json.loads(path.read_text('utf-8')) if path.is_file() else None


def _state_hash(value: Any) -> str:
    return _digest({'state': value})


def read_activation_receipt(sandbox_root: Path | str) -> dict[str, Any] | None:
    """Read and verify the durable sandbox activation receipt after restart."""
    path = Path(sandbox_root).resolve() / _ACTIVATION_RECEIPT
    if not path.is_file():
        return None
    receipt = json.loads(path.read_text('utf-8'))
    digest = receipt.get('receipt_digest')
    body = {k: v for k, v in receipt.items() if k != 'receipt_digest'}
    if receipt.get('schema_id') != 'gwc.q0.successor-activation-receipt.v1' or digest != _digest(body):
        raise ValueError('ACTIVATION_RECEIPT_INVALID')
    return receipt


def _write_json_atomic(path: Path, value: Any) -> None:
    raw = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n'
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(raw, encoding='utf-8')
    temp.replace(path)


def _iso_utc(value: Any) -> float:
    from datetime import datetime, timezone
    if not isinstance(value, str):
        raise ValueError('GRANT_EXPIRED')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('GRANT_EXPIRED') from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError('GRANT_EXPIRED')
    return parsed.timestamp()


def _validate_activation_grant(grant: Any, predecessor: Mapping[str, Any],
                               runtime_plan: Mapping[str, Any], node_allocation: Mapping[str, Any],
                               branch: str, head: str) -> str:
    import time
    if grant is None:
        raise ValueError('LIVE_ACTIVATION_AUTHORITY_REQUIRED')
    if not isinstance(grant, Mapping):
        raise ValueError('GRANT_IDENTITY_REQUIRED')
    if grant.get('authority_kind') != 'SEPARATE_HUMAN_OR_CONTROLLER_GRANT':
        raise ValueError('GRANT_AUTHORITY_KIND_INVALID')
    if (not isinstance(grant.get('grant_ref'), str) or not grant['grant_ref'].strip()
            or not isinstance(grant.get('actor'), str) or not grant['actor'].strip()):
        raise ValueError('GRANT_IDENTITY_REQUIRED')
    now = time.time()
    issued, expires = _iso_utc(grant.get('issued_at')), _iso_utc(grant.get('expires_at'))
    if issued > now or expires <= now or expires <= issued:
        raise ValueError('GRANT_EXPIRED')
    if not isinstance(grant.get('scope'), list) or 'q0.live_activation.sandbox' not in grant['scope']:
        raise ValueError('GRANT_SCOPE_INVALID')
    allocation_digest = node_allocation.get('content_digest')
    if isinstance(allocation_digest, Mapping):
        allocation_digest = allocation_digest.get('value')
    if not allocation_digest:
        allocation_digest = node_allocation.get('digest')
    expected = {'predecessor_context_digest': _digest(predecessor),
                'runtime_plan_digest': runtime_plan.get('digest') or _digest(runtime_plan),
                'node_allocation_digest': allocation_digest,
                'branch': branch, 'head': head}
    bindings = grant.get('bindings')
    if not isinstance(bindings, Mapping) or any(bindings.get(k) != v for k, v in expected.items()):
        raise ValueError('GRANT_BINDING_MISMATCH')
    return _digest(dict(grant))


def _lease_acquire(root: Path, *, ttl: int = 60) -> str:
    import os, time, uuid
    path = root / _ACTIVATION_LEASE
    owner = uuid.uuid4().hex
    payload = {'owner_id': owner, 'expires_at': time.time() + ttl}
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w') as handle:
                json.dump(payload, handle)
            return owner
        except FileExistsError:
            try:
                current = json.loads(path.read_text('utf-8'))
                if float(current.get('expires_at', 0)) <= time.time():
                    path.unlink()
                    continue
            except (OSError, ValueError, TypeError):
                pass
            raise ValueError('LEASE_HELD_BY_OTHER')
    raise ValueError('LEASE_HELD_BY_OTHER')


def _lease_release(root: Path, owner: str) -> None:
    path = root / _ACTIVATION_LEASE
    try:
        if json.loads(path.read_text('utf-8')).get('owner_id') == owner:
            path.unlink()
    except (OSError, ValueError):
        pass


def _journal_read(root: Path) -> list[dict[str, Any]]:
    path = root / _ACTIVATION_JOURNAL
    if not path.exists():
        return []
    value = json.loads(path.read_text('utf-8'))
    if not isinstance(value, list):
        raise ValueError('ACTIVATION_JOURNAL_INVALID')
    return value


def _journal_append(root: Path, record: dict[str, Any]) -> None:
    journal = _journal_read(root)
    journal.append(record)
    _write_json_atomic(root / _ACTIVATION_JOURNAL, journal)


def reconcile_activation_journal(sandbox_root: Path | str) -> dict[str, Any]:
    """Complete or roll back the most recent incomplete sandbox PREPARE safely."""
    root = Path(sandbox_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    owner = _lease_acquire(root)
    try:
        journal = _journal_read(root)
        committed = {row.get('idempotency_key') for row in journal if row.get('phase') == 'COMMIT'}
        pending = next((row for row in reversed(journal)
                        if row.get('phase') == 'PREPARE' and row.get('idempotency_key') not in committed), None)
        if pending is None:
            return {'reconciled': False, 'status': 'NO_PENDING_PREPARE'}
        paths = _activation_state_paths(root)
        actual = {key: _state_read(paths[key]) for key in _ACTIVATION_EFFECTS}
        expected_before = pending['before_state']
        expected_after = pending['after_state']
        if all(_state_hash(actual[k]) in {_state_hash(expected_before[k]), _state_hash(expected_after[k])}
               for k in _ACTIVATION_EFFECTS):
            for effect in _ACTIVATION_EFFECTS:
                if _state_hash(actual[effect]) != _state_hash(expected_after[effect]):
                    _write_json_atomic(paths[effect], expected_after[effect])
            post = {k: _state_hash(_state_read(paths[k])) for k in _ACTIVATION_EFFECTS}
            _journal_append(root, {'phase': 'COMMIT', 'idempotency_key': pending['idempotency_key'],
                                   'post_hashes': post, 'reconciled': True})
            _write_json_atomic(root / _ACTIVATION_RECEIPT, pending['receipt'])
            return {'reconciled': True, 'status': 'COMPLETED'}
        for effect in reversed(_ACTIVATION_EFFECTS):
            _write_json_atomic(paths[effect], expected_before[effect])
        _journal_append(root, {'phase': 'ROLLBACK_APPLIED', 'idempotency_key': pending['idempotency_key'],
                               'reason': 'CAS_CONFLICT'})
        return {'reconciled': True, 'status': 'ROLLED_BACK'}
    finally:
        _lease_release(root, owner)


def activate_successor_plan(*, grant, predecessor, runtime_plan, node_allocation,
                            branch, head, sandbox_root, mode='DRY_RUN') -> dict[str, Any]:
    """Validate and activate a successor plan only against disposable sandbox copies."""
    if mode not in ('DRY_RUN', 'SANDBOX_COMMIT'):
        raise ValueError('LIVE_ACTIVATION_MODE_INVALID')
    import os
    root = Path(sandbox_root).expanduser().resolve()
    hermes_home = Path(os.environ.get('HERMES_HOME', str(Path.home() / '.hermes'))).expanduser().resolve()
    if (not root.is_dir() or (root / '.gwc').exists()
            or root == hermes_home or hermes_home in root.parents):
        raise ValueError('LIVE_ACTIVATION_LIVE_PATH_FORBIDDEN')
    if not isinstance(predecessor, Mapping) or not isinstance(runtime_plan, Mapping) or not isinstance(node_allocation, Mapping):
        raise ValueError('LIVE_ACTIVATION_BINDING_INVALID')
    grant_digest = _validate_activation_grant(grant, predecessor, runtime_plan, node_allocation, branch, head)
    if any((root / name).resolve().parent != root for name in ('selector.json','checkpoint.json','cursor.json','outbox.json')):
        raise ValueError('LIVE_ACTIVATION_LIVE_PATH_FORBIDDEN')
    root.mkdir(parents=True, exist_ok=True)
    owner = _lease_acquire(root)
    try:
        predecessor_id = predecessor.get('run_id') or predecessor.get('identity')
        successor_id = runtime_plan.get('run_id')
        plan_digest = runtime_plan.get('digest') or _digest(runtime_plan)
        key = _digest({'grant_ref': grant['grant_ref'], 'predecessor_run': predecessor_id,
                       'successor_run': successor_id, 'plan_digest': plan_digest})
        journal = _journal_read(root)
        if any(r.get('phase') == 'COMMIT' and r.get('idempotency_key') == key for r in journal):
            return {'accepted': True, 'executed': False, 'mode': mode, 'effects': list(_ACTIVATION_EFFECTS),
                    'applied_effects': [], 'already_applied': True,
                    'activation_receipt': read_activation_receipt(root), 'journal_ref': str(root / _ACTIVATION_JOURNAL),
                    'readback': {k: _state_hash(_state_read(v)) for k, v in _activation_state_paths(root).items()},
                    'authority_granted': False, 'typed_ce_admitted': False, 'protected_effect': 'SANDBOX_ONLY'}
        paths = _activation_state_paths(root)
        before = {effect: _state_read(paths[effect]) for effect in _ACTIVATION_EFFECTS}
        snapshot = {k: _state_hash(_state_read(v)) for k, v in paths.items()}
        successor = {'run_id': successor_id, 'runtime_plan': dict(runtime_plan),
                     'node_allocation': dict(node_allocation), 'source_head': head, 'branch': branch}
        after = {'selector_write': successor,
                 'checkpoint_write': {'predecessor_run_id': predecessor_id, 'successor_run_id': successor_id,
                                      'context_digest': _digest(successor)},
                 'cursor_advance': {'run_id': successor_id, 'branch': branch, 'head': head}}
        receipt_body = {'schema_id': 'gwc.q0.successor-activation-receipt.v1',
                        'predecessor_identity': predecessor_id, 'r3_plan_digest': predecessor.get('runtime_plan_digest'),
                        'predecessor_context_digest': _digest(predecessor), 'successor_run_id': successor_id,
                        'successor_runtime_plan_digest': plan_digest, 'node_allocation': dict(node_allocation),
                        'source_head': head, 'branch': branch, 'grant_ref': grant['grant_ref'],
                        'grant_digest': grant_digest, 'effects': [
                            {'effect': effect, 'pre_hash': _state_hash(before[effect]),
                             'post_hash': _state_hash(after[effect])} for effect in _ACTIVATION_EFFECTS]}
        receipt = {**receipt_body, 'receipt_digest': _digest(receipt_body)}
        prepare = {'phase': 'PREPARE', 'idempotency_key': key, 'snapshot_hashes': snapshot,
                   'before_state': before, 'after_state': after, 'receipt': receipt,
                   'effects': list(_ACTIVATION_EFFECTS), 'mode': mode}
        _journal_append(root, prepare)
        applied = []
        if mode == 'SANDBOX_COMMIT':
            for effect in _ACTIVATION_EFFECTS:
                current = _state_read(paths[effect])
                if _state_hash(current) != _state_hash(before[effect]):
                    raise ValueError('CAS_CONFLICT')
                _write_json_atomic(paths[effect], after[effect])
                applied.append(effect)
            _journal_append(root, {'phase': 'COMMIT', 'idempotency_key': key,
                                   'post_hashes': {k: _state_hash(_state_read(paths[k])) for k in _ACTIVATION_EFFECTS}})
            _write_json_atomic(root / _ACTIVATION_RECEIPT, receipt)
        return {'accepted': True, 'executed': mode == 'SANDBOX_COMMIT', 'mode': mode,
                'effects': list(_ACTIVATION_EFFECTS), 'applied_effects': applied, 'already_applied': False,
                'activation_receipt': receipt if mode == 'SANDBOX_COMMIT' else None,
                'journal_ref': str(root / _ACTIVATION_JOURNAL),
                'readback': {k: _state_hash(_state_read(v)) for k, v in paths.items()},
                'authority_granted': False, 'typed_ce_admitted': False, 'protected_effect': 'SANDBOX_ONLY'}
    finally:
        _lease_release(root, owner)


_LIVE_ACTIVATION_JOURNAL = 'live-activation-journal.json'
_R3_PREDECESSOR_PLAN_REF = 'core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json'


def _live_activation_paths(root: Path) -> dict[str, Path]:
    activation_dir = root / ACTIVATION_RECEIPT_REF
    return {
        'route': root / ROUTE_REF,
        'plan': root / _R3_PREDECESSOR_PLAN_REF,
        'record': activation_dir,
        'database': activation_dir.parent / 'engineering-plan-activation.sqlite3',
        'selector': root / 'selector.json',
        'checkpoint': root / 'checkpoint.json',
        'cursor': root / 'cursor.json',
        'journal': root / _LIVE_ACTIVATION_JOURNAL,
    }


def _live_target_guard(root: Path) -> None:
    import os
    target = root.expanduser().resolve()
    repo = Path(__file__).resolve().parents[2]
    hermes_home = Path(os.environ.get('HERMES_HOME', str(Path.home() / '.hermes'))).expanduser().resolve()
    if target == repo or repo in target.parents or target == hermes_home or hermes_home in target.parents:
        raise ValueError('LIVE_ACTIVATION_LIVE_TARGET_FORBIDDEN')
    gwc = target / '.gwc'
    if gwc.is_symlink() and gwc.resolve().is_relative_to(repo / '.gwc'):
        raise ValueError('LIVE_ACTIVATION_LIVE_TARGET_FORBIDDEN')


def _live_db_generation(db_path: Path, plan_ref: str) -> int:
    import sqlite3
    if not db_path.exists():
        return 0
    with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as db:
        try:
            row = db.execute('SELECT generation FROM engineering_plan_activation WHERE plan_ref=?',
                             (plan_ref,)).fetchone()
        except sqlite3.OperationalError:
            return 0
    return int(row[0]) if row else 0


def reconcile_live_activation_journal(isolated_root: Path | str) -> dict[str, Any]:
    """Finish a durable live-bridge PREPARE using only its isolated target."""
    root = Path(isolated_root).expanduser().resolve()
    _live_target_guard(root)
    journal_path = root / _LIVE_ACTIVATION_JOURNAL
    if not journal_path.exists():
        return {'reconciled': False, 'status': 'NO_PENDING_PREPARE'}
    rows = json.loads(journal_path.read_text('utf-8'))
    committed = {r.get('key') for r in rows if r.get('phase') == 'COMMIT'}
    pending = next((r for r in reversed(rows) if r.get('phase') == 'PREPARE' and r.get('key') not in committed), None)
    if pending is None:
        return {'reconciled': False, 'status': 'NO_PENDING_PREPARE'}
    paths = _live_activation_paths(root)
    for rel, content in pending['files'].items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + '.prepare')
        temp.write_bytes(bytes.fromhex(content))
        temp.replace(path)
    import sqlite3
    db_path = paths['database']
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS engineering_plan_activation '
                   '(plan_ref TEXT PRIMARY KEY, plan_digest TEXT, context_digest TEXT, generation INTEGER, activated_at TEXT)')
        db.execute('INSERT OR IGNORE INTO engineering_plan_activation VALUES (?,?,?,?,?)',
                   (pending['plan_ref'], pending['plan_digest'], pending['receipt']['checkpoint_receipt_digest'],
                    pending['generation'], pending['activated_at']))
    rows.append({'phase': 'COMMIT', 'key': pending['key'], 'generation': pending['generation']})
    _write_json_atomic(journal_path, rows)
    return {'reconciled': True, 'status': 'COMPLETED'}


def apply_live_activation_isolated(*, grant, predecessor, runtime_plan, node_allocation,
                                   branch, head, isolated_root, successor_plan_ref,
                                   mode='SIMULATE') -> dict[str, Any]:
    """Materialize native selector artifacts in a disposable root; never enables live execution."""
    if mode != 'SIMULATE':
        raise ValueError('LIVE_ACTIVATION_LIVE_MODE_FORBIDDEN')
    root = Path(isolated_root).expanduser().resolve()
    _live_target_guard(root)
    if not isinstance(predecessor, Mapping) or not isinstance(runtime_plan, Mapping) or not isinstance(node_allocation, Mapping):
        raise ValueError('LIVE_ACTIVATION_BINDING_INVALID')
    if (not isinstance(successor_plan_ref, str) or not successor_plan_ref.strip()
            or Path(successor_plan_ref).is_absolute() or PurePosixPath(successor_plan_ref).is_absolute()
            or PureWindowsPath(successor_plan_ref).is_absolute() or PureWindowsPath(successor_plan_ref).drive
            or '..' in PurePosixPath(successor_plan_ref).parts
            or '..' in PureWindowsPath(successor_plan_ref).parts):
        raise ValueError('SUCCESSOR_PLAN_REF_INVALID')
    if (successor_plan_ref == _R3_PREDECESSOR_PLAN_REF
            or successor_plan_ref == predecessor.get('runtime_plan_ref')):
        raise ValueError('SUCCESSOR_PLAN_MUST_DIFFER_FROM_PREDECESSOR')
    plan_bytes = (json.dumps(dict(runtime_plan), sort_keys=True, indent=2, ensure_ascii=False) + chr(10)).encode()
    plan_digest = 'sha256:' + hashlib.sha256(plan_bytes).hexdigest()
    if plan_digest == predecessor.get('runtime_plan_digest'):
        raise ValueError('SUCCESSOR_PLAN_MUST_DIFFER_FROM_PREDECESSOR')
    grant_digest = _validate_activation_grant(grant, predecessor, runtime_plan, node_allocation, branch, head)
    root.mkdir(parents=True, exist_ok=True)
    paths = _live_activation_paths(root)
    ref = successor_plan_ref
    allocation_id = node_allocation.get('node_allocation_id') or node_allocation.get('allocation_id')
    allocation_digest = node_allocation.get('content_digest') or node_allocation.get('digest')
    if isinstance(allocation_digest, Mapping):
        allocation_digest = allocation_digest.get('value')
    db_path = paths['database']
    generation = _live_db_generation(db_path, ref) + 1
    key = _digest({'grant_digest': grant_digest, 'predecessor': _digest(predecessor),
                   'plan_digest': plan_digest, 'allocation_id': allocation_id,
                   'allocation_digest': allocation_digest, 'branch': branch, 'head': head})
    journal_path = paths['journal']
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else []
    if any(row.get('phase') == 'COMMIT' and row.get('key') == key for row in journal):
        return {'accepted': True, 'executed': False, 'mode': mode, 'applied_effects': [],
                'already_applied': True, 'receipt_ref': str(paths['record']),
                'selector_readback': _state_read(paths['selector']),
                'resolve_readback': verify_live_activation_isolated(root),
                'authority_granted': False, 'typed_ce_admitted': False,
                'live_target_touched': False, 'mode_available': ['SIMULATE']}
    source_repo = Path(__file__).resolve().parents[2]
    route_path = source_repo / ROUTE_REF
    route = json.loads(route_path.read_text()) if route_path.exists() else {'schema_id':'gwc.engineering-coordination-route/v1'}
    route['approved_successor_g1'] = {**route.get('approved_successor_g1', {}),
                                      'successor_plan_ref': ref, 'activation_status': 'ACTIVATED'}
    stamp = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
    checkpoint_receipt = _digest({'key': key, 'generation': generation, 'plan_digest': plan_digest})
    receipt = {'schema_id':'gwc.q0.plan-activation/v1', 'plan_ref':ref, 'plan_digest':plan_digest,
               'node_allocation_id':allocation_id, 'node_allocation_digest':allocation_digest,
               'generation':generation, 'activation_status':'ACTIVATED',
               'predecessor_identity':predecessor.get('run_id') or predecessor.get('identity'),
               'predecessor_plan_digest':predecessor.get('runtime_plan_digest'),
               'predecessor_context_digest':_digest(predecessor), 'grant_digest':grant_digest,
               'checkpoint_receipt_digest':checkpoint_receipt,
               'checkpoint_ref':str(db_path), 'activated_at':stamp,
               'branch':branch, 'head':head}
    receipt['receipt_digest'] = _digest(receipt)
    selector = {'active_plan_ref':ref, 'activation_status':'ACTIVATED', 'generation':generation}
    checkpoint = {'plan_ref':ref, 'plan_digest':plan_digest, 'generation':generation,
                  'checkpoint_receipt_digest':checkpoint_receipt}
    cursor = {'plan_ref':ref, 'generation':generation}
    files = {ROUTE_REF: (json.dumps(route, sort_keys=True, indent=2, ensure_ascii=False)+'\n').encode().hex(),
             ref: plan_bytes.hex(), ACTIVATION_RECEIPT_REF:(json.dumps(receipt,sort_keys=True,indent=2,ensure_ascii=False)+'\n').encode().hex(),
             'selector.json':(json.dumps(selector,sort_keys=True,indent=2)+'\n').encode().hex(),
             'checkpoint.json':(json.dumps(checkpoint,sort_keys=True,indent=2)+'\n').encode().hex(),
             'cursor.json':(json.dumps(cursor,sort_keys=True,indent=2)+'\n').encode().hex()}
    journal.append({'phase':'PREPARE','key':key,'files':files,'plan_ref':ref,'plan_digest':plan_digest,
                    'generation':generation,'receipt':receipt,'activated_at':stamp})
    _write_json_atomic(journal_path, journal)
    reconcile_live_activation_journal(root)
    return {'accepted':True, 'executed':False, 'mode':mode,
            'applied_effects':['route_write','activation_record_write','activation_row_insert','selector_copy','checkpoint_copy','cursor_copy'],
            'already_applied':False,'receipt_ref':str(paths['record']),
            'selector_readback':_state_read(paths['selector']),
            'resolve_readback':verify_live_activation_isolated(root),
            'authority_granted':False,'typed_ce_admitted':False,
            'live_target_touched':False,'mode_available':['SIMULATE']}


def verify_live_activation_isolated(isolated_root: Path | str) -> dict[str, Any]:
    """Resolve native activation from disk using a fresh SQLite connection."""
    root = Path(isolated_root).expanduser().resolve()
    resolved = resolve_active_plan(root)
    receipt = json.loads((root / ACTIVATION_RECEIPT_REF).read_text('utf-8'))
    import sqlite3
    db_path = Path(receipt['checkpoint_ref'])
    with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as db:
        row = db.execute('SELECT generation FROM engineering_plan_activation WHERE plan_ref=?',
                         (resolved,)).fetchone()
    if row is None:
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    return {'resolved_plan_ref':resolved,'generation':int(row[0]),
            'activation_status':receipt.get('activation_status')}


def prepare_successor_activation(envelope: Mapping[str, Any], *, authority: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate a live-activation envelope and return a non-executing preflight."""

    effects = envelope.get('effects') if isinstance(envelope, Mapping) else None
    if (not isinstance(envelope, Mapping)
            or envelope.get('kind') != 'LIVE_ACTIVATION_EFFECT_ENVELOPE'
            or not envelope.get('schema_id')
            or envelope.get('executed') is not False
            or envelope.get('authority_granted') is not False
            or not isinstance(effects, list) or not effects
            or any(not isinstance(item, Mapping)
                   or not isinstance(item.get('effect'), str)
                   or not item.get('effect').strip() for item in effects)):
        raise ValueError('LIVE_ACTIVATION_ENVELOPE_INVALID')
    if (not isinstance(authority, Mapping)
            or authority.get('granted') is not True
            or authority.get('authority_kind') != 'SEPARATE_HUMAN_OR_CONTROLLER_GRANT'
            or not authority.get('grant_ref')):
        raise ValueError('LIVE_ACTIVATION_AUTHORITY_REQUIRED')
    return {
        'accepted': True,
        'executed': False,
        'effects': [item['effect'] for item in effects],
        'authority_ref': authority['grant_ref'],
        'next_step': 'LIVE_ACTIVATION_EXECUTION_NOT_IMPLEMENTED',
    }


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_active_plan(root: Path | str) -> str:
    """Resolve the active RuntimePlan with fail-closed activation semantics.

    - No approved successor: the lane stays on R2.
    - Approved successor still PENDING: raise Q0_PLAN_ACTIVATION_PENDING instead of
      silently executing the old acceptance target.
    - ACTIVATED: require the durable activation receipt, the plan file at the
      working tree, and matching digests; otherwise Q0_PLAN_ACTIVATION_INVALID.
    - The receipt binds the plan digest at activation time, not the current HEAD,
      so later additive commits do not invalidate activation.
    """
    root = Path(root).resolve()
    route_path = root / ROUTE_REF
    if not route_path.exists():
        return PLAN_REF
    route = json.loads(route_path.read_text())
    successor = route.get('approved_successor_g1') or {}
    if not successor:
        return PLAN_REF
    status = successor.get('activation_status')
    ref = successor.get('successor_plan_ref')
    if status != 'ACTIVATED':
        raise ValueError('Q0_PLAN_ACTIVATION_PENDING')
    if not ref:
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    plan_path = root / ref
    if not plan_path.exists():
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    receipt_path = root / ACTIVATION_RECEIPT_REF
    if not receipt_path.exists():
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get('plan_ref') != ref or
            receipt.get('plan_digest') != _sha256_file(plan_path) or
            not receipt.get('checkpoint_receipt_digest')):
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    checkpoint_ref = receipt.get('checkpoint_ref')
    if not checkpoint_ref:
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    checkpoint_path = Path(checkpoint_ref)
    if not checkpoint_path.is_absolute():
        checkpoint_path = root / checkpoint_ref
    if not checkpoint_path.exists():
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    import sqlite3
    with sqlite3.connect('file:' + str(checkpoint_path) + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT plan_digest,generation FROM engineering_plan_activation WHERE plan_ref=?',
                         (ref,)).fetchone()
    if row is None or row[0] != receipt['plan_digest'] or int(row[1]) < 1:
        raise ValueError('Q0_PLAN_ACTIVATION_INVALID')
    return ref


FRONTIER_R2_REF = 'core/node-architect/q0-engineering-frontier-r1.json'
FRONTIER_R3_REF = 'core/node-architect/q0-controlled-failure-frontier-r3.json'
FRONTIER_NATIVE_SUCCESSOR_REF = 'core/node-architect/q0-native-successor-frontier-r1.json'


def resolve_frontier_ref(root: Path | str) -> str:
    """Prefer a successor-specific frontier only when bound to the active plan."""
    root = Path(root).resolve()
    plan = resolve_active_plan(root)
    successor_path = root / FRONTIER_NATIVE_SUCCESSOR_REF
    if successor_path.exists():
        policy = json.loads(successor_path.read_text())
        if policy.get('runtime_plan_ref') != plan:
            raise ValueError('Q0_FRONTIER_PLAN_DRIFT')
        return FRONTIER_NATIVE_SUCCESSOR_REF
    ref = FRONTIER_R3_REF if 'controlled-failure' in plan else FRONTIER_R2_REF
    path = root / ref
    if not path.exists():
        raise ValueError('Q0_FRONTIER_SOURCE_MISSING')
    policy = json.loads(path.read_text())
    if policy.get('runtime_plan_ref') != plan:
        raise ValueError('Q0_FRONTIER_PLAN_DRIFT')
    return ref


def build_q0_operation(root: Path | str, *, activity_id: str) -> tuple[dict, dict]:
    root = Path(root).resolve()
    if not activity_id or any(char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for char in activity_id):
        raise ValueError('ACTIVITY_ID_INVALID')
    head = _git(root, 'rev-parse', 'HEAD')
    plan_ref = resolve_active_plan(root)
    source = subprocess.check_output(['git', '-C', str(root), 'show', f'{head}:{plan_ref}'])
    if (root / plan_ref).read_bytes() != source:
        raise ValueError('Q0_PLAN_SOURCE_DRIFT')
    plan = json.loads(source)
    branch = _git(root, 'branch', '--show-current')
    if plan.get('runtime_epoch') != 'UNIVERSAL_V2_DEVELOPMENT' or plan.get('parent_task') != 'SCRUM-781':
        raise ValueError('Q0_PLAN_IDENTITY_INVALID')
    if branch != plan['branch'] or not branch.startswith('fix/SCRUM-781-q0-') or not plan['run_id'].startswith('scrum781-q0-'):
        raise ValueError('Q0_WORKTREE_BINDING_MISMATCH')
    if plan.get('source_repo') != 'nhatnguyenquang1838-coder/gwc':
        raise ValueError('Q0_REPOSITORY_BINDING_MISMATCH')
    binding = {
        'task_id': plan['parent_task'], 'repository': plan['source_repo'],
        'run_id': plan['run_id'], 'base_sha': head, 'working_branch': branch,
        'scope_hash': _digest(plan['scope']),
        'runtime_plan_digest': 'sha256:' + hashlib.sha256(source).hexdigest(),
        'authorized_actions': [], 'authorized_paths': [],
    }
    operation = {key: value for key, value in binding.items() if key not in ('authorized_actions', 'authorized_paths')}
    operation.update(head_sha=head, activity_id=activity_id,
                     operation_id=f"{plan['run_id']}:{activity_id}",
                     protocol_version='dw.taskcontroller.continuation/v1',
                     continuation_ref='', cursor={})
    return operation, binding


def observe_q0(root: Path | str, *, activity_id: str, state_path: Path | str) -> dict:
    """Run the real library with no admitted observer, retaining same-run state.

    This source/readiness probe is not a native firing, RunState, NodeAllocation,
    gate receipt, original incident replay, observer qualification or authority.
    """
    from .m1_m7_agent_workflow import load_m1_m7_contracts, build_m1_m7_graph, WorkflowState
    from .checkpoint_store import CheckpointInput, load_store, persist_to_file, replay_checkpoint, validate_readback
    operation, binding = build_q0_operation(root, activity_id=activity_id)
    manifest, profile = load_m1_m7_contracts(root)
    graph = build_m1_m7_graph(workflow_manifest=manifest, runtime_profile=profile,
                             activity_source_sha256=manifest['source_sha256'], execution_binding=binding)
    path = Path(state_path)
    store = load_store(path)
    node_id = 'scrum841-m1-m7-workflow'
    prior = replay_checkpoint(store, operation['task_id'], operation['run_id'], node_id)
    initial: WorkflowState = {'operation_envelope': operation, 'inputs': {'observer_qualified': False},
               'authority_granted': False, 'executed_effects': []}
    if prior:
        for key, value in {'repository': operation['repository'], 'branch': operation['working_branch'],
                           'base_sha': operation['base_sha'], 'head_sha': operation['head_sha'],
                           'scope_hash': operation['scope_hash']}.items():
            if prior.get(key) != value:
                raise ValueError('Q0_CHECKPOINT_SOURCE_DRIFT_REQUIRES_RECONCILIATION')
        state = prior.get('state', {})
        if state.get('current_activity') != 'M1' or state.get('reason_code') != 'OBSERVER_UNQUALIFIED' or state.get('executed_effects'):
            raise ValueError('Q0_CHECKPOINT_PRIOR_OPERATION_UNSETTLED')
        if state.get('operation_id') == operation['operation_id']:
            initial['checkpoint_projection'] = state
    raw = graph.invoke(initial)
    projection = {**operation, 'current_activity': raw['current_activity'],
                  'status': raw['status'], 'reason_code': raw['reason_code'],
                  'activity_results': raw.get('activity_results', {}), 'executed_effects': []}
    item = CheckpointInput(task_id=operation['task_id'], run_id=operation['run_id'], node_id=node_id,
                           repository=operation['repository'], branch=operation['working_branch'],
                           base_sha=operation['base_sha'], head_sha=operation['head_sha'], scope_hash=operation['scope_hash'],
                           state=projection, expected_revision=int(store.get('revision', 0)), graph_revision=manifest['workflow_id'])
    # Identical replay does not mint another revision.
    if not prior or prior.get('state') != projection:
        persist_to_file(path, item)
    readback = validate_readback(load_store(path), item)
    return {'operation': operation, 'verdict': {key: raw[key] for key in ('status', 'reason_code', 'current_activity')},
            'checkpoint_readback': readback, 'native_activation_permitted': False,
            'native_admission': 'C_E_LOOP_ACTIVATION_BLOCKED', 'authority_granted': False,
            'executed_effects': [], 'evidence_class': 'SOURCE_BOUND_READINESS_NOT_LIVE_QUALIFICATION'}
