"""Canonical adapter for the distinct Universal Run (UR.G0..UR.G6) namespace.

This is a semantic adapter only: it never performs protected effects or grants
authority. G2 delegates to C3 and remains held when its trust anchor is absent.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

UR_ACTIONS = {
    "UR.G0": "UNDERSTAND", "UR.G1": "PLAN", "UR.G2": "EXECUTE",
    "UR.G3": "VERIFY", "UR.G4": "INTEGRATE",
    "UR.G5": "VALIDATE-IN-TARGET", "UR.G6": "ACCEPT/HANDOFF",
}


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _valid_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(
        c in "0123456789abcdef" for c in value[7:]
    )


def accept_parent_g6(*, parent_run_id: str, target_contract: Mapping[str, Any],
                     internal_store: Mapping[str, Any] | None = None,
                     receipts_persisted: bool = False) -> dict[str, Any]:
    """Accept a parent target contract from host-owned persisted ChildRun records.

    This is a Consumer decision, not C2 effect authority. Caller-supplied status
    objects are deliberately not an input to this API.
    """
    children = target_contract.get("required_children") if isinstance(target_contract, Mapping) else None
    target_id = target_contract.get("target_id") if isinstance(target_contract, Mapping) else None
    if (not isinstance(parent_run_id, str) or not parent_run_id
            or not isinstance(target_contract, Mapping)
            or target_contract.get("run_id") != parent_run_id
            or target_contract.get("schema_version") != "1.0"
            or not isinstance(target_id, str) or not target_id.strip()
            or not isinstance(children, list)
            or any(not isinstance(child, str) or not child for child in children)
            or len(children) != len(set(children))):
        return {"status": "BLOCKED", "reason_code": "TARGET_CONTRACT_INVALID",
                "parent_run_id": parent_run_id if isinstance(parent_run_id, str) else "",
                "parent_receipt": None, "authority_granted": False, "accepted_child_run_ids": []}
    accepted: list[str] = []
    if children:
        receipts = internal_store.get("run_receipts") if isinstance(internal_store, Mapping) else None
        gates = internal_store.get("gates") if isinstance(internal_store, Mapping) else None
        manifests = internal_store.get("child_manifests") if isinstance(internal_store, Mapping) else None
        child_contracts = internal_store.get("target_contracts") if isinstance(internal_store, Mapping) else None
        try:
            from .checkpoint_store import digest_payload
            checkpoints = internal_store.get("checkpoints") if isinstance(internal_store, Mapping) else None
            expected_store_digest = digest_payload({
                "revision": internal_store.get("revision", 0), "binding": internal_store.get("binding"),
                "lease_binding": internal_store.get("lease_binding"), "events": internal_store.get("events", []),
                "checkpoints": checkpoints if isinstance(checkpoints, Mapping) else {},
                "effects": internal_store.get("effects", {}),
            })
            sealed_states = [record.get("state") for record in checkpoints.values()
                             if isinstance(record, Mapping) and str(record.get("node_id", "")).startswith("recursive-dag:")
                             and isinstance(record.get("state"), Mapping)
                             and digest_payload(record["state"]) == record.get("state_digest")]
            latest_state = sealed_states[-1] if sealed_states else None
            internal_valid = (
                receipts_persisted is True and isinstance(receipts, Mapping) and isinstance(gates, Mapping)
                and isinstance(manifests, Mapping) and isinstance(child_contracts, Mapping)
                and internal_store.get("store_digest") == expected_store_digest
                and isinstance(latest_state, Mapping)
                and latest_state.get("run_receipts") == receipts and latest_state.get("gates") == gates
                and latest_state.get("child_manifests") == manifests
                and latest_state.get("target_contracts") == child_contracts
            )
        except Exception:
            internal_valid = False
        if not internal_valid:
            return {"status": "BLOCKED", "reason_code": "PERSISTED_CHILD_RECEIPTS_REQUIRED",
                    "parent_run_id": parent_run_id, "parent_receipt": None,
                    "authority_granted": False, "accepted_child_run_ids": []}
        for child_id in children:
            receipt = receipts.get(child_id)
            child_gates = gates.get(child_id) if isinstance(gates, Mapping) else None
            child_manifest = manifests.get(child_id) if isinstance(manifests, Mapping) else None
            child_contract = child_contracts.get(child_id) if isinstance(child_contracts, Mapping) else None
            if (not isinstance(child_manifest, Mapping) or child_manifest.get("run_id") != child_id
                    or child_manifest.get("parent_run_ref") != parent_run_id
                    or not isinstance(child_contract, Mapping)
                    or child_contract.get("schema_version") != "1.0"
                    or child_contract.get("run_id") != child_id
                    or child_contract.get("target_id") != target_id
                    or not isinstance(receipt, Mapping) or receipt.get("status") != "COMPLETED"
                    or receipt.get("run_id") != child_id
                    or not isinstance(receipt.get("g6_receipt"), Mapping)
                    or receipt["g6_receipt"].get("status") != "ACCEPTED"
                    or not isinstance(child_gates, Mapping)
                    or any(not isinstance(child_gates.get(g), Mapping) for g in ("G3", "G4", "G5"))
                    or any((child_gates[g].get("target_readback") or {}).get("status") != "VERIFIED" for g in ("G4", "G5"))):
                return {"status": "BLOCKED", "reason_code": "PERSISTED_CHILD_RECEIPT_INVALID",
                        "parent_run_id": parent_run_id, "parent_receipt": None,
                        "authority_granted": False, "accepted_child_run_ids": []}
            accepted.append(child_id)
    contract_digest = _digest(dict(target_contract))
    body = {"artifact_type": "parent-g6-consumer-receipt", "schema_version": "1.0",
            "parent_run_id": parent_run_id, "target_id": target_id,
            "target_contract_digest": contract_digest, "accepted_child_run_ids": accepted,
            "authority_granted": False}
    receipt = {**body, "receipt_id": _digest(body)}
    return {"status": "ACCEPTED", "reason_code": "TARGET_CONTRACT_ACCEPTED",
            "parent_run_id": parent_run_id, "parent_receipt": receipt,
            "g6_receipt": {"status": "ACCEPTED", "receipt_id": receipt["receipt_id"]},
            "authority_granted": False, "accepted_child_run_ids": accepted}


def handle_gate(*, gate: str, action: str, run_id: str, manifest: Mapping[str, Any],
                target_contract: Mapping[str, Any], authority: Mapping[str, Any] | None = None,
                effect_router: Any = None,
                internal_store: Mapping[str, Any] | None = None,
                receipts_persisted: bool = False) -> dict[str, Any]:
    """Handle one canonical UR gate without aliasing GWC effect gates."""
    expected = UR_ACTIONS.get(gate)
    if expected is None or action != expected:
        return {"status": "BLOCKED", "reason_code": "UNIVERSAL_RUN_ROUTE_INVALID"}
    if (not isinstance(manifest, Mapping) or manifest.get("run_id") != run_id
            or manifest.get("run_kind") not in {"ROOT", "CHILD"}
            or not isinstance(target_contract, Mapping)
            or target_contract.get("run_id") != run_id):
        return {"status": "BLOCKED", "reason_code": "UNIVERSAL_RUN_IDENTITY_OR_TARGET_INVALID"}
    if manifest.get("run_kind") == "ROOT" and manifest.get("parent_run_ref") is not None:
        return {"status": "BLOCKED", "reason_code": "UNIVERSAL_RUN_MANIFEST_INVALID"}
    if manifest.get("run_kind") == "CHILD" and not manifest.get("parent_run_ref"):
        return {"status": "BLOCKED", "reason_code": "UNIVERSAL_RUN_MANIFEST_INVALID"}
    if gate == "UR.G2":
        if effect_router is None:
            return {"status": "EFFECT_HOLD",
                    "reason_code": "AUTHORITY_TRUST_ANCHOR_UNAVAILABLE",
                    "authority_granted": False}
        decision = effect_router(authority=authority, manifest=manifest,
                                 target_contract=target_contract, action=action)
        return dict(decision) if isinstance(decision, Mapping) else {
            "status": "EFFECT_HOLD", "reason_code": "EFFECT_DECISION_INVALID",
            "authority_granted": False}
    if gate == "UR.G6":
        return accept_parent_g6(
            parent_run_id=run_id, target_contract=target_contract,
            internal_store=internal_store, receipts_persisted=receipts_persisted,
        )
    return {"status": "ROUTE_SELECTED", "gate": gate, "action": action,
            "run_id": run_id, "authority_granted": False,
            "effect_performed": False, "next_semantic": expected}


__all__ = ["UR_ACTIONS", "accept_parent_g6", "handle_gate"]
