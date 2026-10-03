"""Active Universal Runtime v2 continuation contract regressions."""
from __future__ import annotations

from inspect import signature

import pytest

from tools.node_architect.universal_run_continuation import (
    continue_from_native_state,
    recover_from_native_checkpoint,
)


def test_continuation_api_accepts_native_state_not_mailbox_cursor_inputs():
    params = set(signature(continue_from_native_state).parameters)

    assert params == {
        "profile",
        "runtime_plan",
        "run_state",
        "node_allocation",
        "executor_receipt",
    }
    assert not params.intersection(
        {
            "history_controller",
            "consumer_cursor",
            "mailbox_cursor",
            "mailbox_expected_executor_seq",
        }
    )


def test_checkpoint_recovery_rejects_mailbox_only_projection():
    with pytest.raises(ValueError, match="NATIVE_CHECKPOINT_BINDING_INVALID"):
        recover_from_native_checkpoint(
            profile={},
            checkpoint={"mailbox_cursor": {"seq": "C91", "active_gate": "G1"}},
            node_allocation={},
        )
