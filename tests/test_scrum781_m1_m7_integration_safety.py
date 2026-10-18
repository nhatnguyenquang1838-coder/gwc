"""Native integration safety regressions, independent of live scheduler state."""
import pytest
from tools.node_architect import loop_settlement_reconciler as module


def test_workflow_can_observe_q0_with_separate_non_authorizing_binding():
    from pathlib import Path
    from tools.node_architect.m1_m7_agent_workflow import load_m1_m7_contracts, build_m1_m7_graph
    root = Path(__file__).resolve().parents[1]
    manifest, library_profile = load_m1_m7_contracts(root)
    original = dict(library_profile)
    binding = {**library_profile, 'task_id': 'SCRUM-781', 'working_branch': 'fix/SCRUM-781-q0-test', 'run_id': 'scrum781-q0-test', 'authorized_actions': [], 'authorized_paths': []}
    operation = {key: binding[key] for key in ('task_id', 'repository', 'base_sha', 'working_branch', 'scope_hash', 'runtime_plan_digest', 'run_id')}
    operation.update(head_sha=binding['base_sha'], operation_id='q0-tick-1', activity_id='tick-1', protocol_version='dw.taskcontroller.continuation/v1', continuation_ref='', cursor={})
    graph = build_m1_m7_graph(workflow_manifest=manifest, runtime_profile=library_profile, activity_source_sha256=manifest['source_sha256'], execution_binding=binding)
    result = graph.invoke({'operation_envelope': operation, 'inputs': {'observer_qualified': False}})
    assert result['reason_code'] == 'OBSERVER_UNQUALIFIED'
    assert result['authority_granted'] is False
    assert result['executed_effects'] == []
    assert library_profile == original


def test_next_tick_same_run_does_not_drift_when_prior_has_no_effects(tmp_path):
    import shutil
    from pathlib import Path
    from tools.node_architect.loop_scheduled_operation_harness import emit_operation_envelope, invoke_or_resume
    source = Path(__file__).resolve().parents[1]
    root = tmp_path / 'repo'
    for name in ('scrum841-m1-m7-agent-workflow-r1', 'scrum841-m1-m7-runtime-profile-r1'):
        for rel in (f'core/node-architect/{name}.json', f'schemas/node-architect/{name.replace("-r1", "")}.schema.json'):
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / rel, target)
    run = 'run-two-real-ticks'
    ref = f'.gwc/tasks/SCRUM-842/g2/checkpoints/{run}.json'
    first = invoke_or_resume(root, operation_envelope=emit_operation_envelope(root, run_id=run, tick=1), inputs={'observer_qualified': False}, checkpoint_store_ref=ref, checkpoint_expected_revision=0)
    second = invoke_or_resume(root, operation_envelope=emit_operation_envelope(root, run_id=run, tick=2), inputs={'observer_qualified': False}, checkpoint_store_ref=ref, checkpoint_expected_revision=1)
    assert first['verdict']['reason_code'] == 'OBSERVER_UNQUALIFIED'
    assert second['verdict']['reason_code'] == 'OBSERVER_UNQUALIFIED'
    assert second['checkpoint_projection']['activity_id'] == 'tick-2'
    assert second['checkpoint_persistence']['revision'] == 2


def test_concurrent_settlers_cannot_both_enter_before_intent_is_written(tmp_path, monkeypatch):
    import threading
    ledger = tmp_path / 'concurrent.json'
    entered, release = threading.Event(), threading.Event()
    original = module._write_ledger
    calls, errors = [], []
    request = {'idempotency_key': 'one-real-firing'}
    def delayed(path, payload):
        if threading.current_thread().name == 'first-settler' and not entered.is_set():
            entered.set()
            assert release.wait(5)
        return original(path, payload)
    def native(req):
        calls.append(req)
        return {'status': 'VERIFIED', 'settled': True}
    def first():
        try:
            module.LoopSettlementReconciler(ledger).settle_exactly_once(request, native)
        except BaseException as exc:
            errors.append(exc)
    monkeypatch.setattr(module, '_write_ledger', delayed)
    thread = threading.Thread(target=first, name='first-settler')
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(module.SettlementReconcilerError, match='BUSY'):
            module.LoopSettlementReconciler(ledger).settle_exactly_once(request, native)
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert not errors
    assert len(calls) == 1


def test_newly_emitted_request_keys_are_persisted(tmp_path):
    from test_loop_scheduled_operation_harness import _sandbox_root, _m5_inputs
    from tools.node_architect.loop_scheduled_operation_harness import emit_operation_envelope, invoke_or_resume
    root = _sandbox_root(tmp_path)
    run = 'run-persist-new-requests'
    envelope = emit_operation_envelope(root, run_id=run, tick=1)
    result = invoke_or_resume(root, operation_envelope=envelope, inputs=_m5_inputs(envelope), checkpoint_store_ref=f'.gwc/tasks/SCRUM-842/g2/checkpoints/{run}.json', checkpoint_expected_revision=0)
    assert result['settlement_requests']
    for state_key, projection_key in (('host_action_requests', 'idempotency_keys'), ('controller_exchange_requests', 'controller_exchange_idempotency_keys'), ('settlement_requests', 'settlement_idempotency_keys')):
        assert {item['idempotency_key'] for item in result[state_key]} <= set(result['checkpoint_projection'][projection_key])


def test_intent_write_is_fsynced_before_callback(tmp_path, monkeypatch):
    calls = []
    original = module.os.fsync
    def sync(fd):
        calls.append(fd)
        return original(fd)
    monkeypatch.setattr(module.os, 'fsync', sync)
    def native(_):
        assert len(calls) >= 2, 'intent file and containing directory must be durable before dispatch'
        return {'status': 'VERIFIED', 'settled': True}
    module.LoopSettlementReconciler(tmp_path/'durable.json').settle_exactly_once({'idempotency_key': 'durable-effect'}, native)


def test_q0_operation_is_bound_to_actual_plan_without_minting_transport_cursor():
    from pathlib import Path
    from tools.node_architect.q0_m1_m7_integration import build_q0_operation
    operation, binding = build_q0_operation(Path(__file__).resolve().parents[1], activity_id='user-readiness')
    assert operation['task_id'] == 'SCRUM-781'
    assert operation['run_id'] == 'scrum781-q0-fresh-20261010-r1'
    assert operation['working_branch'] == 'fix/SCRUM-781-q0-fresh-20261010-r1'
    assert operation['cursor'] == {}
    assert operation['continuation_ref'] == ''
    assert binding['authorized_actions'] == []
    assert binding['authorized_paths'] == []


def test_q0_readiness_executes_real_graph_and_reuses_persistent_run(tmp_path):
    from pathlib import Path
    from tools.node_architect.q0_m1_m7_integration import observe_q0
    root = Path(__file__).resolve().parents[1]
    store = tmp_path / 'graph-checkpoint.json'
    first = observe_q0(root, activity_id='user-readiness-1', state_path=store)
    second = observe_q0(root, activity_id='user-readiness-2', state_path=store)
    assert first['verdict']['reason_code'] == 'OBSERVER_UNQUALIFIED'
    assert second['verdict']['reason_code'] == 'OBSERVER_UNQUALIFIED'
    assert first['operation']['run_id'] == second['operation']['run_id']
    assert first['operation']['task_id'] == 'SCRUM-781'
    assert second['checkpoint_readback']['revision'] == 2
    assert second['native_activation_permitted'] is False
    assert second['executed_effects'] == []


def test_legacy_profile_emitter_cannot_impersonate_q0():
    from pathlib import Path
    from tools.node_architect.loop_scheduled_operation_harness import emit_operation_envelope, HarnessContractError
    with pytest.raises(HarnessContractError, match='Q0_SOURCE_BOUND_ADAPTER_REQUIRED'):
        emit_operation_envelope(Path(__file__).resolve().parents[1], run_id='scrum781-q0-fresh-20261010-r1', tick=89)


def test_native_effect_is_not_retried_after_receipt_write_failure(tmp_path, monkeypatch):
    ledger = tmp_path / 'ledger.json'
    calls = []
    request = {'idempotency_key': 'q0-tick:M7:settlement'}
    original = module._write_ledger

    def fail_final_receipt(path, payload):
        entries = payload['settlements'].values()
        if any(entry.get('settled') is True for entry in entries):
            raise OSError('simulated crash after native effect')
        return original(path, payload)

    def native(req):
        calls.append(req)
        return {'status': 'VERIFIED', 'settled': True}

    monkeypatch.setattr(module, '_write_ledger', fail_final_receipt)
    with pytest.raises(OSError):
        module.LoopSettlementReconciler(ledger).settle_exactly_once(request, native)
    monkeypatch.setattr(module, '_write_ledger', original)
    with pytest.raises(module.SettlementReconcilerError, match='UNKNOWN_OUTCOME'):
        module.LoopSettlementReconciler(ledger).settle_exactly_once(request, native)
    assert len(calls) == 1
