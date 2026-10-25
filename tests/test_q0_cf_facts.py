"""Fact-layer engineering fixtures are not naturally observed self-fix evidence."""
import copy
import hashlib
import json
from typing import Any

import pytest
from test_q0_work_evidence import _inputs


def _context(tmp_path) -> dict[str, Any]:
    from tools.node_architect.q0_work_evidence import build_cf_work_contract
    args = _inputs()
    contract = build_cf_work_contract(**args)
    payload = {"facts": {"plan": "unit-plan", "decision": "unit-decision", "identity": "unit-session", "dag": True}}
    path = tmp_path / "observed.json"
    path.write_text(json.dumps(payload))
    requirements = contract["leaves"][0]["acceptance_requirements"]
    specs = {requirement: {"source_ref": "unit:observed", "pointer": ["facts", key],
                           "value_type": "bool" if key == "dag" else "str", "predicate": "equals", "expected": value}
             for requirement, (key, value) in zip(requirements, payload["facts"].items())}
    return dict(contract=contract, contract_inputs=args, session_id="unit-session", scenario=None,
                source_root=tmp_path, sources={"unit:observed": {"path": "observed.json", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "kind": "UNIT_FIXTURE"}},
                fact_specs={"CF-PRECHECK": specs})


def test_independent_readback_is_consumed_as_facts_not_native_completion(tmp_path):
    from tools.node_architect.q0_cf_facts import build_cf_leaf_fact_receipt, consume_cf_leaf_fact_receipt
    context = _context(tmp_path)
    before = copy.deepcopy(context)
    receipt = build_cf_leaf_fact_receipt(cf_leaf="CF-PRECHECK", predecessors=[], **context)
    assert receipt["consumed"] is False
    assert receipt["evidence_kind"] == "PER_LEAF_SOURCE_READBACK_FACTS"
    assert len(receipt["facts"]) == 4
    result = consume_cf_leaf_fact_receipt(receipt, predecessors=[], previous_consumptions=[], **context)
    assert result["consumed"] is True
    assert result["fact_status"] == "ALL_REQUIRED_FACTS_VERIFIED"
    assert result["native_completion_accepted"] is False
    assert result["provenance_authenticated"] is False
    assert result["qualification_accepted"] is False
    assert result["authority_granted"] is False
    assert context == before


def _extend_specs(context, leaf):
    row = next(row for row in context["contract"]["leaves"] if row["cf_leaf"] == leaf)
    context["fact_specs"][leaf] = {
        req: {"source_ref": "unit:observed", "pointer": ["facts", "dag"],
              "value_type": "bool", "predicate": "equals", "expected": True}
        for req in row["acceptance_requirements"]
    }


def test_missing_predecessor_is_not_a_completed_leaf(tmp_path):
    from tools.node_architect.q0_cf_facts import build_cf_leaf_fact_receipt, consume_cf_leaf_fact_receipt, Q0FactEvidenceError
    context = _context(tmp_path)
    _extend_specs(context, "CF-RED")
    receipt = build_cf_leaf_fact_receipt(cf_leaf="CF-RED", predecessors=[], **context)
    with pytest.raises(Q0FactEvidenceError, match="CF_PREDECESSOR_CHAIN_REQUIRED"):
        consume_cf_leaf_fact_receipt(receipt, predecessors=[], previous_consumptions=[], **context)


def test_duplicate_consumption_is_refused_from_prior_record(tmp_path):
    from tools.node_architect.q0_cf_facts import build_cf_leaf_fact_receipt, consume_cf_leaf_fact_receipt, Q0FactEvidenceError
    context = _context(tmp_path)
    receipt = build_cf_leaf_fact_receipt(cf_leaf="CF-PRECHECK", predecessors=[], **context)
    first = consume_cf_leaf_fact_receipt(receipt, predecessors=[], previous_consumptions=[], **context)
    with pytest.raises(Q0FactEvidenceError, match="CF_FACT_RECEIPT_ALREADY_CONSUMED"):
        consume_cf_leaf_fact_receipt(receipt, predecessors=[], previous_consumptions=[first], **context)


def test_w5_certification_is_not_early_fact_completion(tmp_path):
    from tools.node_architect.q0_cf_facts import build_cf_leaf_fact_receipt, consume_cf_leaf_fact_receipt, Q0FactEvidenceError
    context = _context(tmp_path)
    _extend_specs(context, "CF-CERTIFY")
    receipt = build_cf_leaf_fact_receipt(cf_leaf="CF-CERTIFY", predecessors=[], **context)
    with pytest.raises(Q0FactEvidenceError, match="CF_MILESTONE_NOT_YET_DUE"):
        consume_cf_leaf_fact_receipt(receipt, predecessors=[], previous_consumptions=[], **context)


def _causal_context(tmp_path):
    """Untrusted unit records exercise semantic guards, NOT genuine runtime RED."""
    context = _context(tmp_path)
    scenario = {"scenario_id": "unit-causal-boundary", "subject": "APPROVED_DISTINCT_CONTROLLED",
                "defect_class": "GENUINE_GWC_RUNTIME_DEFECT", "source_ref": "unit:capture",
                "frozen_source_head": context["contract_inputs"]["source_head"]}
    for name in ["input", "prestate", "error"]:
        p = tmp_path / (name + ".json")
        p.write_text(json.dumps({"fixture": name}))
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        scenario[name + "_source_ref"] = "unit:" + name
        scenario[name + "_digest"] = "sha256:" + digest
        context["sources"]["unit:" + name] = {"path": p.name, "sha256": digest, "kind": "UNIT_FIXTURE"}
    context["scenario"] = scenario
    capture = {"scenario": scenario, "run_id": context["contract"]["run_id"], "session_id": context["session_id"],
               "source_head": scenario["frozen_source_head"],
               "native_candidate_sha": context["contract"]["source_bindings"]["native_candidate_sha"]}
    p = tmp_path / "capture.json"
    p.write_text(json.dumps(capture))
    context["sources"]["unit:capture"] = {"path": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "kind": "UNIT_FIXTURE"}
    for leaf in ["CF-RED", "CF-FIX", "CF-LOAD", "CF-REPLAY"]:
        _extend_specs(context, leaf)
    return context


def _prefix(context, count):
    from tools.node_architect.q0_cf_facts import build_cf_leaf_fact_receipt
    records = []
    for row in context["contract"]["leaves"][:count]:
        records.append(build_cf_leaf_fact_receipt(cf_leaf=row["cf_leaf"], predecessors=records, **context))
    return records


@pytest.mark.parametrize("mutation", ["injected", "wrong_run", "wrong_session", "wrong_native_candidate", "missing_freeze"])
def test_wrong_causal_source_is_rejected_even_when_resealed(tmp_path, mutation):
    from tools.node_architect.q0_cf_facts import build_cf_leaf_fact_receipt, consume_cf_leaf_fact_receipt, Q0FactEvidenceError
    context = _causal_context(tmp_path)
    records = _prefix(context, 2)
    p = tmp_path / "capture.json"
    capture = json.loads(p.read_text())
    if mutation == "injected":
        context["scenario"]["defect_class"] = "INJECTED_FAULT_RESILIENCE"
        capture["scenario"] = context["scenario"]
    elif mutation == "missing_freeze":
        context["scenario"].pop("input_digest")
        capture["scenario"] = context["scenario"]
    else:
        key = {"wrong_run": "run_id", "wrong_session": "session_id", "wrong_native_candidate": "native_candidate_sha"}[mutation]
        capture[key] = "unrelated"
    p.write_text(json.dumps(capture))
    context["sources"]["unit:capture"]["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    records = _prefix(context, 1)
    receipt = build_cf_leaf_fact_receipt(cf_leaf="CF-RED", predecessors=records[:1], **context)
    with pytest.raises(Q0FactEvidenceError, match="CF_CAUSAL_"):
        consume_cf_leaf_fact_receipt(receipt, predecessors=records[:1], previous_consumptions=[], **context)


def test_missing_fact_is_partial_only_when_explicitly_requested(tmp_path):
    from tools.node_architect.q0_cf_facts import build_cf_leaf_fact_receipt, consume_cf_leaf_fact_receipt, Q0FactEvidenceError
    context = _context(tmp_path)
    context["fact_specs"]["CF-PRECHECK"].pop(next(iter(context["fact_specs"]["CF-PRECHECK"])))
    receipt = build_cf_leaf_fact_receipt(cf_leaf="CF-PRECHECK", predecessors=[], **context)
    with pytest.raises(Q0FactEvidenceError, match="CF_REQUIRED_FACTS_MISSING_OR_INVALID"):
        consume_cf_leaf_fact_receipt(receipt, predecessors=[], previous_consumptions=[], **context)
    partial = consume_cf_leaf_fact_receipt(receipt, predecessors=[], previous_consumptions=[], require_complete=False, **context)
    assert partial["fact_status"] == "PARTIAL_FACTS_VERIFIED"
    assert len(partial["verified_facts"]) == 3


def test_unregistered_fabricated_source_is_not_readback(tmp_path):
    from tools.node_architect.q0_cf_facts import build_cf_leaf_fact_receipt, Q0FactEvidenceError
    context = _context(tmp_path)
    spec = next(iter(context["fact_specs"]["CF-PRECHECK"].values()))
    spec["source_ref"] = "fake:all-pass"
    with pytest.raises(Q0FactEvidenceError, match="FACT_SOURCE_UNREGISTERED"):
        build_cf_leaf_fact_receipt(cf_leaf="CF-PRECHECK", predecessors=[], **context)


@pytest.mark.parametrize("field", ["analysis_source_head", "native_candidate_sha", "runtime_plan_digest", "node_allocation_digest", "native_state_digest"])
def test_resealed_receipt_binding_drift_does_not_survive_independent_readback(tmp_path, field):
    from tools.node_architect.q0_cf_facts import build_cf_leaf_fact_receipt, consume_cf_leaf_fact_receipt, Q0FactEvidenceError
    from tools.node_architect.q0_native_g1_admission import _seal
    context = _context(tmp_path)
    receipt = build_cf_leaf_fact_receipt(cf_leaf="CF-PRECHECK", predecessors=[], **context)
    receipt["source_bindings"][field] = "drift"
    receipt["receipt_digest"] = _seal({k: v for k, v in receipt.items() if k != "receipt_digest"})
    with pytest.raises(Q0FactEvidenceError, match="FACT_RECEIPT_READBACK_MISMATCH"):
        consume_cf_leaf_fact_receipt(receipt, predecessors=[], previous_consumptions=[], **context)


def test_aliasing_one_observation_does_not_mint_another_consumption(tmp_path):
    from tools.node_architect.q0_cf_facts import build_cf_leaf_fact_receipt, consume_cf_leaf_fact_receipt, Q0FactEvidenceError
    context = _context(tmp_path)
    receipt = build_cf_leaf_fact_receipt(cf_leaf="CF-PRECHECK", predecessors=[], **context)
    first = consume_cf_leaf_fact_receipt(receipt, predecessors=[], previous_consumptions=[], **context)
    context["sources"]["unit:alias"] = copy.deepcopy(context["sources"]["unit:observed"])
    for spec in context["fact_specs"]["CF-PRECHECK"].values():
        spec["source_ref"] = "unit:alias"
    alias = build_cf_leaf_fact_receipt(cf_leaf="CF-PRECHECK", predecessors=[], **context)
    assert alias["receipt_digest"] != receipt["receipt_digest"]
    with pytest.raises(Q0FactEvidenceError, match="CF_FACT_OBSERVATION_ALREADY_CONSUMED"):
        consume_cf_leaf_fact_receipt(alias, predecessors=[], previous_consumptions=[first], **context)


def test_zero_facts_does_not_manufacture_partial_consumption(tmp_path):
    from tools.node_architect.q0_cf_facts import build_cf_leaf_fact_receipt, consume_cf_leaf_fact_receipt, Q0FactEvidenceError
    context = _context(tmp_path)
    context["fact_specs"] = {}
    receipt = build_cf_leaf_fact_receipt(cf_leaf="CF-PRECHECK", predecessors=[], **context)
    with pytest.raises(Q0FactEvidenceError, match="CF_NO_VERIFIED_FACTS"):
        consume_cf_leaf_fact_receipt(receipt, predecessors=[], previous_consumptions=[], require_complete=False, **context)


def test_complete_unit_causal_chain_never_authenticates_runtime_or_grants_w5_w6(tmp_path):
    from tools.node_architect.q0_cf_facts import consume_cf_leaf_fact_receipt
    context = _causal_context(tmp_path)
    records = _prefix(context, 5)
    result = consume_cf_leaf_fact_receipt(records[-1], predecessors=records[:-1], previous_consumptions=[], **context)
    assert result["fact_status"] == "ALL_REQUIRED_FACTS_VERIFIED"
    assert len(result["accepted_predecessor_chain"]) == 4
    assert result["native_completion_accepted"] is False
    assert result["provenance_authenticated"] is False
    assert result["qualification_accepted"] is False


def test_w6_cannot_be_inserted_as_a_work_completion_flag(tmp_path):
    from tools.node_architect.q0_cf_facts import build_cf_leaf_fact_receipt, consume_cf_leaf_fact_receipt, Q0FactEvidenceError
    from tools.node_architect.q0_native_g1_admission import _seal
    context = _context(tmp_path)
    receipt = build_cf_leaf_fact_receipt(cf_leaf="CF-PRECHECK", predecessors=[], **context)
    receipt["mapped_work_objectives"]["W6"] = "Human accepted"
    receipt["receipt_digest"] = _seal({k: v for k, v in receipt.items() if k != "receipt_digest"})
    with pytest.raises(Q0FactEvidenceError, match="FACT_RECEIPT_READBACK_MISMATCH"):
        consume_cf_leaf_fact_receipt(receipt, predecessors=[], previous_consumptions=[], **context)


@pytest.mark.parametrize("mutation", ["bytes", "outside", "type"])
def test_readback_drift_containment_and_bool_int_alias_are_refused(tmp_path, mutation):
    from tools.node_architect.q0_cf_facts import build_cf_leaf_fact_receipt, consume_cf_leaf_fact_receipt, Q0FactEvidenceError
    context = _context(tmp_path)
    receipt = build_cf_leaf_fact_receipt(cf_leaf="CF-PRECHECK", predecessors=[], **context)
    if mutation == "bytes":
        (tmp_path / "observed.json").write_text('{"facts": {}}')
        code = "FACT_SOURCE_READBACK_DRIFT"
    elif mutation == "outside":
        context["sources"]["unit:observed"]["path"] = "../outside.json"
        code = "FACT_SOURCE_PATH_INVALID"
    else:
        spec = list(context["fact_specs"]["CF-PRECHECK"].values())[-1]
        spec["value_type"], spec["expected"] = "int", 1
        receipt = build_cf_leaf_fact_receipt(cf_leaf="CF-PRECHECK", predecessors=[], **context)
        code = "CF_REQUIRED_FACTS_MISSING_OR_INVALID"
    with pytest.raises(Q0FactEvidenceError, match=code):
        consume_cf_leaf_fact_receipt(receipt, predecessors=[], previous_consumptions=[], **context)
