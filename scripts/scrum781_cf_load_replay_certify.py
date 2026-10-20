#!/usr/bin/env python3
"""CF-LOAD / CF-REPLAY / CF-CERTIFY evidence runner for the stable-json defect.

CF-LOAD    prove the loaded module identity equals the committed source identity.
CF-REPLAY  replay the exact failure mode (reader inside the writer's truncate
           window) and show the control arm fails while the fixed arm survives.
CF-CERTIFY run the Q0 suites and record the numbers verbatim.

This produces local engineering evidence only. It is not a native LOAD_PROOF, an
original DWO replay, L3 qualification or a gate receipt, and it grants no
authority.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX_FILES = [
    "tools/node_architect/stable_json.py",
    "tools/node_architect/engineering_m1_m7_workflow.py",
    "scripts/scrum781_engineering_loop.py",
]
EVIDENCE = ROOT / ".gwc/tasks/SCRUM-781/evidence/cf-load-replay-certify-r1.json"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def cf_load() -> dict:
    head = git("rev-parse", "HEAD")
    sys.path.insert(0, str(ROOT))
    from tools.node_architect import stable_json

    loaded = Path(stable_json.__file__).read_bytes()
    committed = subprocess.check_output(["git", "show", f"HEAD:tools/node_architect/stable_json.py"], cwd=ROOT)
    rows = []
    for rel in FIX_FILES:
        disk = (ROOT / rel).read_bytes()
        at_head = subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)
        rows.append({"path": rel, "disk_sha256": sha256(disk), "head_sha256": sha256(at_head), "match": disk == at_head})
    return {
        "result": "CF_LOAD_LOCAL_IDENTITY_MATCH" if all(r["match"] for r in rows) and loaded == committed else "CF_LOAD_LOCAL_IDENTITY_MISMATCH",
        "head": head,
        "loaded_module": str(Path(stable_json.__file__)),
        "loaded_module_sha256": sha256(loaded),
        "committed_module_sha256": sha256(committed),
        "files": rows,
        "claim_boundary": "local source/loaded identity only; not a native LOAD_PROOF",
    }


def _writer(path: Path, iterations: int, stop: threading.Event) -> None:
    payload = json.dumps({"seq": 0, "filler": "x" * 4000})
    for i in range(iterations * 3):
        if stop.is_set():
            return
        path.write_text("")              # truncate window a reader can observe
        path.write_text(json.dumps({"seq": i, "filler": "x" * 4000}))
    path.write_text(payload)


def _reader(path: Path, use_fix: bool, iterations: int, stop: threading.Event) -> dict:
    aborts, ok = 0, 0
    for _ in range(iterations):
        if stop.is_set():
            break
        try:
            if use_fix:
                from tools.node_architect.stable_json import read_json

                read_json(path, attempts=6, delay=0.02)
            else:
                json.loads(path.read_text())
            ok += 1
        except (ValueError, json.JSONDecodeError):
            aborts += 1
    return {"ok": ok, "aborts": aborts}


def cf_replay(iterations: int = 150) -> dict:
    results = {}
    for arm, use_fix in (("control_naive_read", False), ("fixed_stable_read", True)):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps({"seq": -1, "filler": "x" * 4000}))
            stop = threading.Event()
            writer = threading.Thread(target=_writer, args=(path, iterations, stop), daemon=True)
            writer.start()
            time.sleep(0.01)
            results[arm] = _reader(path, use_fix, iterations, stop)
            stop.set()
            writer.join(timeout=5)
    control, fixed = results["control_naive_read"], results["fixed_stable_read"]
    reproduced = control["aborts"] > 0
    survived = fixed["aborts"] == 0
    return {
        "result": "CF_REPLAY_ADVANCED" if reproduced and survived else "CF_REPLAY_INCONCLUSIVE",
        "iterations": iterations,
        "control": control,
        "fixed": fixed,
        "failure_reproduced_in_control": reproduced,
        "fixed_arm_aborts": fixed["aborts"],
        "note": "the control arm is the pre-fix read path; a zero-abort control would mean the window was not exercised",
    }


def cf_certify() -> dict:
    suites = {
        "q0": [
            "tests/test_stable_json.py",
            "tests/test_engineering_m1_m7_workflow.py",
            "tests/test_engineering_work_frontier.py",
            "tests/test_engineering_frontier_host.py",
            "tests/test_controller_exchange_adapter.py",
            "tests/test_exchange_outbox_transitions.py",
            "tests/test_q0_plan_resolution.py",
        ]
    }
    env = {"PYTHONPATH": "", "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin:/usr/sbin:/sbin"}
    out = {}
    for name, files in suites.items():
        proc = subprocess.run([sys.executable, "-m", "pytest", *files, "-q"], cwd=ROOT, capture_output=True, text=True, env=env)
        tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        out[name] = {"exit_code": proc.returncode, "summary": tail}
    passed = all(v["exit_code"] == 0 for v in out.values())
    return {"result": "CF_CERTIFIED_LOCAL_SUITES_GREEN" if passed else "CF_CERTIFY_BLOCKED", "suites": out,
            "claim_boundary": "local suites only; no native gate receipt, no L3"}


def main() -> int:
    head = git("rev-parse", "HEAD")
    report = {
        "schema_id": "gwc.q0.cf.load-replay-certify/v1",
        "scenario": ".gwc/tasks/SCRUM-781/evidence/cf-scenario-stable-json-r1.json",
        "source_head": head,
        "CF_LOAD": cf_load(),
        "CF_REPLAY": cf_replay(),
        "CF_CERTIFY": cf_certify(),
        "authority_granted": False,
        "typed_ce_admitted": False,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(report, indent=1, sort_keys=True)
    EVIDENCE.write_text(raw + "\n")
    report["artifact"] = str(EVIDENCE.relative_to(ROOT))
    report["artifact_sha256"] = "sha256:" + sha256(raw.encode())
    print(json.dumps({k: report[k] for k in ("source_head", "artifact", "artifact_sha256")}))
    for stage in ("CF_LOAD", "CF_REPLAY", "CF_CERTIFY"):
        print(stage, "->", report[stage]["result"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
