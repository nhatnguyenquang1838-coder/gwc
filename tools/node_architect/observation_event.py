"""Native GWC Universal v2 observation-event producer for DWO.

Only a verified RunStateRecord v2 can be observed. Canonical identity and
timestamp are preserved; the observer never manufactures GWC authority.
"""
from __future__ import annotations

import copy
import hashlib
import re
from typing import Any, Mapping

from tools.node_architect.canonical_digest.reference_canonicalizer import canonical_json_bytes
from tools.node_architect.universal_run_state import verify_run_state_record

SCHEMA_ID = "gwc.observation-event/v2"
SCHEMA_VERSION = 2
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


class ObservationEventError(ValueError):
    pass


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build_observation_event(
    run_state: Mapping[str, Any],
    *,
    source_repository: str,
    source_sha: str,
    runtime_epoch: str,
    typed_next: str | None = None,
    node_id: str | None = None,
    authority_ref: str | None = None,
    extra_evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    if not verify_run_state_record(run_state):
        raise ObservationEventError("RUN_STATE_RECORD_INVALID")
    if not isinstance(source_repository, str) or not source_repository.strip():
        raise ObservationEventError("SOURCE_REPOSITORY_REQUIRED")
    if not isinstance(source_sha, str) or not _SHA40.fullmatch(source_sha):
        raise ObservationEventError("SOURCE_SHA_INVALID")
    if not isinstance(runtime_epoch, str) or not runtime_epoch.strip():
        raise ObservationEventError("RUNTIME_EPOCH_REQUIRED")

    occurred_at = run_state.get("created_at")
    if not isinstance(occurred_at, str) or not occurred_at.strip():
        raise ObservationEventError("CANONICAL_OCCURRED_AT_REQUIRED")

    gate = str(run_state["active_gate"])
    state = run_state["gate_states"].get(gate)
    if not isinstance(state, str) or not state:
        raise ObservationEventError("ACTIVE_GATE_STATE_REQUIRED")

    refs = list((run_state.get("provenance") or {}).get("source_refs") or [])
    for ref in extra_evidence_refs or []:
        if ref not in refs:
            refs.append(ref)

    source_digest_value = (run_state.get("content_digest") or {}).get("value")
    if not isinstance(source_digest_value, str) or not re.fullmatch(r"[0-9a-f]{64}", source_digest_value):
        raise ObservationEventError("RUN_STATE_CONTENT_DIGEST_INVALID")

    return {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "event_id": str(run_state["record_id"]),
        "run_id": str(run_state["run_id"]),
        "sequence": int(run_state["sequence"]),
        "occurred_at": occurred_at,
        "source": {
            "system": "gwc",
            "repository": source_repository,
            "sha": source_sha,
        },
        "runtime": {
            "epoch": runtime_epoch,
            "profile": copy.deepcopy(dict(run_state["lifecycle_profile"])),
            "gate": gate,
            "state": state,
            "node_id": node_id,
            "typed_next": typed_next,
        },
        "event_type": "RUN_CREATED" if int(run_state["state_revision"]) == 1 else "RUN_STATE_CHANGED",
        "outcome": state,
        "actor": copy.deepcopy(dict(run_state["created_by"])),
        "authority_ref": authority_ref,
        "evidence_refs": refs,
        "payload": {
            "run_manifest_ref": run_state["run_manifest_ref"],
            "run_manifest_digest": run_state["run_manifest_digest"],
            "state_revision": run_state["state_revision"],
            "predecessor_state_ref": run_state.get("predecessor_state_ref"),
            "predecessor_state_digest": run_state.get("predecessor_state_digest"),
            "terminal_state": run_state["terminal_state"],
            "execution_refs": copy.deepcopy(dict(run_state["execution_refs"])),
            "future_contract_refs": copy.deepcopy(dict(run_state["future_contract_refs"])),
        },
        "source_digest": "sha256:" + source_digest_value,
    }


def observation_event_digest(event: Mapping[str, Any]) -> str:
    if event.get("schema_id") != SCHEMA_ID or event.get("schema_version") != SCHEMA_VERSION:
        raise ObservationEventError("OBSERVATION_EVENT_SCHEMA_INVALID")
    return canonical_digest(dict(event))

def build_controller_decision_observation_event(
    decision: Mapping[str, Any],
    *,
    source_repository: str,
    source_sha: str,
    runtime_epoch: str,
    emitted_at: str,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Build an observation event after a validated native Controller transition.

    emitted_at is the timestamp of the newly materialized observation event;
    it is not presented as the historical source-transition timestamp.
    """
    if not isinstance(decision, Mapping) or decision.get("schema_id") != "gwc.universal-run.controller-decision.v2":
        raise ObservationEventError("CONTROLLER_DECISION_INVALID")
    successor = decision.get("successor_run_state")
    transition = decision.get("transition_receipt")
    if not isinstance(successor, Mapping) or successor.get("schema_id") != "gwc.universal-run.run-state.v2":
        raise ObservationEventError("CONTROLLER_SUCCESSOR_STATE_REQUIRED")
    successor_subject = {key: value for key, value in successor.items() if key != "state_digest"}
    if successor.get("state_digest") != canonical_digest(successor_subject):
        raise ObservationEventError("CONTROLLER_SUCCESSOR_STATE_DIGEST_INVALID")
    if not isinstance(transition, Mapping) or transition.get("schema_id") != "gwc.universal-run.controller-transition-receipt.v2":
        raise ObservationEventError("CONTROLLER_TRANSITION_RECEIPT_REQUIRED")
    transition_subject = {key: value for key, value in transition.items() if key != "transition_digest"}
    transition_digest = transition.get("transition_digest")
    if transition_digest != canonical_digest(transition_subject):
        raise ObservationEventError("CONTROLLER_TRANSITION_DIGEST_INVALID")
    if not isinstance(source_repository, str) or not source_repository.strip():
        raise ObservationEventError("SOURCE_REPOSITORY_REQUIRED")
    if not isinstance(source_sha, str) or not _SHA40.fullmatch(source_sha):
        raise ObservationEventError("SOURCE_SHA_INVALID")
    if not isinstance(runtime_epoch, str) or not runtime_epoch.strip():
        raise ObservationEventError("RUNTIME_EPOCH_REQUIRED")
    if not isinstance(emitted_at, str) or not emitted_at.strip():
        raise ObservationEventError("OBSERVATION_EMITTED_AT_REQUIRED")

    transition_ref = transition.get("transition_ref")
    if not isinstance(transition_ref, str) or not transition_ref:
        raise ObservationEventError("CONTROLLER_TRANSITION_REF_REQUIRED")
    if transition.get("run_id") != successor.get("run_id"):
        raise ObservationEventError("CONTROLLER_TRANSITION_RUN_MISMATCH")
    post_state = transition.get("post_state")
    if not isinstance(post_state, Mapping):
        raise ObservationEventError("CONTROLLER_TRANSITION_POST_STATE_REQUIRED")
    if post_state.get("sequence") != successor.get("sequence"):
        raise ObservationEventError("CONTROLLER_TRANSITION_SEQUENCE_MISMATCH")
    if post_state.get("state_digest") != successor.get("state_digest"):
        raise ObservationEventError("CONTROLLER_TRANSITION_STATE_MISMATCH")

    gate = successor.get("active_gate")
    if not isinstance(gate, str) or not gate:
        raise ObservationEventError("CONTROLLER_ACTIVE_GATE_REQUIRED")
    evidence_refs = [transition_ref, str(transition_digest)]
    consumed = decision.get("consumed_receipt_digest")
    if isinstance(consumed, str) and consumed:
        evidence_refs.append(consumed)

    return {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "event_id": transition_ref,
        "run_id": str(successor["run_id"]),
        "sequence": int(successor["sequence"]),
        "occurred_at": emitted_at,
        "source": {"system": "gwc", "repository": source_repository, "sha": source_sha},
        "runtime": {
            "epoch": runtime_epoch,
            "profile": {"id": "gwc.universal-run.v2", "version": 2},
            "gate": gate,
            "state": "ACTIVE",
            "node_id": node_id,
            "typed_next": successor.get("typed_next"),
        },
        "event_type": "RUN_STATE_CHANGED",
        "outcome": "ACTIVE",
        "actor": {"type": "controller", "id": "UniversalController"},
        "authority_ref": None,
        "evidence_refs": evidence_refs,
        "payload": {
            "time_basis": "OBSERVATION_EVENT_EMITTED_AT",
            "transition_digest": transition_digest,
            "from_gate": transition.get("from_gate"),
            "to_gate": transition.get("to_gate"),
            "successor_state_digest": successor["state_digest"],
            "next_owner": successor.get("next_owner"),
            "gate_advanced": decision.get("gate_advanced"),
            "idempotent_replay": decision.get("idempotent_replay"),
        },
        "source_digest": str(successor["state_digest"]),
    }

