"""Crash-safe JSON reads for files another process may be rewriting.

GWC state lives in JSON files that operators, schedulers and host adapters
rewrite while a firing is reading them. A plain ``json.loads(path.read_text())``
observes the truncate-then-write window and aborts the whole activity with a
bare ``JSONDecodeError``, which surfaced as
``BLOCKED / Expecting value: line 1 column 1 (char 0)`` with no statement about
which file was racing.

``read_json`` retries the read a bounded number of times and fails closed with
``STABLE_JSON_UNREADABLE`` naming the file, so a persistent problem is reported
instead of being mistaken for a transport fault.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

DEFAULT_ATTEMPTS = 6
DEFAULT_DELAY = 0.15


def read_json(path: str | Path, attempts: int = DEFAULT_ATTEMPTS, delay: float = DEFAULT_DELAY):
    """Return the parsed JSON at ``path``, retrying a transient partial write."""
    target = Path(path)
    last: Exception | None = None
    for _ in range(max(1, attempts)):
        try:
            return json.loads(target.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            last = exc
            if delay:
                time.sleep(delay)
    raise ValueError(f"STABLE_JSON_UNREADABLE: {target}: {last}")
