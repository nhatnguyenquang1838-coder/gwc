"""Per-leaf fact readback, deliberately separate from native qualification.

Pinned local sources and independent selectors prove what bytes were read, not
who authored them or that a runtime claim is genuine. This layer consumes typed
facts only. It cannot authenticate provenance, stamp work/matrix PASS, advance a
native cursor, or grant effects. Callers must persist returned consumption records
and pass their complete prior records for cross-invocation replay protection.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .q0_native_g1_admission import _seal
from .q0_work_evidence import validate_cf_work_contract


class Q0FactEvidenceError(ValueError):
    """Stable fact-layer refusal; never a Human approval request."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise Q0FactEvidenceError(code)


OPTION_B_DECISION_TEXT = (
    "APPROVE OPTION B — Replan Q0 sang Controlled Failure Campaign, giữ original DWO NOT_REPRODUCED."
)
_OPTION_B_PROPOSAL_REF = (
    "https://github.com/nhatnguyenquang1838-coder/gwc/issues/595#issuecomment-6281823173"
)
_OPTION_B_ATTESTATION_REF = (
    "https://github.com/nhatnguyenquang1838-coder/gwc/issues/595#issuecomment-6281930331"
)
_OPTION_B_G1_COMMIT = "47fce8bf35515dc36ad830d5fe1c4b48535d6ff2"
_OPTION_B_PLAN_REF = "core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json"
_OPTION_B_PLAN_BLOB = "444f64dcff12e52a95c69b4698d1cc369be295f0"
_OPTION_B_ROUTE_REF = "core/node-architect/q0-engineering-coordination-route-r1.json"
_OPTION_B_ROUTE_BLOB = "e1b75c8b20c8326c74873b634dac62a12820bfbf"


def validate_option_b_controller_attestation(
    comment: Mapping[str, Any], materialization: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify exact ACK65 + G1 bytes as a Controller attestation, not raw Human proof.

    The caller must obtain ``comment`` from a fresh GitHub API readback and independently
    resolve the declared Git blobs from the materialization commit. This pure validator
    checks their identity and cross-bindings; it does not authenticate the caller, the
    original browser turn, a Human principal, or native plan activation.
    """
    _require(isinstance(comment, Mapping) and isinstance(materialization, Mapping),
             "HUMAN_DECISION_ATTESTATION_INVALID")
    if comment.get("id") == 6281823173:
        raise Q0FactEvidenceError("HUMAN_DECISION_PROPOSAL_NOT_APPROVAL")
    _require(comment.get("id") == 6281930331
             and comment.get("html_url") == _OPTION_B_ATTESTATION_REF
             and comment.get("issue_url") == "https://api.github.com/repos/nhatnguyenquang1838-coder/gwc/issues/595",
             "HUMAN_DECISION_ATTESTATION_SOURCE_MISMATCH")
    user = comment.get("user")
    _require(isinstance(user, Mapping) and user.get("login") == "nhatnguyenquang1838-coder",
             "HUMAN_DECISION_CONTROLLER_AUTHOR_MISMATCH")
    body = comment.get("body")
    if not isinstance(body, str):
        raise Q0FactEvidenceError("HUMAN_DECISION_ATTESTATION_INVALID")
    lines = body.splitlines()
    _require(len(lines) >= 16 and lines[0] == "<!-- dw.taskcontroller.communication/v2 -->"
             and lines[1].startswith("### A2A v2 · "),
             "HUMAN_DECISION_COMMUNICATION_INVALID")
    headers: dict[str, str] = {}
    for line in lines[2:9]:
        if ": " not in line:
            raise Q0FactEvidenceError("HUMAN_DECISION_COMMUNICATION_INVALID")
        key, value = line.split(": ", 1)
        if key in headers:
            raise Q0FactEvidenceError("HUMAN_DECISION_COMMUNICATION_INVALID")
        headers[key] = value
    _require(set(headers) == {"run", "seq", "from", "to", "kind", "source_ref", "reply_to"},
             "HUMAN_DECISION_COMMUNICATION_INVALID")
    _require(lines[1].startswith(f"### A2A v2 · {headers['kind']} #{headers['seq']}"),
             "HUMAN_DECISION_SEQUENCE_MISMATCH")
    _require(headers["run"] == "scrum781-q0-fresh-20261010-r1", "HUMAN_DECISION_RUN_MISMATCH")
    _require(headers["seq"] == "65" and headers["kind"] == "ACK"
             and headers["from"] == "GPT" and headers["to"] == "Hermes"
             and headers["source_ref"] == "github://nhatnguyenquang1838-coder/gwc/issues/595",
             "HUMAN_DECISION_SEQUENCE_MISMATCH")
    _require(headers["reply_to"] == _OPTION_B_PROPOSAL_REF,
             "HUMAN_DECISION_PROPOSAL_LINK_MISMATCH")
    _require("NEW, EXPLICIT USER DECISION RECEIVED IN THE BOUND CHATGPT THREAD" in body
             and OPTION_B_DECISION_TEXT in body,
             "HUMAN_DECISION_TEXT_MISMATCH")

    expected_materialization = {
        "commit": _OPTION_B_G1_COMMIT,
        "plan_ref": _OPTION_B_PLAN_REF,
        "plan_git_blob": _OPTION_B_PLAN_BLOB,
        "route_ref": _OPTION_B_ROUTE_REF,
        "route_git_blob": _OPTION_B_ROUTE_BLOB,
    }
    _require(all(materialization.get(key) == value for key, value in expected_materialization.items())
             and all(value in body for value in expected_materialization.values()),
             "HUMAN_DECISION_G1_MATERIALIZATION_MISMATCH")
    plan = materialization.get("r3_plan")
    route = materialization.get("route")
    _require(isinstance(plan, Mapping) and plan.get("run_id") == headers["run"]
             and isinstance(plan.get("g1_revision"), Mapping), "HUMAN_DECISION_R3_BINDING_MISMATCH")
    revision = plan["g1_revision"]
    decision = revision.get("human_decision")
    successor = route.get("approved_successor_g1") if isinstance(route, Mapping) else None
    _require(revision.get("status") == "HUMAN_APPROVED_PENDING_NATIVE_ACTIVATION"
             and isinstance(decision, Mapping)
             and decision.get("exact_text") == OPTION_B_DECISION_TEXT
             and decision.get("context_ref") == _OPTION_B_PROPOSAL_REF
             and decision.get("scope") == "ACCEPTANCE_TARGET_CHANGE_AND_G1_SUCCESSOR_PLAN_ONLY"
             and decision.get("not_effect_authority") is True
             and isinstance(successor, Mapping)
             and successor.get("successor_plan_ref") == _OPTION_B_PLAN_REF
             and successor.get("activation_status") != "ACTIVATED",
             "HUMAN_DECISION_R3_BINDING_MISMATCH")
    return {
        "schema_id": "gwc.q0.option-b-controller-attestation-readback.v1",
        "decision_attestation_ref": _OPTION_B_ATTESTATION_REF,
        "proposal_ref": _OPTION_B_PROPOSAL_REF,
        "decision_text": OPTION_B_DECISION_TEXT,
        "run_id": headers["run"],
        "communication_seq": int(headers["seq"]),
        "github_comment_id": comment["id"],
        "github_author": user["login"],
        "g1_materialization_commit": _OPTION_B_G1_COMMIT,
        "plan_ref": _OPTION_B_PLAN_REF,
        "plan_git_blob": _OPTION_B_PLAN_BLOB,
        "route_ref": _OPTION_B_ROUTE_REF,
        "route_git_blob": _OPTION_B_ROUTE_BLOB,
        "trust_class": "CONTROLLER_OBSERVED_HUMAN_DECISION_ATTESTATION",
        "decision_attested": True,
        "raw_human_receipt_present": False,
        "human_authenticated": False,
        "native_plan_activated": False,
        "authority_granted": False,
        "qualification_accepted": False,
        "executed_effects": [],
    }


def _read_source(ref: str, context: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    registry = context["sources"]
    _require(ref in registry, "FACT_SOURCE_UNREGISTERED")
    descriptor = registry[ref]
    root = Path(context["source_root"]).resolve(strict=True)
    relative = Path(descriptor["path"])
    _require(not relative.is_absolute() and ".." not in relative.parts, "FACT_SOURCE_PATH_INVALID")
    path = (root / relative).resolve(strict=True)
    _require(path.is_relative_to(root), "FACT_SOURCE_PATH_INVALID")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    _require(digest == descriptor["sha256"], "FACT_SOURCE_READBACK_DRIFT")
    _require(isinstance(descriptor.get("kind"), str) and bool(descriptor["kind"].strip()), "FACT_SOURCE_KIND_REQUIRED")
    return json.loads(raw), {"source_ref": ref, "path": str(relative), "kind": descriptor["kind"],
                             "file_sha256": digest, "independent_readback": True,
                             "provenance_authenticated": False}


def _fact(requirement: str, spec: Any, context: Mapping[str, Any]) -> dict[str, Any]:
    if spec is None:
        return {"requirement": requirement, "validity": "MISSING", "value": None}
    _require(isinstance(spec, Mapping), "FACT_SPEC_INVALID")
    value, readback = _read_source(spec["source_ref"], context)
    pointer = spec["pointer"]
    _require(isinstance(pointer, list), "FACT_SPEC_INVALID")
    try:
        for component in pointer:
            value = value[component]
    except (KeyError, IndexError, TypeError):
        return {"requirement": requirement, "validity": "MISSING", "value": None, "source": readback}
    types = {"str": str, "int": int, "bool": bool, "list": list, "dict": dict}
    expected_type = types.get(spec.get("value_type"))
    _require(expected_type is not None, "FACT_TYPE_INVALID")
    typed = type(value) is expected_type
    predicate = spec.get("predicate")
    _require(predicate in {"equals", "nonempty", "nonzero_exit"}, "FACT_PREDICATE_INVALID")
    if predicate == "equals":
        valid = typed and type(value) is type(spec.get("expected")) and value == spec["expected"]
    elif predicate == "nonzero_exit":
        valid = typed and type(value) is int and value != 0
    else:
        valid = typed and isinstance(value, (str, list, dict)) and bool(value)
    return {"requirement": requirement, "value_type": spec["value_type"], "value": copy.deepcopy(value),
            "validity": "VALID" if valid else "INVALID", "source": readback,
            "selector": copy.deepcopy(dict(spec))}


def _causal_readback(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    scenario = context.get("scenario")
    if not isinstance(scenario, Mapping):
        raise Q0FactEvidenceError("CF_CAUSAL_SCENARIO_REQUIRED")
    _require(scenario.get("subject") == "APPROVED_DISTINCT_CONTROLLED"
             and scenario.get("defect_class") == "GENUINE_GWC_RUNTIME_DEFECT",
             "CF_CAUSAL_SCENARIO_CLASS_INVALID")
    _require(isinstance(scenario.get("scenario_id"), str) and bool(scenario["scenario_id"])
             and isinstance(scenario.get("frozen_source_head"), str)
             and re.fullmatch(r"[0-9a-f]{40}", scenario["frozen_source_head"]) is not None,
             "CF_CAUSAL_FREEZE_REQUIRED")
    capture_ref = scenario.get("source_ref")
    if not isinstance(capture_ref, str):
        raise Q0FactEvidenceError("CF_CAUSAL_CAPTURE_REQUIRED")
    capture, origin = _read_source(capture_ref, context)
    _require(isinstance(capture, Mapping) and capture.get("scenario") == scenario
             and capture.get("run_id") == context["contract"]["run_id"]
             and capture.get("session_id") == context["session_id"]
             and capture.get("source_head") == scenario["frozen_source_head"]
             and capture.get("native_candidate_sha") == context["contract"]["source_bindings"]["native_candidate_sha"],
             "CF_CAUSAL_CAPTURE_BINDING_MISMATCH")
    origins = [origin]
    for name in ("input", "prestate", "error"):
        ref, digest = scenario.get(name + "_source_ref"), scenario.get(name + "_digest")
        _require(isinstance(ref, str) and isinstance(digest, str)
                 and re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is not None,
                 "CF_CAUSAL_FREEZE_REQUIRED")
        if not isinstance(ref, str):
            raise Q0FactEvidenceError("CF_CAUSAL_FREEZE_REQUIRED")
        _, readback = _read_source(ref, context)
        _require(digest == "sha256:" + readback["file_sha256"], "CF_CAUSAL_FREEZE_DIGEST_MISMATCH")
        origins.append(readback)
    return origins


def build_cf_leaf_fact_receipt(*, cf_leaf: str, predecessors: Sequence[Mapping[str, Any]],
                               **context: Any) -> dict[str, Any]:
    """Produce measured facts against independently supplied current bindings."""
    contract = context["contract"]
    validate_cf_work_contract(contract, **context["contract_inputs"])
    _require(isinstance(context.get("session_id"), str) and bool(context["session_id"].strip()), "FACT_SESSION_REQUIRED")
    leaves = {row["cf_leaf"]: row for row in contract["leaves"]}
    _require(cf_leaf in leaves, "FACT_LEAF_INVALID")
    row = leaves[cf_leaf]
    specs = context["fact_specs"].get(cf_leaf, {})
    _require(set(specs) <= set(row["acceptance_requirements"]), "FACT_REQUIREMENT_UNKNOWN")
    body = {
        "schema_id": "gwc.q0.cf-leaf-fact-receipt.v1", "schema_version": 1,
        "evidence_kind": "PER_LEAF_SOURCE_READBACK_FACTS",
        "producer": "tools.node_architect.q0_cf_facts:build_cf_leaf_fact_receipt",
        "consumer": "tools.node_architect.q0_cf_facts:consume_cf_leaf_fact_receipt",
        "run_id": contract["run_id"], "session_id": context["session_id"],
        "issuer": {"kind": "LOCAL_FACT_COLLECTOR", "session_id": context["session_id"], "authenticated": False},
        "source_bindings": copy.deepcopy(contract["source_bindings"]),
        "contract_digest": contract["contract_digest"], "cf_leaf": cf_leaf,
        "mapped_work_objectives": {name: contract["objectives"][name] for name in row["native_work_ids"]},
        "scenario": copy.deepcopy(context.get("scenario")),
        "upstream_receipt_refs": [p["receipt_digest"] for p in predecessors],
        "required_predecessors": list(row["cf_predecessors"]),
        "facts": [_fact(req, specs.get(req), context) for req in row["acceptance_requirements"]],
        "consumed": False, "native_completion_accepted": False,
        "provenance_authenticated": False, "qualification_accepted": False,
        "authority_granted": False, "executed_effects": [],
    }
    return {**body, "receipt_digest": _seal(body)}


def consume_cf_leaf_fact_receipt(receipt: Mapping[str, Any], *,
                                 predecessors: Sequence[Mapping[str, Any]],
                                 previous_consumptions: Sequence[Mapping[str, Any]],
                                 require_complete: bool = True, **context: Any) -> dict[str, Any]:
    """Re-read all independent sources; return FACT consumption, not native PASS."""
    _require(isinstance(receipt, Mapping), "FACT_RECEIPT_INVALID")
    leaf = receipt.get("cf_leaf")
    if not isinstance(leaf, str):
        raise Q0FactEvidenceError("FACT_LEAF_INVALID")
    _require(leaf != "CF-CERTIFY", "CF_MILESTONE_NOT_YET_DUE")
    order = [row["cf_leaf"] for row in context["contract"]["leaves"]]
    _require(leaf in order, "FACT_LEAF_INVALID")
    _require([p.get("cf_leaf") for p in predecessors] == order[:order.index(leaf)],
             "CF_PREDECESSOR_CHAIN_REQUIRED")
    causal_sources = _causal_readback(context) if leaf != "CF-PRECHECK" else []
    for index, predecessor in enumerate(predecessors):
        consume_cf_leaf_fact_receipt(predecessor, predecessors=predecessors[:index],
                                     previous_consumptions=[], **context)
    expected = build_cf_leaf_fact_receipt(cf_leaf=leaf, predecessors=predecessors, **context)
    _require(dict(receipt) == expected, "FACT_RECEIPT_READBACK_MISMATCH")
    fingerprint = _seal({"run_id": expected["run_id"], "cf_leaf": leaf,
                         "source_bytes": sorted({fact["source"]["file_sha256"] for fact in expected["facts"] if "source" in fact}),
                         "causal_bytes": sorted({source["file_sha256"] for source in causal_sources})})
    for prior in previous_consumptions:
        body = {key: value for key, value in prior.items() if key != "consumption_digest"}
        _require(prior.get("consumption_digest") == _seal(body) and prior.get("consumed") is True,
                 "CF_PRIOR_CONSUMPTION_INVALID")
        _require(prior.get("receipt_digest") != receipt.get("receipt_digest"),
                 "CF_FACT_RECEIPT_ALREADY_CONSUMED")
        _require(prior.get("observation_fingerprint") != fingerprint,
                 "CF_FACT_OBSERVATION_ALREADY_CONSUMED")
    valid = [fact["requirement"] for fact in expected["facts"] if fact["validity"] == "VALID"]
    gaps = [fact["requirement"] for fact in expected["facts"] if fact["validity"] != "VALID"]
    _require(not require_complete or not gaps, "CF_REQUIRED_FACTS_MISSING_OR_INVALID")
    _require(bool(valid), "CF_NO_VERIFIED_FACTS")
    body = {"schema_id": "gwc.q0.cf-leaf-fact-consumption.v1", "schema_version": 1,
            "run_id": expected["run_id"], "session_id": expected["session_id"],
            "source_bindings": expected["source_bindings"], "contract_digest": expected["contract_digest"],
            "cf_leaf": expected["cf_leaf"], "receipt_digest": expected["receipt_digest"],
            "observation_fingerprint": fingerprint,
            "accepted_predecessor_chain": [p["receipt_digest"] for p in predecessors],
            "causal_source_readbacks": causal_sources,
            "consumer": expected["consumer"], "consumed": True, "verified_facts": valid, "missing_or_invalid_facts": gaps,
            "fact_status": "PARTIAL_FACTS_VERIFIED" if gaps else "ALL_REQUIRED_FACTS_VERIFIED",
            "native_completion_accepted": False, "provenance_authenticated": False,
            "qualification_accepted": False, "authority_granted": False, "executed_effects": []}
    return {**body, "consumption_digest": _seal(body)}
