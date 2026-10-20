"""Hash-bound, non-rewriting Universal V2 checkpoint persistence and recovery.

This module never grants authority. Physical same-sequence recovery requires a
separately validated, exact-bound Controller authorization and preserves the
original checkpoint bytes before installing a new verified generation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


class CheckpointPersistenceError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _require(ok: bool, code: str, detail: str = "") -> None:
    if not ok:
        raise CheckpointPersistenceError(code, detail)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Mapping[str, Any], field: str) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes({k: v for k, v in value.items() if k != field})).hexdigest()


def _file_sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_schema(value: Mapping[str, Any], filename: str, error_code: str) -> None:
    try:
        import jsonschema
        schema_path = Path(__file__).resolve().parents[2] / "schemas/node-architect/universal-run" / filename
        jsonschema.validate(dict(value), json.loads(schema_path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise CheckpointPersistenceError(error_code, str(exc)) from exc


def _write_immutable(path: Path, payload: bytes, *, conflict_code: str) -> tuple[str, bool]:
    _require(not path.is_symlink(), "PERSISTENCE_PATH_SYMLINK", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = path.read_bytes()
        _require(existing == payload, conflict_code, str(path))
        return _file_sha(existing), True
    except OSError as exc:
        raise CheckpointPersistenceError("IMMUTABLE_ARTIFACT_WRITE_FAILED", str(exc)) from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        readback = path.read_bytes()
        _require(readback == payload, "IMMUTABLE_ARTIFACT_READBACK_MISMATCH", str(path))
        return _file_sha(readback), False
    except OSError as exc:
        raise CheckpointPersistenceError("IMMUTABLE_ARTIFACT_WRITE_FAILED", str(exc)) from exc


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointPersistenceError(code, str(exc)) from exc
    _require(isinstance(value, dict), code, "expected JSON object")
    return value


def materialize_controller_successor_snapshot(
    *, successor_run_state: Mapping[str, Any], runtime_plan_digest: str,
    candidate_sha: str, transition_ref: str, path: str | Path,
) -> dict[str, Any]:
    """Seal and write the full canonical successor state before checkpoint persistence."""
    state = copy.deepcopy(dict(successor_run_state))
    _require(state.get("schema_id") == "gwc.universal-run.run-state.v2" and state.get("schema_version") == 2,
             "SUCCESSOR_STATE_SCHEMA_INVALID")
    _require(state.get("state_digest") == _digest(state, "state_digest"), "SUCCESSOR_STATE_DIGEST_INVALID")
    refs = state.get("execution_refs")
    _require(isinstance(refs, Mapping), "SUCCESSOR_STATE_BINDING_INVALID", "execution_refs")
    _require(state.get("runtime_plan_digest", refs.get("runtime_plan_digest")) == runtime_plan_digest,
             "SUCCESSOR_PLAN_BINDING_MISMATCH")
    _require(refs.get("runtime_plan_digest") == runtime_plan_digest, "SUCCESSOR_PLAN_BINDING_MISMATCH")
    _require(refs.get("candidate_sha") == candidate_sha, "SUCCESSOR_CANDIDATE_BINDING_MISMATCH")
    _require(isinstance(transition_ref, str) and bool(transition_ref.strip()), "SUCCESSOR_TRANSITION_REF_INVALID")
    artifact: dict[str, Any] = {
        "schema_id": "gwc.universal-run.controller-successor-snapshot.v2",
        "schema_version": 2,
        "run_id": state["run_id"],
        "runtime_plan_digest": runtime_plan_digest,
        "candidate_sha": candidate_sha,
        "sequence": state["sequence"],
        "active_gate": state["active_gate"],
        "next_owner": state["next_owner"],
        "typed_next": state["typed_next"],
        "transition_ref": transition_ref,
        "successor_state_digest": state["state_digest"],
        "successor_run_state": state,
    }
    artifact["snapshot_digest"] = _digest(artifact, "snapshot_digest")
    _validate_schema(artifact, "controller-successor-snapshot.schema.json", "SUCCESSOR_SNAPSHOT_SCHEMA_INVALID")
    payload = (json.dumps(artifact, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    target = Path(path)
    file_sha, replay = _write_immutable(target, payload, conflict_code="SUCCESSOR_SNAPSHOT_IMMUTABLE_CONFLICT")
    return {
        "path": str(target), "file_sha256": file_sha,
        "snapshot_digest": artifact["snapshot_digest"],
        "successor_state_digest": state["state_digest"],
        "runtime_plan_digest": runtime_plan_digest,
        "candidate_sha": candidate_sha,
        "run_id": state["run_id"], "sequence": state["sequence"],
        "transition_ref": transition_ref, "idempotent_replay": replay,
    }


def bind_successor_snapshot_to_transition(
    *, transition: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind the full pre-persist successor artifact into the transition receipt."""
    result = copy.deepcopy(dict(transition))
    _require(result.get("transition_digest") == _digest(result, "transition_digest"), "TRANSITION_RECEIPT_DIGEST_INVALID")
    _require(result.get("run_id") == snapshot.get("run_id"), "TRANSITION_SNAPSHOT_RUN_MISMATCH")
    _require(result.get("runtime_plan_digest") == snapshot.get("runtime_plan_digest"), "TRANSITION_SNAPSHOT_PLAN_MISMATCH")
    _require(result.get("transition_ref") == snapshot.get("transition_ref"), "TRANSITION_SNAPSHOT_REF_MISMATCH")
    post = result.get("post_state")
    _require(isinstance(post, Mapping) and post.get("sequence") == snapshot.get("sequence")
             and post.get("state_digest") == snapshot.get("successor_state_digest"),
             "TRANSITION_SNAPSHOT_STATE_MISMATCH")
    result["successor_snapshot_ref"] = snapshot["path"]
    result["successor_snapshot_file_sha256"] = snapshot["file_sha256"]
    result["successor_snapshot_digest"] = snapshot["snapshot_digest"]
    result["successor_state_digest"] = snapshot["successor_state_digest"]
    result.pop("transition_digest", None)
    result["transition_digest"] = _digest(result, "transition_digest")
    _validate_schema(result, "controller-transition-receipt.schema.json", "TRANSITION_RECEIPT_SCHEMA_INVALID")
    return result


def materialize_successor_bound_transition_receipt(
    *, transition: Mapping[str, Any], snapshot: Mapping[str, Any], path: str | Path
) -> dict[str, Any]:
    """Bind and immutably persist a transition only after its full successor is sealed."""
    from .universal_run_controller import materialize_controller_transition_receipt

    bound = bind_successor_snapshot_to_transition(transition=transition, snapshot=snapshot)
    materialized = materialize_controller_transition_receipt(receipt=bound, path=path)
    return {"transition": bound, **materialized}


def make_checkpoint_document(
    *, run_state: Mapping[str, Any], runtime_plan: Mapping[str, Any], node_allocation: Mapping[str, Any],
    base_document: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the V2 checkpoint envelope while preserving unrelated run metadata."""
    state = copy.deepcopy(dict(run_state))
    _require(state.get("state_digest") == _digest(state, "state_digest"), "SUCCESSOR_STATE_DIGEST_INVALID")
    document = copy.deepcopy(dict(base_document or {}))
    document.update({
        "schema_id": "gwc.universal-run.run-state-checkpoint.v2",
        "schema_version": 2,
        "run_id": state["run_id"],
        "runtime_plan": copy.deepcopy(dict(runtime_plan)),
        "node_allocation": copy.deepcopy(dict(node_allocation)),
        "run_state": state,
        "sequence": state["sequence"],
        "active_gate": state["active_gate"],
        "next_owner": state["next_owner"],
        "typed_next": state["typed_next"],
        "state_digest": state["state_digest"],
    })
    document.pop("checkpoint_digest", None)
    document["checkpoint_digest"] = _digest(document, "checkpoint_digest")
    return document


def _verify_checkpoint_document(document: Mapping[str, Any], *, require_valid: bool) -> Mapping[str, Any]:
    state = document.get("run_state")
    _require(isinstance(state, Mapping), "CHECKPOINT_RUN_STATE_INVALID")
    if require_valid:
        _require(state.get("state_digest") == _digest(state, "state_digest"), "CHECKPOINT_STATE_DIGEST_INVALID")
        _require(document.get("checkpoint_digest") == _digest(document, "checkpoint_digest"), "CHECKPOINT_ENVELOPE_DIGEST_INVALID")
    return state


def materialize_persistence_intent(
    *, current_checkpoint_path: str | Path, expected_current_file_sha256: str,
    intended_checkpoint_document: Mapping[str, Any], snapshot_path: str | Path,
    transition_receipt_path: str | Path, writer_identity: str, intent_path: str | Path,
) -> dict[str, Any]:
    """Persist exact CAS and successor provenance before any official checkpoint rewrite."""
    current_path, snap_path, transition_path = Path(current_checkpoint_path), Path(snapshot_path), Path(transition_receipt_path)
    _require(not current_path.is_symlink(), "CHECKPOINT_PATH_SYMLINK")
    try:
        current_bytes = current_path.read_bytes()
    except OSError as exc:
        raise CheckpointPersistenceError("CHECKPOINT_READ_FAILED", str(exc)) from exc
    current_sha = _file_sha(current_bytes)
    _require(current_sha == expected_current_file_sha256, "NATIVE_CHECKPOINT_CAS_CONFLICT")
    current = _load_json(current_path, "CHECKPOINT_JSON_INVALID")
    prior_state = _verify_checkpoint_document(current, require_valid=False)
    intended = copy.deepcopy(dict(intended_checkpoint_document))
    successor = _verify_checkpoint_document(intended, require_valid=True)
    snapshot = _load_json(snap_path, "SUCCESSOR_SNAPSHOT_INVALID")
    _require(snapshot.get("snapshot_digest") == _digest(snapshot, "snapshot_digest"), "SUCCESSOR_SNAPSHOT_DIGEST_INVALID")
    _require(snapshot.get("successor_run_state") == dict(successor), "SUCCESSOR_SNAPSHOT_CHECKPOINT_MISMATCH")
    transition = _load_json(transition_path, "TRANSITION_RECEIPT_INVALID")
    _require(transition.get("transition_digest") == _digest(transition, "transition_digest"), "TRANSITION_RECEIPT_DIGEST_INVALID")
    _require(transition.get("successor_snapshot_file_sha256") == _file_sha(snap_path.read_bytes()), "TRANSITION_SNAPSHOT_FILE_HASH_MISMATCH")
    _require(transition.get("successor_snapshot_digest") == snapshot.get("snapshot_digest"), "TRANSITION_SNAPSHOT_DIGEST_MISMATCH")
    _require(transition.get("successor_state_digest") == successor.get("state_digest"), "TRANSITION_SNAPSHOT_STATE_MISMATCH")
    _require(transition.get("run_id") == successor.get("run_id") and transition.get("runtime_plan_digest") == snapshot.get("runtime_plan_digest"),
             "TRANSITION_SUCCESSOR_BINDING_MISMATCH")
    _require(isinstance(writer_identity, str) and bool(writer_identity.strip()), "PERSISTENCE_WRITER_IDENTITY_REQUIRED")
    intended_bytes = (json.dumps(intended, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    intent: dict[str, Any] = {
        "schema_id": "gwc.universal-run.controller-persistence-intent.v2",
        "schema_version": 2,
        "writer_api_identity": writer_identity,
        "checkpoint_ref": str(current_path),
        "prior_generation": {
            "checkpoint_file_sha256": current_sha,
            "checkpoint_sequence": prior_state.get("sequence"),
            "checkpoint_state_digest": prior_state.get("state_digest"),
            "state_digest_valid": prior_state.get("state_digest") == _digest(prior_state, "state_digest"),
            "generation_or_cas_revision": current.get("generation") or current.get("checkpoint_generation") or current.get("revision") or f"file-sha256:{current_sha}",
            "checkpoint_envelope_digest_valid": current.get("checkpoint_digest") == _digest(current, "checkpoint_digest"),
        },
        "cas": {"expected_current_file_sha256": current_sha, "compare_and_swap": True},
        "successor_snapshot": {
            "path": str(snap_path), "file_sha256": _file_sha(snap_path.read_bytes()),
            "snapshot_digest": snapshot["snapshot_digest"],
            "successor_state_digest": successor["state_digest"],
        },
        "transition_receipt": {
            "path": str(transition_path), "file_sha256": _file_sha(transition_path.read_bytes()),
            "transition_digest": transition["transition_digest"],
            "transition_ref": transition["transition_ref"],
        },
        "intended_checkpoint_file_sha256": _file_sha(intended_bytes),
        "intended_run_id": successor["run_id"],
        "intended_sequence": successor["sequence"],
        "intended_gate": successor["active_gate"],
        "intended_owner": successor["next_owner"],
        "intended_typed_next": successor["typed_next"],
        "intended_checkpoint_document": intended,
    }
    intent["intent_digest"] = _digest(intent, "intent_digest")
    _validate_schema(intent, "controller-persistence-intent.schema.json", "PERSISTENCE_INTENT_SCHEMA_INVALID")
    payload = (json.dumps(intent, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path = Path(intent_path)
    sha, replay = _write_immutable(path, payload, conflict_code="PERSISTENCE_INTENT_IMMUTABLE_CONFLICT")
    _require(current_path.read_bytes() == current_bytes, "NATIVE_CHECKPOINT_CHANGED_DURING_INTENT")
    return {"path": str(path), "file_sha256": sha, "intent_digest": intent["intent_digest"], "idempotent_replay": replay}


def _verify_authorization(auth: Mapping[str, Any], *, intent: Mapping[str, Any], snapshot: Mapping[str, Any], transition: Mapping[str, Any]) -> None:
    _require(auth.get("schema_id") == "gwc.universal-run.same-sequence-recovery-authorization.v2"
             and auth.get("decision") == "AUTHORIZE"
             and auth.get("authorized_action") == "NONREWRITE_SAME_SEQ_CHECKPOINT_RECOVERY",
             "RECOVERY_AUTHORIZATION_REQUIRED")
    _require(auth.get("authorization_digest") == _digest(auth, "authorization_digest"), "RECOVERY_AUTHORIZATION_DIGEST_INVALID")
    _validate_schema(auth, "same-sequence-recovery-authorization.schema.json", "RECOVERY_AUTHORIZATION_SCHEMA_INVALID")
    state = snapshot["successor_run_state"]
    expected = {
        "run_id": state["run_id"], "runtime_plan_digest": snapshot["runtime_plan_digest"],
        "candidate_sha": snapshot["candidate_sha"], "sequence": state["sequence"],
        "active_gate": state["active_gate"], "next_owner": state["next_owner"],
        "typed_next": state["typed_next"],
        "expected_checkpoint_file_sha256": intent["cas"]["expected_current_file_sha256"],
        "successor_snapshot_digest": snapshot["snapshot_digest"],
        "transition_digest": transition["transition_digest"],
    }
    for key, value in expected.items():
        _require(auth.get(key) == value, "RECOVERY_AUTHORIZATION_BINDING_MISMATCH", key)
    _require(auth.get("authority_granted") is False and auth.get("executed_effects") == [], "RECOVERY_AUTHORITY_ESCALATION")
    _require(bool(auth.get("authority_ref")) and bool(auth.get("controller_body_sha256")), "RECOVERY_AUTHORITY_PROVENANCE_REQUIRED")
    _require(isinstance(auth.get("controller_sequence"), int) and not isinstance(auth.get("controller_sequence"), bool), "RECOVERY_AUTHORITY_PROVENANCE_REQUIRED")


def persist_same_sequence_checkpoint_recovery(
    *, checkpoint_path: str | Path, intent_path: str | Path, snapshot_path: str | Path,
    transition_receipt_path: str | Path, archive_path: str | Path,
    authorization: Mapping[str, Any] | None, profile: Mapping[str, Any],
    runtime_plan: Mapping[str, Any], node_allocation: Mapping[str, Any],
    recovery_receipt_path: str | Path,
) -> dict[str, Any]:
    """CAS-install one authorized canonical state at the same logical cursor, archiving corrupt bytes."""
    from .universal_run_controller import UniversalController

    cp_path, intent_file, snap_path, transition_path = map(Path, (checkpoint_path, intent_path, snapshot_path, transition_receipt_path))
    _require(authorization is not None, "RECOVERY_AUTHORIZATION_REQUIRED")
    intent = _load_json(intent_file, "PERSISTENCE_INTENT_INVALID")
    _require(intent.get("intent_digest") == _digest(intent, "intent_digest"), "PERSISTENCE_INTENT_DIGEST_INVALID")
    snapshot = _load_json(snap_path, "SUCCESSOR_SNAPSHOT_INVALID")
    transition = _load_json(transition_path, "TRANSITION_RECEIPT_INVALID")
    _require(snapshot.get("snapshot_digest") == _digest(snapshot, "snapshot_digest"), "SUCCESSOR_SNAPSHOT_DIGEST_INVALID")
    _require(transition.get("transition_digest") == _digest(transition, "transition_digest"), "TRANSITION_RECEIPT_DIGEST_INVALID")
    _verify_authorization(authorization, intent=intent, snapshot=snapshot, transition=transition)
    successor = snapshot.get("successor_run_state")
    _require(isinstance(successor, Mapping), "SUCCESSOR_SNAPSHOT_STATE_INVALID")
    _require(successor.get("state_digest") == _digest(successor, "state_digest"), "SUCCESSOR_STATE_DIGEST_INVALID")
    try:
        UniversalController(profile=profile, runtime_plan=runtime_plan, run_state=successor, node_allocation=node_allocation)
    except Exception as exc:
        code = getattr(exc, "code", "CONTROLLER_SUCCESSOR_VALIDATION_FAILED")
        raise CheckpointPersistenceError(code, str(exc)) from exc

    try:
        current_bytes = cp_path.read_bytes()
    except OSError as exc:
        raise CheckpointPersistenceError("CHECKPOINT_READ_FAILED", str(exc)) from exc
    intended = intent["intended_checkpoint_document"]
    payload = (json.dumps(intended, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    current_sha = _file_sha(current_bytes)
    if current_sha != intent["cas"]["expected_current_file_sha256"]:
        if current_bytes == payload:
            existing_receipt = _load_json(Path(recovery_receipt_path), "RECOVERY_RECEIPT_INVALID")
            _require(existing_receipt.get("receipt_digest") == _digest(existing_receipt, "receipt_digest"), "RECOVERY_RECEIPT_DIGEST_INVALID")
            _validate_schema(existing_receipt, "same-sequence-recovery-receipt.schema.json", "RECOVERY_RECEIPT_SCHEMA_INVALID")
            _require(existing_receipt.get("recovery_intent_digest") == intent["intent_digest"], "RECOVERY_RECEIPT_IDEMPOTENCY_CONFLICT")
            return {"idempotent_replay": True, "logical_cursor_changed": False,
                    "checkpoint_file_sha256": current_sha,
                    "recovery_receipt_file_sha256": _file_sha(Path(recovery_receipt_path).read_bytes())}
        raise CheckpointPersistenceError("NATIVE_CHECKPOINT_CAS_CONFLICT")
    current = _load_json(cp_path, "CHECKPOINT_JSON_INVALID")
    old_state = _verify_checkpoint_document(current, require_valid=False)
    _require(intent.get("prior_generation", {}).get("state_digest_valid") is False,
             "SAME_SEQUENCE_RECOVERY_REQUIRES_INVALID_STATE_DIGEST")
    for key in ("run_id", "sequence", "active_gate", "next_owner", "typed_next"):
        _require(old_state.get(key) == successor.get(key), "RECOVERY_LOGICAL_CURSOR_MISMATCH", key)
    _require(old_state.get("runtime_plan_digest", old_state.get("execution_refs", {}).get("runtime_plan_digest")) == snapshot.get("runtime_plan_digest"),
             "RECOVERY_PLAN_BINDING_MISMATCH")
    _require(_file_sha(payload) == intent.get("intended_checkpoint_file_sha256"), "INTENDED_CHECKPOINT_DIGEST_MISMATCH")

    lock = cp_path.with_name(cp_path.name + ".same-sequence-recovery.lock")
    try:
        lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CheckpointPersistenceError("RECOVERY_ALREADY_IN_PROGRESS") from exc
    except OSError as exc:
        raise CheckpointPersistenceError("RECOVERY_LOCK_FAILED", str(exc)) from exc
    try:
        _require(cp_path.read_bytes() == current_bytes, "NATIVE_CHECKPOINT_CAS_CONFLICT")
        archive = Path(archive_path)
        archive_sha, archive_replay = _write_immutable(archive, current_bytes, conflict_code="CORRUPT_CHECKPOINT_ARCHIVE_CONFLICT")
        generation_dir = cp_path.with_name(cp_path.name + ".generations")
        generation_path = generation_dir / f"seq{successor['sequence']}-{_file_sha(payload)}.json"
        generation_sha, generation_replay = _write_immutable(generation_path, payload, conflict_code="CHECKPOINT_GENERATION_CONFLICT")
        _require(cp_path.read_bytes() == current_bytes, "NATIVE_CHECKPOINT_CAS_CONFLICT")
        fd, temp_name = tempfile.mkstemp(prefix=cp_path.name + ".", suffix=".tmp", dir=cp_path.parent)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            _require(cp_path.read_bytes() == current_bytes, "NATIVE_CHECKPOINT_CAS_CONFLICT")
            os.replace(temp, cp_path)
            dir_fd = os.open(cp_path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            temp.unlink(missing_ok=True)
        readback = cp_path.read_bytes()
        _require(readback == payload, "NATIVE_CHECKPOINT_READBACK_MISMATCH")
        decoded = _load_json(cp_path, "CHECKPOINT_JSON_INVALID")
        readback_state = _verify_checkpoint_document(decoded, require_valid=True)
        _require(dict(readback_state) == dict(successor), "NATIVE_CHECKPOINT_STATE_READBACK_MISMATCH")
        try:
            UniversalController(profile=profile, runtime_plan=runtime_plan, run_state=readback_state, node_allocation=node_allocation)
        except Exception as exc:
            raise CheckpointPersistenceError("CONTROLLER_READBACK_VALIDATION_FAILED", str(exc)) from exc
        receipt: dict[str, Any] = {
            "schema_id": "gwc.universal-run.same-sequence-recovery-receipt.v2",
            "schema_version": 2,
            "recovery_intent_digest": intent["intent_digest"],
            "authorization_digest": authorization["authorization_digest"],
            "checkpoint_ref": str(cp_path),
            "prior_checkpoint_file_sha256": current_sha,
            "corrupt_checkpoint_archive_ref": str(archive),
            "corrupt_checkpoint_archive_file_sha256": archive_sha,
            "generation_ref": str(generation_path),
            "generation_file_sha256": generation_sha,
            "checkpoint_readback_file_sha256": _file_sha(readback),
            "run_id": successor["run_id"], "sequence": successor["sequence"],
            "active_gate": successor["active_gate"], "next_owner": successor["next_owner"],
            "typed_next": successor["typed_next"], "state_digest": successor["state_digest"],
            "logical_cursor_changed": False, "authority_granted": False, "executed_effects": [],
        }
        receipt["receipt_digest"] = _digest(receipt, "receipt_digest")
        _validate_schema(receipt, "same-sequence-recovery-receipt.schema.json", "RECOVERY_RECEIPT_SCHEMA_INVALID")
        receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        receipt_file_sha, receipt_replay = _write_immutable(Path(recovery_receipt_path), receipt_bytes,
                                                           conflict_code="RECOVERY_RECEIPT_IMMUTABLE_CONFLICT")
        return {"idempotent_replay": False, "logical_cursor_changed": False,
                "checkpoint_file_sha256": _file_sha(readback), "corrupt_checkpoint_archive_file_sha256": archive_sha,
                "generation_file_sha256": generation_sha, "recovery_receipt_file_sha256": receipt_file_sha,
                "archive_idempotent_replay": archive_replay, "generation_idempotent_replay": generation_replay,
                "receipt_idempotent_replay": receipt_replay}
    finally:
        os.close(lock_fd)
        lock.unlink(missing_ok=True)


def _verify_recovery_replan_activation_authorization(
    authorization: Mapping[str, Any], *, expected_checkpoint_sha: str,
    runtime_plan: Mapping[str, Any], successor: Mapping[str, Any],
    recovery_replan_receipt: Mapping[str, Any], invalidation: Mapping[str, Any],
) -> None:
    _require(isinstance(authorization, Mapping), "RECOVERY_REPLAN_AUTHORIZATION_REQUIRED")
    _require(authorization.get("schema_id") == "gwc.universal-run.recovery-replan-cursor-activation-authorization.v2"
             and authorization.get("decision") == "AUTHORIZE"
             and authorization.get("authorized_action") == "IMMUTABLE_INTEGRITY_RECOVERY_REPLAN_CURSOR_ACTIVATION",
             "RECOVERY_REPLAN_AUTHORIZATION_REQUIRED")
    _require(authorization.get("authorization_digest") == _digest(authorization, "authorization_digest"),
             "RECOVERY_REPLAN_AUTHORIZATION_DIGEST_INVALID")
    _validate_schema(authorization, "recovery-replan-cursor-activation-authorization.schema.json",
                     "RECOVERY_REPLAN_AUTHORIZATION_SCHEMA_INVALID")
    expected = {
        "run_id": successor.get("run_id"),
        "runtime_plan_digest": runtime_plan.get("digest"),
        "candidate_sha": runtime_plan.get("source_binding", {}).get("pre_head_sha"),
        "expected_incident_checkpoint_file_sha256": expected_checkpoint_sha,
        "incident_sequence": 14, "incident_gate": "UR.G5",
        "recovery_sequence": successor.get("sequence"),
        "recovery_gate": successor.get("active_gate"),
        "next_owner": successor.get("next_owner"), "typed_next": successor.get("typed_next"),
        "recovery_replan_receipt_digest": recovery_replan_receipt.get("receipt_digest"),
        "stale_evidence_invalidation_digest": invalidation.get("manifest_digest"),
    }
    for key, value in expected.items():
        _require(authorization.get(key) == value, "RECOVERY_REPLAN_AUTHORIZATION_BINDING_MISMATCH", key)
    _require(authorization.get("authority_granted") is False and authorization.get("executed_effects") == [],
             "RECOVERY_REPLAN_AUTHORITY_ESCALATION")
    _require(bool(authorization.get("authority_ref")) and bool(authorization.get("controller_body_sha256")),
             "RECOVERY_REPLAN_AUTHORITY_PROVENANCE_REQUIRED")


def persist_recovery_replan_cursor_activation(
    *, checkpoint_path: str | Path, expected_incident_checkpoint_file_sha256: str,
    archive_path: str | Path, generation_path: str | Path, activation_receipt_path: str | Path,
    recovery_cursor_state: Mapping[str, Any], authorization: Mapping[str, Any] | None,
    profile: Mapping[str, Any], runtime_plan: Mapping[str, Any], node_allocation: Mapping[str, Any],
    recovery_replan_receipt: Mapping[str, Any], stale_evidence_invalidation_record: Mapping[str, Any],
) -> dict[str, Any]:
    """CAS-install one authorized immutable recovery generation, archiving incident bytes first.

    The function is an implementation capability; callers remain responsible for
    invoking it only on the exact checkpoint and under a current typed Controller
    authorization. Tests exercise it against disposable checkpoints only.
    """
    from .universal_run_controller import UniversalController

    cp_path = Path(checkpoint_path)
    archive = Path(archive_path)
    generation = Path(generation_path)
    receipt_path = Path(activation_receipt_path)
    if authorization is None:
        raise CheckpointPersistenceError("RECOVERY_REPLAN_AUTHORIZATION_REQUIRED")
    auth = authorization
    _require(not cp_path.is_symlink(), "CHECKPOINT_PATH_SYMLINK")
    _require(not archive.is_symlink() and not generation.is_symlink() and not receipt_path.is_symlink(),
             "PERSISTENCE_PATH_SYMLINK")
    _require(recovery_cursor_state.get("state_digest") == _digest(recovery_cursor_state, "state_digest"),
             "RECOVERY_REPLAN_STATE_DIGEST_INVALID")
    successor = dict(recovery_cursor_state)
    _require(successor.get("run_id") == runtime_plan.get("run_id")
             and successor.get("runtime_plan_digest") == runtime_plan.get("digest")
             and successor.get("sequence") == 15 and successor.get("active_gate") == "UR.G2"
             and successor.get("next_owner") == "EXECUTOR"
             and successor.get("typed_next") == "EXECUTE_Q0_R7_UR_G2_REPLAY_PROBE",
             "RECOVERY_REPLAN_STATE_BINDING_MISMATCH")
    _require(recovery_replan_receipt.get("receipt_digest") == _digest(recovery_replan_receipt, "receipt_digest")
             and recovery_replan_receipt.get("run_id") == successor.get("run_id")
             and recovery_replan_receipt.get("to_plan", {}).get("digest") == runtime_plan.get("digest")
             and recovery_replan_receipt.get("new_candidate_sha") == runtime_plan.get("source_binding", {}).get("pre_head_sha"),
             "RECOVERY_REPLAN_RECEIPT_BINDING_MISMATCH")
    _require(stale_evidence_invalidation_record.get("manifest_digest") == _digest(stale_evidence_invalidation_record, "manifest_digest")
             and stale_evidence_invalidation_record.get("run_id") == successor.get("run_id")
             and stale_evidence_invalidation_record.get("to_plan", {}).get("digest") == runtime_plan.get("digest")
             and stale_evidence_invalidation_record.get("to_plan", {}).get("candidate_sha") == runtime_plan.get("source_binding", {}).get("pre_head_sha"),
             "RECOVERY_REPLAN_INVALIDATION_BINDING_MISMATCH")
    _verify_recovery_replan_activation_authorization(
        auth, expected_checkpoint_sha=expected_incident_checkpoint_file_sha256,
        runtime_plan=runtime_plan, successor=successor,
        recovery_replan_receipt=recovery_replan_receipt,
        invalidation=stale_evidence_invalidation_record,
    )
    try:
        UniversalController(profile=profile, runtime_plan=runtime_plan, run_state=successor,
                            node_allocation=node_allocation)
    except Exception as exc:
        code = getattr(exc, "code", "RECOVERY_REPLAN_STATE_VALIDATION_FAILED")
        raise CheckpointPersistenceError(code, str(exc)) from exc

    intended = make_checkpoint_document(run_state=successor, runtime_plan=runtime_plan,
                                       node_allocation=node_allocation)
    payload = (json.dumps(intended, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if not cp_path.exists():
        raise CheckpointPersistenceError("INCIDENT_CHECKPOINT_READ_FAILED", str(cp_path))
    try:
        current_bytes = cp_path.read_bytes()
    except OSError as exc:
        raise CheckpointPersistenceError("INCIDENT_CHECKPOINT_READ_FAILED", str(exc)) from exc
    current_sha = _file_sha(current_bytes)

    def build_activation_receipt(archive_sha: str, generation_sha: str, installed_sha: str) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_id": "gwc.universal-run.recovery-replan-cursor-activation-receipt.v2",
            "schema_version": 2,
            "activation_result": "INSTALLED",
            "authorization_digest": auth["authorization_digest"],
            "checkpoint_ref": str(cp_path),
            "prior_checkpoint_file_sha256": expected_incident_checkpoint_file_sha256,
            "corrupt_incident_archive_ref": str(archive),
            "corrupt_incident_archive_file_sha256": archive_sha,
            "recovery_generation_ref": str(generation),
            "recovery_generation_file_sha256": generation_sha,
            "checkpoint_readback_file_sha256": installed_sha,
            "run_id": successor["run_id"],
            "runtime_plan_digest": runtime_plan["digest"],
            "candidate_sha": runtime_plan["source_binding"]["pre_head_sha"],
            "sequence": successor["sequence"], "active_gate": successor["active_gate"],
            "next_owner": successor["next_owner"], "typed_next": successor["typed_next"],
            "state_digest": successor["state_digest"],
            "authority_granted": False, "executed_effects": [],
        }
        value["receipt_digest"] = _digest(value, "receipt_digest")
        _validate_schema(value, "recovery-replan-cursor-activation-receipt.schema.json",
                         "RECOVERY_REPLAN_ACTIVATION_RECEIPT_SCHEMA_INVALID")
        return value

    if current_bytes == payload:
        archive_bytes = archive.read_bytes() if archive.is_file() else b""
        generation_bytes = generation.read_bytes() if generation.is_file() else b""
        _require(_file_sha(archive_bytes) == expected_incident_checkpoint_file_sha256,
                 "RECOVERY_REPLAN_ARCHIVE_READBACK_MISMATCH")
        _require(generation_bytes == payload, "RECOVERY_REPLAN_GENERATION_READBACK_MISMATCH")
        installed_sha = _file_sha(current_bytes)
        if receipt_path.exists():
            receipt = _load_json(receipt_path, "RECOVERY_REPLAN_ACTIVATION_RECEIPT_INVALID")
            _require(receipt.get("receipt_digest") == _digest(receipt, "receipt_digest")
                     and receipt.get("authorization_digest") == auth.get("authorization_digest")
                     and receipt.get("checkpoint_readback_file_sha256") == installed_sha,
                     "RECOVERY_REPLAN_ACTIVATION_RECEIPT_BINDING_MISMATCH")
            receipt_sha = _file_sha(receipt_path.read_bytes())
        else:
            receipt = build_activation_receipt(_file_sha(archive_bytes), _file_sha(generation_bytes), installed_sha)
            receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            receipt_sha, _ = _write_immutable(receipt_path, receipt_bytes,
                                              conflict_code="RECOVERY_REPLAN_ACTIVATION_RECEIPT_CONFLICT")
        return {"idempotent_replay": True, "checkpoint_file_sha256": installed_sha,
                "activation_receipt_file_sha256": receipt_sha,
                "generation_file_sha256": _file_sha(generation_bytes),
                "archive_file_sha256": _file_sha(archive_bytes)}
    _require(current_sha == expected_incident_checkpoint_file_sha256,
             "NATIVE_CHECKPOINT_CAS_CONFLICT")
    try:
        incident = json.loads(current_bytes)
    except json.JSONDecodeError as exc:
        raise CheckpointPersistenceError("INCIDENT_CHECKPOINT_JSON_INVALID", str(exc)) from exc
    incident_state = incident.get("run_state") if isinstance(incident, Mapping) else None
    _require(isinstance(incident_state, Mapping)
             and incident_state.get("run_id") == successor.get("run_id")
             and incident_state.get("sequence") == 14
             and incident_state.get("active_gate") == "UR.G5",
             "RECOVERY_REPLAN_INCIDENT_CURSOR_MISMATCH")

    lock = cp_path.with_name(cp_path.name + ".recovery-replan.lock")
    try:
        lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CheckpointPersistenceError("RECOVERY_REPLAN_ALREADY_IN_PROGRESS") from exc
    except OSError as exc:
        raise CheckpointPersistenceError("RECOVERY_REPLAN_LOCK_FAILED", str(exc)) from exc
    try:
        _require(cp_path.read_bytes() == current_bytes, "NATIVE_CHECKPOINT_CAS_CONFLICT")
        archive_sha, _ = _write_immutable(archive, current_bytes,
                                         conflict_code="RECOVERY_REPLAN_ARCHIVE_CONFLICT")
        _require(archive_sha == expected_incident_checkpoint_file_sha256,
                 "RECOVERY_REPLAN_ARCHIVE_HASH_MISMATCH")
        generation_sha, _ = _write_immutable(generation, payload,
                                              conflict_code="RECOVERY_REPLAN_GENERATION_CONFLICT")
        _require(cp_path.read_bytes() == current_bytes, "NATIVE_CHECKPOINT_CAS_CONFLICT")
        fd, temp_name = tempfile.mkstemp(prefix=cp_path.name + ".", suffix=".tmp", dir=cp_path.parent)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            _require(cp_path.read_bytes() == current_bytes, "NATIVE_CHECKPOINT_CAS_CONFLICT")
            os.replace(temp, cp_path)
            dir_fd = os.open(cp_path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            temp.unlink(missing_ok=True)
        readback = cp_path.read_bytes()
        _require(readback == payload, "RECOVERY_REPLAN_CHECKPOINT_READBACK_MISMATCH")
        decoded = _load_json(cp_path, "RECOVERY_REPLAN_CHECKPOINT_READBACK_INVALID")
        readback_state = decoded.get("run_state")
        _require(isinstance(readback_state, Mapping), "RECOVERY_REPLAN_CHECKPOINT_READBACK_INVALID")
        _require(readback_state == successor, "RECOVERY_REPLAN_STATE_READBACK_MISMATCH")
        _require(readback_state.get("state_digest") == _digest(readback_state, "state_digest"),
                 "RECOVERY_REPLAN_STATE_READBACK_DIGEST_INVALID")
        try:
            UniversalController(profile=profile, runtime_plan=runtime_plan, run_state=readback_state,
                                node_allocation=node_allocation)
        except Exception as exc:
            code = getattr(exc, "code", "RECOVERY_REPLAN_READBACK_VALIDATION_FAILED")
            raise CheckpointPersistenceError(code, str(exc)) from exc
        receipt = build_activation_receipt(archive_sha, generation_sha, _file_sha(readback))
        receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        receipt_sha, _ = _write_immutable(receipt_path, receipt_bytes,
                                          conflict_code="RECOVERY_REPLAN_ACTIVATION_RECEIPT_CONFLICT")
        return {"idempotent_replay": False, "checkpoint_file_sha256": _file_sha(readback),
                "activation_receipt_file_sha256": receipt_sha,
                "generation_file_sha256": generation_sha, "archive_file_sha256": archive_sha}
    finally:
        os.close(lock_fd)
        lock.unlink(missing_ok=True)
