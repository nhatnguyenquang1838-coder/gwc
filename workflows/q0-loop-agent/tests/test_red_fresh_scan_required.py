"""RED #1 — a tick without a fresh URL scan must be fail-closed.

Rule (runtime-enforced): never trust or use any `same:N` / `SAME:XX` result as
current inventory. A tick that carries only a delta (no fresh full inventory
after reload) may not proceed to compose/send; controls are UNKNOWN and the
tick stays M7_PENDING.
"""
import pytest

from q0_loop_agent.workflow import run_tick

TICK_BASE = {
    "run_id": "scrum781-q0-fresh-20261010-r1",
    "session_id": "test-session",
    "profile": "default",
    "gpt_url": "https://chatgpt.com/g/g-p-6a622940beac81918180ce69e50ef83c-dw-super/c/6accef27-fbe0-83ec-88f1-40347dc2b3f1",
}


def test_tick_without_fresh_url_scan_is_rejected():
    tick = {
        **TICK_BASE,
        "browser": {
            "url_verified": True,
            "fresh_full_inventory": False,  # only a delta was returned this tick
            "elements": {"delta": "same:19"},
            "composer_value": "UNKNOWN",
            "send_ref_fresh": None,
        },
    }
    verdict = run_tick(tick)
    assert verdict["can_send"] is False
    assert verdict["state"] == "M7_PENDING_UNKNOWN_CONTROLS"
    assert verdict["controls"]["composer"] == "UNKNOWN"
    assert verdict["controls"]["send"] is None
    assert verdict["elements_accepted"] is False
