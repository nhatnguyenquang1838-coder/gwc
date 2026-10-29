"""RED #2 — a `same:N` payload must never populate control bindings.

Even when a caller labels a result "fresh", a same:N-only elements payload
carries no element identities and must never be used to bind composer/Send.
"""
import pytest

from q0_loop_agent.workflow import run_tick

TICK_BASE = {
    "run_id": "scrum781-q0-fresh-20261010-r1",
    "session_id": "test-session",
    "profile": "default",
    "gpt_url": "https://chatgpt.com/g/g-p-6a622940beac81918180ce69e50ef83c-dw-super/c/6accef27-fbe0-83ec-88f1-40347dc2b3f1",
}


def test_same_n_never_used_as_inventory_evidence():
    tick = {
        **TICK_BASE,
        "browser": {
            "url_verified": True,
            "fresh_full_inventory": True,  # caller claims fresh…
            "elements": {"delta": "same:19"},  # …but payload is same:N only
            "composer_value": "UNKNOWN",
            "send_ref_fresh": "btn-send-stale",
        },
    }
    verdict = run_tick(tick)
    assert verdict["elements_accepted"] is False
    assert verdict["controls"]["composer"] == "UNKNOWN"
    assert verdict["controls"]["send"] is None  # stale ref must not be used
    assert verdict["can_send"] is False
