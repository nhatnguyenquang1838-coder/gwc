from __future__ import annotations

import importlib
import importlib.util


def _dispatcher_module():
    spec = importlib.util.find_spec("tools.node_architect.semantic_dispatcher")
    assert spec is not None, "semantic dispatcher must exist"
    return importlib.import_module("tools.node_architect.semantic_dispatcher")


def _node() -> dict:
    return {
        "id": "failure_recovery.timeout-recovery",
        "version": "1.0.0",
        "family": "failure_recovery",
        "runtime_executable": True,
    }


def _source(**overrides) -> dict:
    source = {
        "status": "NAMED_TOOL_PRESENT",
        "runtime_eligible": True,
        "reason_code": "SEMANTIC_NAMED_TOOL_BOUND",
        "evaluator_path": "tools/node_architect/timeout_recovery.py",
        "descriptor_path": None,
    }
    source.update(overrides)
    return source


def test_dispatcher_runs_only_explicit_matching_binding():
    module = _dispatcher_module()
    calls: list[dict] = []

    def handler(payload):
        calls.append(dict(payload))
        return {"outcome": "RECONCILE", "reason_code": "UNKNOWN_EXTERNAL_EFFECT"}

    binding = module.SemanticEvaluatorBinding(
        node_id="failure_recovery.timeout-recovery",
        evaluator_path="tools/node_architect/timeout_recovery.py",
        handler=handler,
    )
    result = module.dispatch_semantic_node(
        _node(),
        _source(),
        {"effect_status": "UNKNOWN"},
        bindings={binding.node_id: binding},
    )

    assert calls == [{"effect_status": "UNKNOWN"}]
    assert result["status"] == "SEMANTIC_EXECUTED"
    assert result["semantic_execution"] is True
    assert result["result"]["outcome"] == "RECONCILE"
    assert result["authority_granted"] is False
    assert result["executed_effects"] == []
    assert result["result_digest"].startswith("sha256:")


def test_dispatcher_rejects_source_binding_mismatch_without_calling_handler():
    module = _dispatcher_module()
    called = False

    def handler(payload):
        nonlocal called
        called = True
        return {"outcome": "PASS"}

    binding = module.SemanticEvaluatorBinding(
        node_id="failure_recovery.timeout-recovery",
        evaluator_path="tools/node_architect/different.py",
        handler=handler,
    )
    result = module.dispatch_semantic_node(
        _node(),
        _source(),
        {},
        bindings={binding.node_id: binding},
    )

    assert called is False
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "SEMANTIC_BINDING_MISMATCH"
    assert result["semantic_execution"] is False


def test_dispatcher_blocks_descriptor_only_without_handler_call():
    module = _dispatcher_module()
    result = module.dispatch_semantic_node(
        _node(),
        _source(
            status="DESCRIPTOR_ONLY",
            runtime_eligible=False,
            reason_code="SEMANTIC_EVALUATOR_MISSING",
            evaluator_path=None,
        ),
        {},
        bindings={},
    )

    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "SEMANTIC_EVALUATOR_MISSING"
    assert result["semantic_execution"] is False


def test_dispatcher_fails_closed_on_handler_exception():
    module = _dispatcher_module()

    def handler(payload):
        raise RuntimeError("boom")

    binding = module.SemanticEvaluatorBinding(
        node_id="failure_recovery.timeout-recovery",
        evaluator_path="tools/node_architect/timeout_recovery.py",
        handler=handler,
    )
    result = module.dispatch_semantic_node(
        _node(),
        _source(),
        {},
        bindings={binding.node_id: binding},
    )

    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "SEMANTIC_EVALUATOR_ERROR"
    assert result["semantic_execution"] is False
    assert "RuntimeError" in result["error"]


def test_dispatcher_fails_closed_on_non_mapping_result():
    module = _dispatcher_module()

    def handler(payload):
        return ["not", "a", "mapping"]

    binding = module.SemanticEvaluatorBinding(
        node_id="failure_recovery.timeout-recovery",
        evaluator_path="tools/node_architect/timeout_recovery.py",
        handler=handler,
    )
    result = module.dispatch_semantic_node(
        _node(),
        _source(),
        {},
        bindings={binding.node_id: binding},
    )

    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "SEMANTIC_EVALUATOR_INVALID_RESULT"
    assert result["semantic_execution"] is False


def test_dispatcher_same_input_same_semantic_digest():
    module = _dispatcher_module()

    def handler(payload):
        return {"outcome": "PASS", "input": dict(payload)}

    binding = module.SemanticEvaluatorBinding(
        node_id="failure_recovery.timeout-recovery",
        evaluator_path="tools/node_architect/timeout_recovery.py",
        handler=handler,
    )
    kwargs = {
        "bindings": {binding.node_id: binding},
    }
    first = module.dispatch_semantic_node(_node(), _source(), {"x": 1}, **kwargs)
    second = module.dispatch_semantic_node(_node(), _source(), {"x": 1}, **kwargs)

    assert first["result_digest"] == second["result_digest"]
