#!/usr/bin/env python3
"""Q0 E2E closure package (ACK #77): P1 scope, P2 replay, P3 matrix, P4 dossier.

P1  classify every changed path against the R3 writable targets.
P2  replay the same source twice and prove the result digest is identical.
P3  map each R3 acceptance criterion to evidence and an honest status.
P4  emit one dossier JSON that the PR body and handoff cite.

The dossier is local engineering evidence. It records the absence of native
LOAD_PROOF and L3 instead of implying them.
"""

from __future__ import annotations

import fnmatch
import hashlib
import re
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = "core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json"
EVIDENCE = ROOT / ".gwc/tasks/SCRUM-781/evidence"
OUT = EVIDENCE / "q0-e2e-closure-r1.json"
SUITE = [
    "tests/test_stable_json.py",
    "tests/test_engineering_m1_m7_workflow.py",
    "tests/test_engineering_work_frontier.py",
    "tests/test_engineering_frontier_host.py",
    "tests/test_controller_exchange_adapter.py",
    "tests/test_exchange_outbox_transitions.py",
    "tests/test_q0_plan_resolution.py",
]
AC_STATUS = {
    0: ("PASS", ["core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json",
                 ".gwc/tasks/SCRUM-781/activation/cf-plan-activation.json"]),
    1: ("PASS", ["engineering_workflow", "engineering_source_reconciliations"]),
    2: ("PASS", ["core/node-architect/q0-controlled-failure-frontier-r3.json"]),
    3: ("PASS", [".gwc/tasks/SCRUM-781/evidence/cf-red-prefix-runtime-r1.json"]),
    4: ("PASS", ["commit 4a775eb1", "tests/test_stable_json.py"]),
    5: ("PARTIAL", [".gwc/tasks/SCRUM-781/evidence/cf-load-replay-certify-r1.json"]),
    6: ("PARTIAL", [".gwc/tasks/SCRUM-781/evidence/cf-load-replay-certify-r1.json"]),
    7: ("PARTIAL", [".gwc/tasks/SCRUM-781/evidence/cf-load-replay-certify-r1.json"]),
    8: ("PASS", ["DWO-LOGIN-AUTH-R1 kept NOT_REPRODUCED; no reconstructed trace used as proof"]),
    9: ("PARTIAL", [".gwc/tasks/SCRUM-781/evidence/q0-e2e-closure-r1.json#P1_scope_reconciliation"]),
    10: ("PASS", ["https://github.com/nhatnguyenquang1838-coder/gwc/pull/609", "q0-e2e-closure-r1.json"]),
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def p1_scope(plan: dict) -> dict:
    targets = list((plan.get("scope") or {}).get("writable_targets") or [])
    changed = [l for l in git("diff", "--name-only", "--diff-filter=ADM", "origin/main...HEAD").splitlines() if l]
    matched, unmatched = [], []
    for path in changed:
        if any(fnmatch.fnmatch(path, pattern) for pattern in targets):
            matched.append(path)
        else:
            unmatched.append(path)
    groups: dict[str, int] = {}
    for path in unmatched:
        top = path.split("/")[0] + ("/" + path.split("/")[1] if path.count("/") >= 1 else "")
        groups[top] = groups.get(top, 0) + 1
    return {
        "changed_files": len(changed),
        "writable_targets": targets,
        "matched": {"count": len(matched), "paths": matched},
        "unmatched": {"count": len(unmatched), "paths": unmatched, "top_level_groups": dict(sorted(groups.items(), key=lambda kv: -kv[1]))},
    }


def _run_suite() -> dict:
    proc = subprocess.run([sys.executable, "-m", "pytest", *SUITE, "-q"], cwd=ROOT,
                          capture_output=True, text=True, env={"PYTHONPATH": "", "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin:/usr/sbin:/sbin"})
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    # Drop the wall-clock suffix so the replay digest compares the RESULT, not timing.
    tail = re.sub(r" in \d+\.\d+s$", "", tail)
    return {"exit_code": proc.returncode, "summary": tail}


def p2_replay() -> dict:
    runs = [_run_suite() for _ in range(2)]
    normalized = json.dumps(runs, sort_keys=True).encode()
    return {
        "runs": runs,
        "result_digest": "sha256:" + sha(normalized),
        "deterministic": runs[0] == runs[1],
        "source_head": git("rev-parse", "HEAD"),
        "boundary": "same source + same suites replayed twice; not an original DWO replay",
    }


def p3_matrix(plan: dict) -> dict:
    criteria = list(plan.get("acceptance_criteria") or [])
    rows = []
    for index, text in enumerate(criteria):
        status, refs = AC_STATUS.get(index, ("NOT_ASSESSED", []))
        rows.append({"index": index, "criterion": text, "status": status, "evidence": refs})
    return {
        "criteria_count": len(criteria),
        "rows": rows,
        "counts": {s: sum(1 for r in rows if r["status"] == s) for s in ("PASS", "PARTIAL", "NOT_ASSESSED")},
        "native_load_proof": "ABSENT",
        "original_dwo_replay": "NOT_REPRODUCED",
        "l3_certification": "NOT_CLAIMED",
        "human_g6": "NOT_ACCEPTED",
    }


def main() -> int:
    plan = json.loads((ROOT / PLAN).read_text())
    dossier = {
        "schema_id": "gwc.q0.e2e-closure/v1",
        "ack": 77,
        "run_id": plan.get("run_id"),
        "source_head": git("rev-parse", "HEAD"),
        "P1_scope_reconciliation": p1_scope(plan),
        "P2_deterministic_replay": p2_replay(),
        "P3_qualification_matrix": p3_matrix(plan),
        "claim_boundary": "local engineering evidence; no native LOAD_PROOF, no original DWO replay, no L3, no gate receipt",
    }
    raw = json.dumps(dossier, indent=1, sort_keys=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(raw + "\n")
    print(json.dumps({
        "artifact": str(OUT.relative_to(ROOT)),
        "artifact_sha256": "sha256:" + sha(raw.encode()),
        "changed_files": dossier["P1_scope_reconciliation"]["changed_files"],
        "unmatched_files": dossier["P1_scope_reconciliation"]["unmatched"]["count"],
        "deterministic": dossier["P2_deterministic_replay"]["deterministic"],
        "matrix_counts": dossier["P3_qualification_matrix"]["counts"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
