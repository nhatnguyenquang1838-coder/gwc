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


_LIVE_EXECUTOR_JOURNAL = 'live-activation-executor-journal.json'
_LIVE_EXECUTOR_LEASE = '.live-activation-executor-lease.json'


def read_live_activation_receipt(live_root: Path | str) -> dict[str, Any] | None:
    root = Path(live_root).expanduser().resolve()
    _live_target_guard(root)
    path = root / ACTIVATION_RECEIPT_REF
    if not path.is_file():
        return None
    receipt = json.loads(path.read_text('utf-8'))
    body = {key: value for key, value in receipt.items() if key != 'receipt_digest'}
    if receipt.get('receipt_digest') != _digest(body):
        raise ValueError('LIVE_ACTIVATION_RECEIPT_INVALID')
    return receipt


def _executor_validate(authority, predecessor, successor_plan, successor_plan_ref,
                       node_allocation, branch, head):
    import sqlite3, time
    from .universal_run_plan import _sha256_digest
    if authority is None:
        raise ValueError('LIVE_ACTIVATION_AUTHORITY_REQUIRED')
    if not isinstance(authority, Mapping) or authority.get('authority_kind') != 'HUMAN_OPERATOR_EFFECT_AUTHORITY':
        raise ValueError('EFFECT_AUTHORITY_KIND_INVALID')
    if any(not isinstance(authority.get(k), str) or not authority[k].strip()
           for k in ('actor', 'authority_ref', 'issued_at', 'expires_at')):
        raise ValueError('EFFECT_AUTHORITY_IDENTITY_REQUIRED')
    try:
        issued, expires = _iso_utc(authority['issued_at']), _iso_utc(authority['expires_at'])
    except ValueError as exc:
        raise ValueError('EFFECT_AUTHORITY_EXPIRED') from exc
    if issued > time.time() or expires <= time.time() or expires <= issued:
        raise ValueError('EFFECT_AUTHORITY_EXPIRED')
    if not isinstance(authority.get('scope'), (list, tuple, set)) or 'q0.live_activation.execute' not in authority['scope']:
        raise ValueError('EFFECT_AUTHORITY_SCOPE_INVALID')
    if not all(isinstance(v, Mapping) for v in (predecessor, successor_plan, node_allocation)):
        raise ValueError('LIVE_ACTIVATION_BINDING_INVALID')
    ref = successor_plan_ref
    if (not isinstance(ref, str) or not ref.strip() or Path(ref).is_absolute()
        or PurePosixPath(ref).is_absolute() or PureWindowsPath(ref).is_absolute()
        or PureWindowsPath(ref).drive or '..' in PurePosixPath(ref).parts
        or '..' in PureWindowsPath(ref).parts):
        raise ValueError('SUCCESSOR_PLAN_REF_INVALID')
    if ref == _R3_PREDECESSOR_PLAN_REF or ref == predecessor.get('runtime_plan_ref'):
        raise ValueError('SUCCESSOR_PLAN_MUST_DIFFER_FROM_PREDECESSOR')
    body = {k: v for k, v in successor_plan.items() if k != 'digest'}
    plan_digest = _sha256_digest(body)
    if successor_plan.get('digest') != plan_digest:
        raise ValueError('SUCCESSOR_PLAN_DIGEST_MISMATCH')
    repo = Path(__file__).resolve().parents[2]
    if _git(repo, 'rev-parse', 'HEAD') != head:
        raise ValueError('SOURCE_HEAD_DRIFT')
    checkpoint = predecessor.get('checkpoint_ref')
    if not isinstance(checkpoint, str) or not Path(checkpoint).is_file():
        raise ValueError('PREDECESSOR_CHECKPOINT_UNBOUND')
    run_id, context = predecessor.get('run_id'), predecessor.get('context_digest')
    if not isinstance(run_id, str) or not isinstance(context, str):
        raise ValueError('PREDECESSOR_CHECKPOINT_UNBOUND')
    try:
        with sqlite3.connect(Path(checkpoint).resolve().as_uri() + '?mode=ro', uri=True) as db:
            row = db.execute('SELECT context_digest FROM engineering_workflow WHERE run=?', (run_id,)).fetchone()
    except (sqlite3.Error, OSError) as exc:
        raise ValueError('PREDECESSOR_CHECKPOINT_UNBOUND') from exc
    if row is None or row[0] != context:
        raise ValueError('PREDECESSOR_CONTEXT_MISMATCH')
    alloc_digest = node_allocation.get('content_digest')
    if isinstance(alloc_digest, Mapping):
        alloc_digest = alloc_digest.get('value')
    if not alloc_digest:
        alloc_digest = node_allocation.get('digest')
    expected = {'predecessor_context_digest': context, 'successor_plan_digest': plan_digest,
                'node_allocation_digest': alloc_digest, 'branch': branch, 'head': head}
    bindings = authority.get('bindings')
    if not isinstance(bindings, Mapping) or any(bindings.get(k) != v for k, v in expected.items()):
        raise ValueError('EFFECT_AUTHORITY_BINDING_MISMATCH')
    return _digest(dict(authority)), plan_digest, _digest(dict(predecessor))


def _executor_bytes(path: Path):
    return path.read_bytes() if path.is_file() else None


def _executor_write(path: Path, content):
    if content is None:
        if path.is_file():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.activation-tmp')
    temp.write_bytes(content)
    temp.replace(path)


def _executor_rows(root: Path):
    path = root / _LIVE_EXECUTOR_JOURNAL
    if not path.exists():
        return []
    rows = json.loads(path.read_text('utf-8'))
    if not isinstance(rows, list):
        raise ValueError('LIVE_ACTIVATION_JOURNAL_INVALID')
    return rows


def _executor_apply(root: Path, prepare: Mapping[str, Any], *, rollback: bool):
    states = prepare['files']
    for rel, state in states.items():
        current = _executor_bytes(root / rel)
        current_hex = None if current is None else current.hex()
        if current_hex not in (state['before'], state['after']):
            raise ValueError('CAS_CONFLICT')
    effects = reversed(_ACTIVATION_EFFECTS) if rollback else _ACTIVATION_EFFECTS
    for effect in effects:
        for rel in prepare['effects'][effect]:
            content = states[rel]['before' if rollback else 'after']
            _executor_write(root / rel, None if content is None else bytes.fromhex(content))
            if _executor_bytes(root / rel) != (None if content is None else bytes.fromhex(content)):
                raise ValueError('CAS_CONFLICT')


def _reconcile_executor_live_activation_journal(live_root: Path | str) -> dict[str, Any]:
    root = Path(live_root).expanduser().resolve()
    _live_target_guard(root)
    rows = _executor_rows(root)
    done = {r.get('key') for r in rows if r.get('phase') in ('COMMIT', 'ROLLBACK_APPLIED')}
    pending = next((r for r in reversed(rows) if r.get('phase') == 'PREPARE' and r.get('key') not in done), None)
    if pending is None:
        return {'reconciled': False, 'status': 'NO_PENDING_PREPARE'}
    try:
        _executor_apply(root, pending, rollback=False)
    except ValueError as exc:
        if str(exc) != 'CAS_CONFLICT':
            raise
        _executor_apply(root, pending, rollback=True)
        rows.append({'phase': 'ROLLBACK_APPLIED', 'key': pending['key'], 'reason': 'CAS_CONFLICT'})
        _write_json_atomic(root / _LIVE_EXECUTOR_JOURNAL, rows)
        return {'reconciled': True, 'status': 'ROLLED_BACK'}
    rows.append({'phase': 'COMMIT', 'key': pending['key'], 'recovered': True})
    _write_json_atomic(root / _LIVE_EXECUTOR_JOURNAL, rows)
    resolve_active_plan(root)
    return {'reconciled': True, 'status': 'COMPLETED'}


def rollback_live_activation(live_root: Path | str) -> dict[str, Any]:
    root = Path(live_root).expanduser().resolve()
    _live_target_guard(root)
    rows = _executor_rows(root)
    rolled = {r.get('key') for r in rows if r.get('phase') == 'ROLLBACK_APPLIED'}
    commit = next((r for r in reversed(rows) if r.get('phase') == 'COMMIT' and r.get('key') not in rolled), None)
    if commit is None:
        return {'rolled_back': False, 'status': 'NO_ACTIVATION'}
    prepare = next(r for r in reversed(rows) if r.get('phase') == 'PREPARE' and r.get('key') == commit['key'])
    _executor_apply(root, prepare, rollback=True)
    rows.append({'phase': 'ROLLBACK_APPLIED', 'key': commit['key'], 'reason': 'EXPLICIT_ROLLBACK'})
    _write_json_atomic(root / _LIVE_EXECUTOR_JOURNAL, rows)
    return {'rolled_back': True, 'status': 'ROLLED_BACK'}


def execute_live_activation(*, authority, predecessor, successor_plan, successor_plan_ref,
                            node_allocation, branch, head, live_root, mode='PREFLIGHT') -> dict[str, Any]:
    """Execute authority-bound effects only inside an isolated live_root; SIMULATE is untouched."""
    if mode not in ('PREFLIGHT', 'COMMIT'):
        raise ValueError('LIVE_ACTIVATION_MODE_INVALID')
    root = Path(live_root).expanduser().resolve()
    _live_target_guard(root)
    auth_digest, plan_digest, predecessor_digest = _executor_validate(
        authority, predecessor, successor_plan, successor_plan_ref, node_allocation, branch, head)
    paths = _live_activation_paths(root)
    paths['plan'] = root / successor_plan_ref
    for path in paths.values():
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('LIVE_ACTIVATION_LIVE_TARGET_FORBIDDEN')
    key = _digest({'authority_digest': auth_digest, 'predecessor_digest': predecessor_digest,
                   'plan_digest': plan_digest, 'plan_ref': successor_plan_ref,
                   'allocation': dict(node_allocation), 'branch': branch, 'head': head})
    if mode == 'PREFLIGHT':
        return {'accepted': True, 'executed': False, 'mode': mode, 'applied_effects': [],
                'already_applied': False, 'activation_receipt_ref': str(paths['record']),
                'resolve_readback': None, 'authority_granted': False, 'typed_ce_admitted': False,
                'live_target': str(root)}
    root.mkdir(parents=True, exist_ok=True)
    owner = _lease_acquire(root)
    try:
        rows = _executor_rows(root)
        if any(r.get('phase') == 'COMMIT' and r.get('key') == key for r in rows):
            return {'accepted': True, 'executed': False, 'mode': mode, 'applied_effects': [],
                    'already_applied': True, 'activation_receipt_ref': str(paths['record']),
                    'resolve_readback': verify_live_activation_isolated(root),
                    'authority_granted': False, 'typed_ce_admitted': False, 'live_target': str(root)}
        recovery = reconcile_live_activation_journal(root)
        if recovery['status'] not in ('NO_PENDING_PREPARE', 'COMPLETED', 'ROLLED_BACK'):
            raise ValueError('LIVE_ACTIVATION_RECOVERY_REQUIRED')
        import sqlite3, tempfile
        generation = _live_db_generation(paths['database'], successor_plan_ref) + 1
        raw_plan = (json.dumps(dict(successor_plan), sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode()
        file_digest = 'sha256:' + hashlib.sha256(raw_plan).hexdigest()
        route = json.loads(paths['route'].read_text()) if paths['route'].exists() else {'schema_id': 'gwc.engineering-coordination-route/v1'}
        route['approved_successor_g1'] = {'successor_plan_ref': successor_plan_ref, 'activation_status': 'ACTIVATED'}
        stamp = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        checkpoint_digest = _digest({'key': key, 'generation': generation, 'plan_digest': file_digest})
        receipt_body = {'schema_id': 'gwc.q0.live-activation-executor-receipt.v1', 'plan_ref': successor_plan_ref,
                        'plan_digest': file_digest, 'checkpoint_receipt_digest': checkpoint_digest,
                        'checkpoint_ref': str(paths['database']),
                        'generation': generation, 'predecessor_run_id': predecessor['run_id'],
                        'predecessor_context_digest': predecessor['context_digest'],
                        'successor_run_id': successor_plan.get('run_id'), 'node_allocation': dict(node_allocation),
                        'branch': branch, 'head': head, 'authority_ref': authority['authority_ref'],
                        'authority_digest': auth_digest, 'activated_at': stamp}
        receipt = {**receipt_body, 'receipt_digest': _digest(receipt_body)}
        selector = {'active_plan_ref': successor_plan_ref, 'activation_status': 'ACTIVATED', 'generation': generation}
        checkpoint = {'plan_ref': successor_plan_ref, 'plan_digest': file_digest,
                      'generation': generation, 'checkpoint_receipt_digest': checkpoint_digest}
        cursor = {'plan_ref': successor_plan_ref, 'generation': generation}
        with tempfile.TemporaryDirectory(prefix='q0-live-activation-') as tmp:
            db_tmp = Path(tmp) / 'activation.sqlite3'
            with sqlite3.connect(db_tmp) as db:
                db.execute('CREATE TABLE engineering_plan_activation (plan_ref TEXT PRIMARY KEY, plan_digest TEXT, context_digest TEXT, generation INTEGER, activated_at TEXT)')
                db.execute('INSERT INTO engineering_plan_activation VALUES (?,?,?,?,?)',
                           (successor_plan_ref, file_digest, checkpoint_digest, generation, stamp))
            after = {
                'selector_write': {paths['selector']: json.dumps(selector, sort_keys=True, indent=2).encode() + b'\n'},
                'checkpoint_write': {paths['checkpoint']: json.dumps(checkpoint, sort_keys=True, indent=2).encode() + b'\n',
                                     paths['route']: json.dumps(route, sort_keys=True, indent=2).encode() + b'\n',
                                     paths['plan']: raw_plan,
                                     paths['record']: json.dumps(receipt, sort_keys=True, indent=2).encode() + b'\n',
                                     paths['database']: db_tmp.read_bytes()},
                'cursor_advance': {paths['cursor']: json.dumps(cursor, sort_keys=True, indent=2).encode() + b'\n'},
            }
        files, effects = {}, {effect: [] for effect in _ACTIVATION_EFFECTS}
        for effect, group in after.items():
            for path, content in group.items():
                rel = path.relative_to(root).as_posix()
                old = _executor_bytes(path)
                files[rel] = {'before': None if old is None else old.hex(), 'after': content.hex()}
                effects[effect].append(rel)
        prepare = {'phase': 'PREPARE', 'key': key, 'files': files, 'effects': effects}
        rows.append(prepare)
        _write_json_atomic(root / _LIVE_EXECUTOR_JOURNAL, rows)
        for rel, state in files.items():
            now = _executor_bytes(root / rel)
            if (None if now is None else now.hex()) != state['before']:
                raise ValueError('CAS_CONFLICT')
        for effect in _ACTIVATION_EFFECTS:
            for rel in effects[effect]:
                _executor_write(root / rel, bytes.fromhex(files[rel]['after']))
                actual = _executor_bytes(root / rel)
                if actual is None or hashlib.sha256(actual).hexdigest() != hashlib.sha256(bytes.fromhex(files[rel]['after'])).hexdigest():
                    raise ValueError('CAS_CONFLICT')
        rows.append({'phase': 'COMMIT', 'key': key})
        _write_json_atomic(root / _LIVE_EXECUTOR_JOURNAL, rows)
        read_live_activation_receipt(root)
        readback = verify_live_activation_isolated(root)
        return {'accepted': True, 'executed': True, 'mode': mode, 'applied_effects': list(_ACTIVATION_EFFECTS),
                'already_applied': False, 'activation_receipt_ref': str(paths['record']),
                'resolve_readback': readback, 'authority_granted': False, 'typed_ce_admitted': False,
                'live_target': str(root)}
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


def _reconcile_legacy_live_activation_journal(isolated_root: Path | str) -> dict[str, Any]:
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


def reconcile_live_activation_journal(live_root: Path | str) -> dict[str, Any]:
    """Dispatch journal reconciliation without changing the legacy SIMULATE contract."""
    root = Path(live_root).expanduser().resolve()
    if (root / _LIVE_EXECUTOR_JOURNAL).exists():
        return _reconcile_executor_live_activation_journal(root)
    return _reconcile_legacy_live_activation_journal(root)


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


_REAL_TARGET_AUTHORITY_KIND = 'HUMAN_OPERATOR_EFFECT_AUTHORITY'
_REAL_TARGET_AUTHORITY_SCOPE = 'q0.live_activation.execute'
_REAL_TARGET_PLAN_REF = 'core/node-architect/q0-native-successor-runtime-plan-r2.json'
_R4_TARGET_PLAN_REF = 'core/node-architect/q0-native-successor-runtime-plan-r3-proposal-r2.json'
_R4_NATIVE_PLAN_REF = 'core/node-architect/q0-r4-native-runtime-plan-r1.json'
_R4_ALLOCATION_REF = 'core/node-architect/q0-r4-work-node-allocation-r1.json'
_R4_PLAN_DIGEST = 'sha256:16445abb85d78f61ac6dc2207c47c98240a45c8107e49f546b369e2d90bfa38f'
_R4_PREVIOUS_DIGEST = 'sha256:bdcf4e9c44ea1b5cdeaa464c77446b9e1b66aeec98f2aaa48018564a2eedc0e6'
_R4_ALLOCATION_FILE_DIGEST = 'sha256:65a54ac57973e40c960917b4d84c509bc16cbd16b76be0b5fc11ba194b9b73c8'
_REAL_TARGET_PLAN_REFS = frozenset({_REAL_TARGET_PLAN_REF, _R4_TARGET_PLAN_REF})
# COMMAND #186: a live-activation trusted issuer is an INDEPENDENT Human/operator
# effect grant recorded as a dedicated grant artifact — NEVER a RuntimePlan or a
# standing development-policy document. Those are self-referential artifacts the
# adapter reads; treating them as the Human issuer would let a caller self-author
# live activation by referencing the plan/policy it controls. No such independent
# grant exists in the current canonical governance, so the anchor is UNAVAILABLE
# and live activation fails closed with EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE.
_REAL_TARGET_GRANTS_DIR = 'authority/grants'
_SELF_REFERENTIAL_ISSUER_REFS = frozenset({
    _R4_NATIVE_PLAN_REF, _R4_ALLOCATION_REF, _R3_PREDECESSOR_PLAN_REF, ROUTE_REF, ACTIVATION_RECEIPT_REF,
}) | _REAL_TARGET_PLAN_REFS
_REAL_TARGET_VIEW_REFS = (
    _R3_PREDECESSOR_PLAN_REF,
    ROUTE_REF,
    ACTIVATION_RECEIPT_REF,
)


class RealTargetActivationAdapter:
    """Authority-audited adapter whose target is an isolated real-target snapshot.

    The source tree is read only. Selector/checkpoint/cursor writes, the PREPARE /
    COMMIT journal, rollback and verification are confined to ``live_root``.
    """

    def __init__(self, *, source_root: Path | str, live_root: Path | str):
        self.source_root = Path(source_root).expanduser().resolve()
        self.live_root = Path(live_root).expanduser().resolve()
        _live_target_guard(self.live_root)
        if (self.live_root == self.source_root
                or self.source_root in self.live_root.parents
                or self.live_root in self.source_root.parents):
            raise ValueError('LIVE_ACTIVATION_LIVE_TARGET_FORBIDDEN')

    def _real_target_view(self, successor_plan_ref: str, successor_plan: Mapping[str, Any],
                          predecessor: Mapping[str, Any]) -> dict[str, Any]:
        if successor_plan_ref not in _REAL_TARGET_PLAN_REFS:
            raise ValueError('SUCCESSOR_PLAN_REF_INVALID')
        proposal_path = self.source_root / successor_plan_ref
        if not proposal_path.is_file():
            raise ValueError('REAL_TARGET_SOURCE_ARTIFACT_MISSING')
        proposal = json.loads(proposal_path.read_text('utf-8'))
        if proposal.get('native_runtime_plan') != dict(successor_plan):
            raise ValueError('REAL_TARGET_SUCCESSOR_MISMATCH')
        extra_refs = ()
        if successor_plan_ref == _R4_TARGET_PLAN_REF:
            if (successor_plan.get('digest') != _R4_PLAN_DIGEST
                    or successor_plan.get('previous_digest') != _R4_PREVIOUS_DIGEST
                    or _digest({k: v for k, v in successor_plan.items() if k != 'digest'}) != _R4_PLAN_DIGEST):
                raise ValueError('REAL_TARGET_SUCCESSOR_MISMATCH')
            plan_path = self.source_root / _R4_NATIVE_PLAN_REF
            allocation_path = self.source_root / _R4_ALLOCATION_REF
            if not plan_path.is_file() or not allocation_path.is_file():
                raise ValueError('REAL_TARGET_SOURCE_ARTIFACT_MISSING')
            if (json.loads(plan_path.read_text('utf-8')) != dict(successor_plan)
                    or _sha256_file(allocation_path) != _R4_ALLOCATION_FILE_DIGEST
                    or proposal.get('node_allocation') != json.loads(allocation_path.read_text('utf-8'))):
                raise ValueError('REAL_TARGET_SUCCESSOR_MISMATCH')
            extra_refs = (_R4_NATIVE_PLAN_REF, _R4_ALLOCATION_REF)
        artifacts = {}
        for rel in (successor_plan_ref, *_REAL_TARGET_VIEW_REFS, *extra_refs):
            path = self.source_root / rel
            if path.is_file():
                artifacts[rel] = _sha256_file(path)
        if _R3_PREDECESSOR_PLAN_REF not in artifacts:
            raise ValueError('REAL_TARGET_SOURCE_ARTIFACT_MISSING')
        first_activation = ACTIVATION_RECEIPT_REF not in artifacts
        if first_activation:
            # A prior selector/checkpoint/cursor proves this is not a cold start;
            # continuity must be backed by its durable activation receipt.
            prior_state = any((self.source_root / name).is_file()
                              for name in ('selector.json', 'checkpoint.json', 'cursor.json'))
            if prior_state:
                raise ValueError('REAL_TARGET_RECEIPT_MISSING')
        checkpoint_ref = predecessor.get('checkpoint_ref') if isinstance(predecessor, Mapping) else None
        if not isinstance(checkpoint_ref, str) or not Path(checkpoint_ref).is_file():
            raise ValueError('PREDECESSOR_CHECKPOINT_UNBOUND')
        artifacts['predecessor_checkpoint'] = _sha256_file(Path(checkpoint_ref))
        return {'source_root': str(self.source_root), 'artifacts': artifacts,
                'view_digest': _digest(artifacts), 'first_activation': first_activation}

    def _canonical_issuer(self, issuer_ref: str) -> dict[str, Any]:
        """Resolve an independent Human/operator grant as the trusted issuer.

        COMMAND #186 rejects self-referential plan/policy artifacts as issuers;
        an independent committed grant is required. No such grant exists in the
        current governance, so the trust anchor is UNAVAILABLE and fails closed.
        """
        if issuer_ref in _SELF_REFERENTIAL_ISSUER_REFS:
            raise ValueError('EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE')
        if not issuer_ref.startswith(_REAL_TARGET_GRANTS_DIR + '/'):
            raise ValueError('EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE')
        grant_root = (self.source_root / _REAL_TARGET_GRANTS_DIR).resolve()
        path = (self.source_root / issuer_ref).resolve()
        if ('..' in Path(issuer_ref).parts
                or not grant_root.is_relative_to(self.source_root)
                or not path.is_relative_to(grant_root)):
            raise ValueError('EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE')
        if not path.is_file():
            raise ValueError('EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE')
        try:
            grant = json.loads(path.read_text('utf-8'))
        except (OSError, ValueError) as exc:
            raise ValueError('EFFECT_AUTHORITY_ISSUER_UNREADABLE') from exc
        if (not isinstance(grant, Mapping)
                or grant.get('authority_kind') != _REAL_TARGET_AUTHORITY_KIND):
            raise ValueError('EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE')
        return {'issuer_ref': issuer_ref, 'issuer_digest': _sha256_file(path), 'grant': grant}

    def _verify_trusted_authority_source(self, authority: Mapping[str, Any]) -> dict[str, Any]:
        # Authority must resolve to an independent committed grant artifact; a
        # caller-supplied registry_ref is never consulted.
        issuer_ref = authority.get('issuer_ref')
        if not isinstance(issuer_ref, str) or not issuer_ref.strip():
            raise ValueError('EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE')
        issuer = self._canonical_issuer(issuer_ref)
        grant = issuer['grant']
        if grant.get('issued') is False:
            raise ValueError('EFFECT_AUTHORITY_GRANT_NOT_ISSUED')
        bindings = authority.get('bindings')
        grant_bindings = grant.get('bindings')
        bound_keys = ('predecessor_context_digest', 'successor_plan_digest',
                      'node_allocation_digest', 'branch', 'head',
                      'successor_plan_ref', 'live_target')
        if (not isinstance(bindings, Mapping) or not isinstance(grant_bindings, Mapping)
                or any(bindings.get(k) != grant_bindings.get(k) for k in bound_keys)):
            raise ValueError('EFFECT_AUTHORITY_BINDING_MISMATCH')
        if authority.get('authority_kind') != _REAL_TARGET_AUTHORITY_KIND:
            raise ValueError('EFFECT_AUTHORITY_KIND_INVALID')
        scope = authority.get('scope')
        if (not isinstance(scope, (list, tuple))
                or len(scope) != 1 or scope[0] != _REAL_TARGET_AUTHORITY_SCOPE):
            raise ValueError('REAL_TARGET_AUTHORITY_SCOPE_INVALID')
        separate = grant.get('separate_authority_required')
        if isinstance(separate, (list, tuple)) and _REAL_TARGET_AUTHORITY_SCOPE in separate:
            raise ValueError('EFFECT_AUTHORITY_SCOPE_SEPARATELY_GOVERNED')
        if grant.get('not_a_new_grant') is False and not authority.get('grant_ref'):
            raise ValueError('EFFECT_AUTHORITY_GRANT_REF_REQUIRED')
        return issuer

    def validate_authority(self, *, authority, predecessor, successor_plan, successor_plan_ref,
                           node_allocation, branch, head) -> dict[str, Any]:
        if not isinstance(authority, Mapping):
            raise ValueError('LIVE_ACTIVATION_AUTHORITY_REQUIRED')
        if authority.get('authority_kind') != _REAL_TARGET_AUTHORITY_KIND:
            raise ValueError('EFFECT_AUTHORITY_KIND_INVALID')
        scopes = authority.get('scope')
        if (not isinstance(scopes, (list, tuple))
                or len(scopes) != 1 or scopes[0] != _REAL_TARGET_AUTHORITY_SCOPE):
            raise ValueError('REAL_TARGET_AUTHORITY_SCOPE_INVALID')
        if not isinstance(successor_plan_ref, str) or successor_plan_ref not in _REAL_TARGET_PLAN_REFS:
            raise ValueError('SUCCESSOR_PLAN_REF_INVALID')
        trusted_issuer = self._verify_trusted_authority_source(authority)
        authority_digest, plan_digest, predecessor_digest = _executor_validate(
            authority, predecessor, successor_plan, successor_plan_ref,
            node_allocation, branch, head)
        bindings = authority['bindings']
        if (bindings.get('successor_plan_ref') != successor_plan_ref
                or bindings.get('live_target') != str(self.live_root)):
            raise ValueError('EFFECT_AUTHORITY_BINDING_MISMATCH')
        if successor_plan_ref == _R4_TARGET_PLAN_REF:
            if trusted_issuer['grant'].get('issued') is not True:
                raise ValueError('EFFECT_AUTHORITY_GRANT_NOT_ISSUED')
            allocation_path = self.source_root / _R4_ALLOCATION_REF
            if not allocation_path.is_file():
                raise ValueError('REAL_TARGET_SOURCE_ARTIFACT_MISSING')
            if json.loads(allocation_path.read_text('utf-8')) != dict(node_allocation):
                raise ValueError('EFFECT_AUTHORITY_BINDING_MISMATCH')
        return {'verified': True, 'authority_kind': _REAL_TARGET_AUTHORITY_KIND,
                'scope': _REAL_TARGET_AUTHORITY_SCOPE, 'authority_digest': authority_digest,
                'successor_plan_digest': plan_digest,
                'predecessor_digest': predecessor_digest,
                'trusted_issuer_ref': trusted_issuer['issuer_ref'],
                'trusted_issuer_digest': trusted_issuer['issuer_digest'],
                'checkpoint_context_digest': predecessor['context_digest'],
                'branch': branch, 'head': head}

    def transition(self, *, authority, predecessor, successor_plan, successor_plan_ref,
                   node_allocation, branch, head, mode='PREFLIGHT') -> dict[str, Any]:
        authority_check = self.validate_authority(
            authority=authority, predecessor=predecessor, successor_plan=successor_plan,
            successor_plan_ref=successor_plan_ref, node_allocation=node_allocation,
            branch=branch, head=head)
        view = self._real_target_view(successor_plan_ref, successor_plan, predecessor)
        result = execute_live_activation(
            authority=authority, predecessor=predecessor, successor_plan=successor_plan,
            successor_plan_ref=successor_plan_ref, node_allocation=node_allocation,
            branch=branch, head=head, live_root=self.live_root, mode=mode)
        result['authority_verification'] = authority_check
        result['real_target_view'] = view
        result['first_activation'] = view['first_activation']
        if mode == 'COMMIT' and result.get('executed'):
            receipt = read_live_activation_receipt(self.live_root)
            if receipt is None:
                raise ValueError('REAL_TARGET_RECEIPT_MISSING')
            result['independent_verification'] = verify_real_target_transition(
                self.live_root, expected_receipt=receipt)
        return result

    def preflight(self, **kwargs) -> dict[str, Any]:
        return self.transition(**kwargs, mode='PREFLIGHT')

    def commit(self, **kwargs) -> dict[str, Any]:
        return self.transition(**kwargs, mode='COMMIT')


def verify_real_target_transition(live_root: Path | str, *, expected_receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Independently verify isolated selector/checkpoint/cursor and generation."""
    root = Path(live_root).expanduser().resolve()
    _live_target_guard(root)
    if not isinstance(expected_receipt, Mapping):
        raise ValueError('REAL_TARGET_EXPECTED_RECEIPT_REQUIRED')
    actual = read_live_activation_receipt(root)
    if actual is None or actual.get('receipt_digest') != expected_receipt.get('receipt_digest'):
        raise ValueError('REAL_TARGET_RECEIPT_MISMATCH')
    readback = verify_live_activation_isolated(root)
    ref, generation = actual.get('plan_ref'), actual.get('generation')
    selector = _state_read(root / 'selector.json')
    checkpoint = _state_read(root / 'checkpoint.json')
    cursor = _state_read(root / 'cursor.json')
    for artifact in (selector, checkpoint, cursor):
        if not isinstance(artifact, Mapping) or artifact.get('plan_ref', artifact.get('active_plan_ref')) != ref:
            raise ValueError('REAL_TARGET_ARTIFACT_MISMATCH')
        if artifact.get('generation') != generation:
            raise ValueError('REAL_TARGET_GENERATION_MISMATCH')
    if readback.get('resolved_plan_ref') != ref or readback.get('generation') != generation:
        raise ValueError('REAL_TARGET_READBACK_MISMATCH')
    return {'verified': True, 'plan_ref': ref, 'generation': generation,
            'artifact_digests': {name: _sha256_file(root / f'{name}.json')
                                 for name in ('selector', 'checkpoint', 'cursor')}}


def rollback_real_target_activation(live_root: Path | str) -> dict[str, Any]:
    root = Path(live_root).expanduser().resolve()
    _live_target_guard(root)
    return rollback_live_activation(root)


def reconcile_real_target_activation_journal(live_root: Path | str) -> dict[str, Any]:
    root = Path(live_root).expanduser().resolve()
    _live_target_guard(root)
    return reconcile_live_activation_journal(root)


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
