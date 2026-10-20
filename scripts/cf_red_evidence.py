#!/usr/bin/env python3
"""Produce genuine RED evidence for the partial-JSON-read defect.

Two independent sources are recorded:

1. OBSERVED runtime failures — the pre-fix CLI's own BLOCKED outputs captured at
   ticks 175/176/177, hashed and cited by path. Those firings really aborted.
2. SOURCE-EXACT reproduction — the pre-fix read statement is extracted verbatim
   from the pre-fix commit, executed against an empty file, and its traceback is
   captured. The executed statement and digest are stored in the artifact.

A full pre-fix CLI re-run is deliberately not used: the CLI binds its own
repository path and refuses to run from an extracted snapshot
(Q0_WORKTREE_BINDING_MISMATCH), so such a run would prove nothing.

Local engineering evidence only: no native receipt, no typed C-E authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRE_FIX_COMMIT = "91ca8e92"
FIX_COMMIT = "20239524"
WORKFLOW = "tools/node_architect/engineering_m1_m7_workflow.py"
ROUTE_REF = "core/node-architect/q0-engineering-coordination-route-r1.json"
CHECKPOINTS = Path.home() / ".hermes/loop-checkpoints/scrum781-q0-fresh-20261010-r1"
OBSERVED = ["native175-cli-actual.json", "native176-cli-actual.json", "native177-cli-actual.json"]
ARTIFACT = ROOT / ".gwc/tasks/SCRUM-781/evidence/cf-red-prefix-runtime-r1.json"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def observed_runtime_failures() -> list[dict]:
    rows = []
    for name in OBSERVED:
        path = CHECKPOINTS / name
        if not path.exists():
            rows.append({"artifact": name, "present": False})
            continue
        raw = path.read_bytes()
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {}
        rows.append({
            "artifact": str(path), "present": True, "sha256": "sha256:" + sha(raw),
            "outcome": body.get("outcome"), "reason_code": body.get("reason_code"),
            "native_state_modified": body.get("native_state_modified"),
        })
    return rows


def source_exact_reproduction() -> dict:
    pre = subprocess.check_output(["git", "rev-parse", PRE_FIX_COMMIT], cwd=ROOT, text=True).strip()
    source = subprocess.check_output(["git", "show", f"{pre}:{WORKFLOW}"], cwd=ROOT).decode()
    line = next(l.strip() for l in source.splitlines() if l.strip().startswith("route=json.loads("))
    driver = (
        "import json,pathlib,traceback\n"
        f"root=pathlib.Path({str(ROOT)!r})\n"
        f"ROUTE_REF={ROUTE_REF!r}\n"
        "try:\n"
        f"    {line}\n"
        "    print('NO_FAILURE')\n"
        "except Exception:\n"
        "    traceback.print_exc(); raise SystemExit(3)\n"
    )
    import tempfile
    with tempfile.TemporaryDirectory(prefix="cf-red-root-") as tmp:
        # Never truncate the real repository file: reproduce in a sandbox root
        # that holds the same relative path.
        sandbox = Path(tmp)
        (sandbox / ROUTE_REF).parent.mkdir(parents=True, exist_ok=True)
        (sandbox / ROUTE_REF).write_text("")   # truncate window: reader sees empty file
        sandboxed = driver.replace(str(ROOT), str(sandbox))
        proc = subprocess.run([sys.executable, "-c", sandboxed], capture_output=True, text=True,
                              env={**os.environ, "PYTHONPATH": ""}, timeout=120)
        empty_sha = "sha256:" + sha(b"")
    return {
        "pre_fix_commit": pre,
        "pre_fix_file_sha256": "sha256:" + sha(source.encode()),
        "executed_statement": line,
        "input": {"file": ROUTE_REF, "content": "", "sha256": empty_sha},
        "exit_code": proc.returncode,
        "error_boundary": (proc.stderr.strip().splitlines() or [""])[-1],
        "stderr_tail": proc.stderr.strip().splitlines()[-4:],
        "failed": proc.returncode != 0 and "Expecting value" in proc.stderr,
    }


def main() -> int:
    observed = observed_runtime_failures()
    repro = source_exact_reproduction()
    genuine_observed = [r for r in observed if (r.get("reason_code") or "").startswith("Expecting value")]
    artifact = {
        "schema_id": "gwc.q0.cf.red/v1",
        "scenario": ".gwc/tasks/SCRUM-781/evidence/cf-scenario-stable-json-r1.json",
        "defect": "P1 host read of a JSON file inside its truncate-then-write window",
        "fix": {"commit": subprocess.check_output(["git", "rev-parse", FIX_COMMIT], cwd=ROOT, text=True).strip(),
                "module": "tools/node_architect/stable_json.py"},
        "observed_runtime_failures": observed,
        "source_exact_reproduction": repro,
        "observed_note": ("the tick 175/176/177 BLOCKED outputs were overwritten by later "
                          "successful runs of the same checkpoint files, so they are not claimed "
                          "as preserved evidence; the reproduction below is the preserved RED"),
        "is_genuine_red": repro["failed"],
        "claim_boundary": "local engineering evidence only; no native LOAD_PROOF, L3 or gate receipt",
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(artifact, indent=1, sort_keys=True)
    ARTIFACT.write_text(raw + "\n")
    print(json.dumps({
        "artifact": str(ARTIFACT.relative_to(ROOT)),
        "artifact_sha256": "sha256:" + sha(raw.encode()),
        "observed_failures": len(genuine_observed),
        "source_exact_exit": repro["exit_code"],
        "is_genuine_red": artifact["is_genuine_red"],
    }))
    return 0 if artifact["is_genuine_red"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
