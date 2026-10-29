"""RED #3 — a duplicate send must be blocked when a prior send is unresolved.

If the checkpoint holds `m7_status = SEND_NOT_VERIFIED` and a marker hash, the
workflow must not emit another CAN_SEND even if the browser looks writable.
"""
import pytest

from q0_loop_agent.workflow import run_tick

TICK_BASE = {
    "run_id": "scrum781-q0-fresh-20261010-r1",
    "session_id": "test-session",
    "profile": "default",
    "gpt_url": "https://chatgpt.com/g/g-p-6a622940beac81918180ce69e50ef83c-dw-super/c/6accef27-fbe0-83ec-88f1-40347dc2b3f1",
}


def test_duplicate_send_blocked_when_equivalent_marker_pending():
    tick = {
        **TICK_BASE,
        "state": {
            "m7_status": "SEND_NOT_VERIFIED",
            "m7_marker_sha256": "de7e03ade2797765d4675cd7bbfc09b61755e104f204cd8f7ae7010ee45cc2f6",
        },
        "browser": {
            "url_verified": True,
            "fresh_full_inventory": True,
            "elements": {"added": ["btn-send"]},
            "composer_value": "",  # verified empty
            "send_ref_fresh": "btn-send",
        },
    }
    verdict = run_tick(tick)
    assert verdict["can_send"] is False
    assert verdict["state"] == "M7_PENDING_PRIOR_UNVERIFIED"
