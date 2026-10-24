from __future__ import annotations

import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest


def _m():
    return importlib.import_module("tools.node_architect.q0_qualification")


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _provenance(subject="ORIGINAL_DWO", defect_class="GENUINE_GWC_RUNTIME_DEFECT", **updates):
    body = {
        "subject": subject,
        "scenario_id": "dwo-incident-42" if subject == "ORIGINAL_DWO" else "controlled-fault-42",
        "observed_prestate_ref": "evidence:prestate-42",
        "observed_error_ref": "evidence:error-42",
        "defect_class": defect_class,
        "original_incident_replayed": subject == "ORIGINAL_DWO",
    }
    if subject == "APPROVED_DISTINCT_CONTROLLED":
        body["authorization_ref"] = "approval:controlled-replay-42"
    body.update(updates)
    body.pop("provenance_digest", None)
    return {**body, "provenance_digest": _digest(body)}


def _inputs(**overrides):
    m = _m()
    matrix_body = {
        "mandatory_entries": list(m.MANDATORY_QUALIFICATION_ENTRIES),
        "results": {name: "PASS" for name in m.MANDATORY_QUALIFICATION_ENTRIES},
        "active_unresolved_defects": [],
    }
    matrix = {"digest": _digest(matrix_body), **matrix_body}
    profile_digest = m.q0_qualification_profile()["profile_digest"]
    values = {
        "run_id": "scrum781-q0-replay-provenance-test",
        "task_id": "SCRUM-781",
        "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
        "qualification_profile": "q0_live_qualification",
        "qualification_profile_digest": profile_digest,
        "qualification_matrix": matrix,
        "candidate_sha": "a" * 40,
        "loaded_runtime_identity": "a" * 40,
        "load_proof_ref": "load-proof:replay-test",
        "load_proof_evidence": {
            "activation_id": "activation-replay-test",
            "candidate_sha": "a" * 40,
            "loaded_source_sha": "a" * 40,
            "source_root": "worktree:q0",
            "runtime_session_id": "session-replay-test",
            "runtime_process_id": "process-replay-test",
            "loaded_profile_digest": profile_digest,
            "loaded_module_identities": {"tools/node_architect/q0_qualification.py": "sha256:" + "e" * 64},
        },
        "incident_replay_refs": ["replay:incident-42"],
        "replay_result": "PASS",
        "replay_exact_readback": True,
        "replay_provenance": _provenance(),
        "previous_failure_state": "CONTROLLER_WAIT",
        "first_state_beyond_failure": "UR.G2_EXECUTION_STARTED",
        "forward_progress_refs": ["progress:42"],
        "broader_regression_refs": ["regression:42"],
        "broader_regression_result": "PASS",
        "stale_dependent_state": [],
        "created_at": "2026-10-22T00:00:00Z",
        "created_by": {"type": "agent", "id": "Codex-GPT"},
    }
    values.update(overrides)
    return values


def _certify(**overrides):
    return _m().certify_q0_runtime(**_inputs(**overrides))


@pytest.mark.parametrize("subject", ["ORIGINAL_DWO", "APPROVED_DISTINCT_CONTROLLED"])
def test_certifies_sealed_provenance_for_each_distinct_subject(subject):
    provenance = _provenance(subject=subject)
    cert = _certify(replay_provenance=provenance)
    assert cert["schema_version"] == "1.1"
    assert cert["replay_provenance"] == provenance
    assert _m().verify_q0_certification(cert) is True


def test_empty_incident_refs_keep_original_required_error():
    with pytest.raises(_m().Q0QualificationError, match="ORIGINAL_INCIDENT_REPLAY_REQUIRED"):
        _certify(incident_replay_refs=[])


@pytest.mark.parametrize("field", ["subject", "scenario_id", "observed_prestate_ref", "observed_error_ref"])
def test_missing_or_empty_provenance_identity_fails_closed(field):
    provenance = _provenance()
    provenance[field] = " "
    provenance["provenance_digest"] = _digest({k: v for k, v in provenance.items() if k != "provenance_digest"})
    with pytest.raises(_m().Q0QualificationError, match="REPLAY_PROVENANCE_REQUIRED"):
        _certify(replay_provenance=provenance)


def test_non_mapping_provenance_fails_closed():
    with pytest.raises(_m().Q0QualificationError, match="REPLAY_PROVENANCE_INVALID"):
        _certify(replay_provenance=[("subject", "ORIGINAL_DWO")])


def test_unrecognized_provenance_fields_are_rejected():
    provenance = _provenance()
    provenance["unbound_note"] = "extra"
    provenance["provenance_digest"] = _digest({k: v for k, v in provenance.items() if k != "provenance_digest"})
    with pytest.raises(_m().Q0QualificationError, match="REPLAY_PROVENANCE_FIELDS_INVALID"):
        _certify(replay_provenance=provenance)


def test_distinct_controlled_replay_requires_authorization():
    provenance = _provenance(subject="APPROVED_DISTINCT_CONTROLLED")
    del provenance["authorization_ref"]
    provenance["provenance_digest"] = _digest({k: v for k, v in provenance.items() if k != "provenance_digest"})
    with pytest.raises(_m().Q0QualificationError, match="REPLAY_PROVENANCE_AUTHORIZATION_REQUIRED"):
        _certify(replay_provenance=provenance)


@pytest.mark.parametrize("subject,replayed", [("ORIGINAL_DWO", False), ("APPROVED_DISTINCT_CONTROLLED", True)])
def test_subject_and_original_incident_flag_must_agree(subject, replayed):
    provenance = _provenance(subject=subject, original_incident_replayed=replayed)
    with pytest.raises(_m().Q0QualificationError, match="REPLAY_PROVENANCE_SUBJECT_MISMATCH"):
        _certify(replay_provenance=provenance)


def test_tampered_provenance_digest_is_rejected():
    provenance = _provenance()
    provenance["scenario_id"] = "different-scenario"
    with pytest.raises(_m().Q0QualificationError, match="REPLAY_PROVENANCE_DIGEST_MISMATCH"):
        _certify(replay_provenance=provenance)


def test_unsupported_provenance_subject_or_defect_class_is_rejected():
    provenance = _provenance(subject="INJECTED")
    with pytest.raises(_m().Q0QualificationError, match="REPLAY_PROVENANCE_SUBJECT_INVALID"):
        _certify(replay_provenance=provenance)


def test_injected_fault_cannot_claim_self_fix_replay_pass():
    provenance = _provenance(subject="APPROVED_DISTINCT_CONTROLLED", defect_class="INJECTED_FAULT_RESILIENCE")
    with pytest.raises(_m().Q0QualificationError, match="SELF_FIX_REPLAY_REQUIRES_GENUINE_DEFECT"):
        _certify(replay_provenance=provenance)


def test_injected_fault_without_self_fix_pass_still_cannot_complete_matrix():
    m = _m()
    matrix = copy.deepcopy(_inputs()["qualification_matrix"])
    matrix["results"]["self_fix_replay"] = "NOT_RUN"
    matrix["digest"] = _digest({k: v for k, v in matrix.items() if k != "digest"})
    provenance = _provenance(subject="APPROVED_DISTINCT_CONTROLLED", defect_class="INJECTED_FAULT_RESILIENCE")
    with pytest.raises(m.Q0QualificationError, match="INJECTED_FAULT_CANNOT_SATISFY_SELF_FIX_REPLAY"):
        _certify(qualification_matrix=matrix, replay_provenance=provenance)


def test_original_runtime_defect_may_claim_self_fix_replay_pass():
    provenance = _provenance(defect_class="GENUINE_GWC_RUNTIME_DEFECT")
    cert = _certify(replay_provenance=provenance)
    assert cert["replay_provenance"]["defect_class"] == "GENUINE_GWC_RUNTIME_DEFECT"


def test_schema_version_and_profile_digest_are_supported_version_boundaries():
    cert = _certify()
    legacy = copy.deepcopy(cert)
    legacy["schema_version"] = "1.0"
    legacy.pop("replay_provenance")
    legacy["qualification_profile_digest"] = "sha256:" + "0" * 64
    legacy["receipt_digest"] = _digest({k: v for k, v in legacy.items() if k != "receipt_digest"})
    assert _m().verify_q0_certification(legacy) is True

    unsupported = copy.deepcopy(cert)
    unsupported["schema_version"] = "9.9"
    unsupported["receipt_digest"] = _digest({k: v for k, v in unsupported.items() if k != "receipt_digest"})
    assert _m().verify_q0_certification(unsupported) is False

    stale_profile_semantics = copy.deepcopy(cert)
    stale_profile_semantics["qualification_profile"] = "legacy_q0"
    stale_profile_semantics["receipt_digest"] = _digest({k: v for k, v in stale_profile_semantics.items() if k != "receipt_digest"})
    assert _m().verify_q0_certification(stale_profile_semantics) is False

    stale_loaded_identity = copy.deepcopy(cert)
    stale_loaded_identity["load_proof_evidence"]["loaded_source_sha"] = "b" * 40
    stale_loaded_identity["receipt_digest"] = _digest({k: v for k, v in stale_loaded_identity.items() if k != "receipt_digest"})
    assert _m().verify_q0_certification(stale_loaded_identity) is False

    with pytest.raises(_m().Q0QualificationError, match="Q0_PROFILE_DIGEST_MISMATCH"):
        _certify(qualification_profile_digest="sha256:" + "0" * 64)


def test_matrix_digest_remains_independent_from_replay_provenance():
    first = _certify()
    second = _certify(replay_provenance=_provenance(scenario_id="another-original-scenario"))
    assert first["qualification_matrix_digest"] == second["qualification_matrix_digest"]
    assert first["replay_provenance"]["provenance_digest"] != second["replay_provenance"]["provenance_digest"]

    broken_matrix = copy.deepcopy(_inputs()["qualification_matrix"])
    broken_matrix["results"]["fresh_boot"] = "FAIL"
    with pytest.raises(_m().Q0QualificationError, match="QUALIFICATION_MATRIX_DIGEST_MISMATCH"):
        _certify(qualification_matrix=broken_matrix)


def test_certification_receipt_schema_validates_legacy_and_current_versions():
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path(__file__).resolve().parents[1] / "schemas/q0-certification-receipt.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    current = _certify()
    jsonschema.validate(current, schema)
    legacy = copy.deepcopy(current)
    legacy["schema_version"] = "1.0"
    legacy.pop("replay_provenance")
    legacy["receipt_digest"] = _digest({k: v for k, v in legacy.items() if k != "receipt_digest"})
    jsonschema.validate(legacy, schema)
