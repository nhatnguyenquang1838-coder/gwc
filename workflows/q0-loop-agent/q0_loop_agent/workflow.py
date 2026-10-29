"""Q0 Loop Agent — fail-closed per-tick decision state machine.

Implements the M7 UI recovery guard as runtime-checked deterministic logic:

1. A tick without a fresh full element inventory (after an authorized reload)
   is NEVER accepted: controls stay UNKNOWN and the tick is M7_PENDING.
2. A `same:N` / `SAME:XX` elements payload is NEVER used as inventory evidence,
   element identity, unchanged-state signal, liveness, composer value, or Send
   state — it is discarded.
3. A prior `SEND_NOT_VERIFIED` with a stored marker blocks any new send until
   the pending-send ambiguity is resolved.

This module contains pure decision logic only (no browser, no I/O). The
LangGraph wrapper adds state persistence, evidence and GraphNode contracts.
"""
from __future__ import annotations

from typing import Any, Dict


def _is_same_n_only(payload: Any) -> bool:
    """True when the elements payload is a same:N/SAME:XX delta only."""
    if not isinstance(payload, dict):
        return False
    delta = payload.get("delta")
    return isinstance(delta, str) and delta.lower().startswith("same:")


def classify_browser(tick: Dict[str, Any]) -> Dict[str, Any]:
    """Fail-closed classification of one tick's browser evidence."""
    browser = tick.get("browser") or {}
    elements = browser.get("elements")
    fresh = browser.get("fresh_full_inventory") is True

    same_only = _is_same_n_only(elements)
    accepted = fresh and not same_only

    if not accepted:
        controls = {"composer": "UNKNOWN", "send": None}
        state = "M7_PENDING_UNKNOWN_CONTROLS"
        can_send = False
    else:
        composer = browser.get("composer_value")
        composer_known = composer is not None
        send_ref = browser.get("send_ref_fresh")
        if not send_ref and isinstance(elements, dict):
            added = elements.get("added")
            if isinstance(added, list):
                for item in added:
                    if isinstance(item, dict) and str(
                        item.get("ref", "")
                    ).lower().startswith("btn-send"):
                        send_ref = item.get("ref")
        controls = {
            "composer": composer if composer_known else "UNKNOWN",
            "send": send_ref,
        }
        can_send = bool(send_ref)
        state = "M7_READY_TO_STAGE" if can_send else "M7_PENDING_UNKNOWN_CONTROLS"

    return {
        "elements_accepted": accepted,
        "controls": controls,
        "state": state,
        "can_send": can_send,
    }


def run_tick(tick: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate one tick's browser evidence and prior checkpoint state."""
    verdict = classify_browser(tick)

    prior = tick.get("state") or {}
    if prior.get("m7_status") == "SEND_NOT_VERIFIED" and prior.get(
        "m7_marker_sha256"
    ):
        verdict["can_send"] = False
        verdict["state"] = "M7_PENDING_PRIOR_UNVERIFIED"

    return verdict
