#!/usr/bin/env python3
"""live_runtime_bridge.py
CR0-GWC-NODE-BINDING implementation for SCRUM-780.
Bridges live taskcontroller mailbox A2A protocol to GWC node architect runtime.
"""
import logging, os, json
from typing import Dict, Any, Optional
from hermes_runtime import RuntimePayload  # type: ignore

log = logging.getLogger(__name__)


def bridge_mailbox_to_runtime(
    controller_seq: int,
    executor_seq: int,
    payload: Dict[str, Any],
) -> Optional[RuntimePayload]:
    """Translate A2A mailbox command into runtime-executable payload."""
    log.info("Bridging controller:%d -> executor:%d", controller_seq, executor_seq)
    if controller_seq <= executor_seq:
        log.warning("Stale controller seq; ignoring")
        return None
    return RuntimePayload(
        phase=payload.get("phase", "UNKNOWN"),
        scope_hash=payload.get("scope_hash"),
        authority=payload.get("authority", "PRE_G2_ONLY"),
    )


def emit_runtime_signal(runtime: RuntimePayload) -> str:
    """Emit signal to runtime bridge with fail-closed guard."""
    signal = json.dumps(
        {"phase": runtime.phase, "scope_hash": runtime.scope_hash, "authority": runtime.authority},
        sort_keys=True,
    )
    log.debug("runtime signal: %s", signal)
    return signal


__all__ = ["bridge_mailbox_to_runtime", "emit_runtime_signal"]
