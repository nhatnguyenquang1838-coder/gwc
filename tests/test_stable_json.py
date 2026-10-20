import json
import threading
import time
from pathlib import Path

import pytest


def _rewrite_later(path: Path, payload: dict, delay: float = 0.05) -> threading.Thread:
    def run() -> None:
        time.sleep(delay)
        path.write_text(json.dumps(payload))

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_naive_read_of_a_partially_written_file_raises(tmp_path):
    """RED: the pre-fix read path aborts on a transient truncation."""
    target = tmp_path / "route.json"
    target.write_text("")
    with pytest.raises(json.JSONDecodeError):
        json.loads(target.read_text())


def test_read_json_survives_an_atomic_rewrite_window(tmp_path):
    """Read while the writer is mid-rewrite, not after it finished."""
    from tools.node_architect.stable_json import read_json

    target = tmp_path / "route.json"
    target.write_text(json.dumps({"route": "before"}))
    stop = threading.Event()

    def writer() -> None:
        payload = json.dumps({"route": "after", "filler": "x" * 2000})
        for _ in range(60):
            if stop.is_set():
                return
            target.write_text("")       # truncate window a reader can observe
            target.write_text(payload)
            time.sleep(0.002)

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    try:
        observed = []
        for _ in range(40):
            observed.append(read_json(target, attempts=6, delay=0.02)["route"])
    finally:
        stop.set()
        thread.join(timeout=5)
    assert observed and set(observed) <= {"before", "after"}


def test_read_json_retries_within_the_same_call(tmp_path, monkeypatch):
    from tools.node_architect import stable_json

    target = tmp_path / "plan.json"
    target.write_text('{"a": 1}')  # valid payload once the truncation window closes
    calls = {"n": 0}
    real_loads = json.loads

    def flaky(raw, *a, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise json.JSONDecodeError("truncated", raw, 0)
        return real_loads(raw, *a, **kw)

    monkeypatch.setattr(stable_json.json, "loads", flaky)
    assert stable_json.read_json(target, attempts=5, delay=0.0) == {"a": 1}


def test_read_json_fails_closed_when_the_file_stays_unreadable(tmp_path):
    from tools.node_architect.stable_json import read_json

    target = tmp_path / "broken.json"
    target.write_text("{not json")
    with pytest.raises(ValueError, match="STABLE_JSON_UNREADABLE"):
        read_json(target, attempts=3, delay=0.0)


def test_workflow_route_read_fails_closed_instead_of_raising_json_error(tmp_path):
    from tools.node_architect.stable_json import read_json

    target = tmp_path / "q0-engineering-coordination-route-r1.json"
    target.write_text("")
    with pytest.raises(ValueError, match="STABLE_JSON_UNREADABLE"):
        read_json(target, attempts=2, delay=0.0)
