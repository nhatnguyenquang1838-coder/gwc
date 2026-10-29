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


def _ack65_fixture():
    from tools.node_architect.q0_cf_facts import OPTION_B_DECISION_TEXT
    body = """<!-- dw.taskcontroller.communication/v2 -->
### A2A v2 · ACK #65
run: scrum781-q0-fresh-20261010-r1
seq: 65
from: GPT
to: Hermes
kind: ACK
source_ref: github://nhatnguyenquang1838-coder/gwc/issues/595
reply_to: https://github.com/nhatnguyenquang1838-coder/gwc/issues/595#issuecomment-6281823173

**GOAL**
NEW, EXPLICIT USER DECISION RECEIVED IN THE BOUND CHATGPT THREAD. This is human approval. ACK64 RECOMMENDS Option B and is NOT a Human approval.

**NEXT**
""" + OPTION_B_DECISION_TEXT + "\n\n**EVIDENCE**\nG1 materialized in canonical branch: `47fce8bf35515dc36ad830d5fe1c4b48535d6ff2`; plan `core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json` blob `444f64dcff12e52a95c69b4698d1cc369be295f0`; route `core/node-architect/q0-engineering-coordination-route-r1.json` blob `e1b75c8b20c8326c74873b634dac62a12820bfbf`.\n"
    return {
        "id": 6281930331,
        "html_url": "https://github.com/nhatnguyenquang1838-coder/gwc/issues/595#issuecomment-6281930331",
        "issue_url": "https://api.github.com/repos/nhatnguyenquang1838-coder/gwc/issues/595",
        "user": {"login": "nhatnguyenquang1838-coder"},
        "body": body,
    }


def _option_b_materialization():
    return {
        "commit": "47fce8bf35515dc36ad830d5fe1c4b48535d6ff2",
        "plan_ref": "core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json",
        "plan_git_blob": "444f64dcff12e52a95c69b4698d1cc369be295f0",
        "route_ref": "core/node-architect/q0-engineering-coordination-route-r1.json",
        "route_git_blob": "e1b75c8b20c8326c74873b634dac62a12820bfbf",
        "r3_plan": {
            "run_id": "scrum781-q0-fresh-20261010-r1",
            "g1_revision": {
                "status": "HUMAN_APPROVED_PENDING_NATIVE_ACTIVATION",
                "human_decision": {
                    "exact_text": "APPROVE OPTION B — Replan Q0 sang Controlled Failure Campaign, giữ original DWO NOT_REPRODUCED.",
                    "context_ref": "https://github.com/nhatnguyenquang1838-coder/gwc/issues/595#issuecomment-6281823173",
                    "scope": "ACCEPTANCE_TARGET_CHANGE_AND_G1_SUCCESSOR_PLAN_ONLY",
                    "not_effect_authority": True,
                },
            },
        },
        "route": {"approved_successor_g1": {
            "successor_plan_ref": "core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json",
            "activation_status": "PENDING_HERMES_CF_PRECHECK_AND_NATIVE_CHECKPOINT_RECONCILIATION",
        }},
    }


def test_ack65_is_controller_attestation_and_not_raw_human_or_effect_authority():
    from tools.node_architect.q0_cf_facts import validate_option_b_controller_attestation
    result = validate_option_b_controller_attestation(_ack65_fixture(), _option_b_materialization())
    assert result["decision_attested"] is True
    assert result["trust_class"] == "CONTROLLER_OBSERVED_HUMAN_DECISION_ATTESTATION"
    assert result["raw_human_receipt_present"] is False
    assert result["human_authenticated"] is False
    assert result["native_plan_activated"] is False
    assert result["authority_granted"] is False
    assert result["proposal_ref"] != result["decision_attestation_ref"]


@pytest.mark.parametrize("mutation,code", [
    ("proposal_comment", "HUMAN_DECISION_PROPOSAL_NOT_APPROVAL"),
    ("wrong_run", "HUMAN_DECISION_RUN_MISMATCH"),
    ("wrong_author", "HUMAN_DECISION_CONTROLLER_AUTHOR_MISMATCH"),
    ("wrong_sequence", "HUMAN_DECISION_SEQUENCE_MISMATCH"),
    ("wrong_text", "HUMAN_DECISION_TEXT_MISMATCH"),
    ("wrong_plan_blob", "HUMAN_DECISION_G1_MATERIALIZATION_MISMATCH"),
    ("wrong_r3_pointer", "HUMAN_DECISION_R3_BINDING_MISMATCH"),
])
def test_option_b_attestation_rejects_proposal_drift_and_unbound_materialization(mutation, code):
    from tools.node_architect.q0_cf_facts import validate_option_b_controller_attestation, Q0FactEvidenceError
    comment, materialization = _ack65_fixture(), _option_b_materialization()
    if mutation == "proposal_comment":
        comment["id"] = 6281823173
        comment["html_url"] = "https://github.com/nhatnguyenquang1838-coder/gwc/issues/595#issuecomment-6281823173"
        comment["body"] = comment["body"].replace("ACK #65", "ACK #64").replace("seq: 65", "seq: 64")
    elif mutation == "wrong_run":
        comment["body"] = comment["body"].replace("scrum781-q0-fresh-20261010-r1", "other-run")
    elif mutation == "wrong_author":
        comment["user"]["login"] = "untrusted-user"
    elif mutation == "wrong_sequence":
        comment["body"] = comment["body"].replace("ACK #65", "ACK #66").replace("seq: 65", "seq: 66")
    elif mutation == "wrong_text":
        comment["body"] = comment["body"].replace("APPROVE OPTION B", "RECOMMEND OPTION B")
    elif mutation == "wrong_plan_blob":
        materialization["plan_git_blob"] = "0" * 40
    elif mutation == "wrong_r3_pointer":
        materialization["r3_plan"]["g1_revision"]["human_decision"]["context_ref"] = comment["html_url"]
    with pytest.raises(Q0FactEvidenceError, match=code):
        validate_option_b_controller_attestation(comment, materialization)
