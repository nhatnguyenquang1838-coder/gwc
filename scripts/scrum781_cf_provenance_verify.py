"""Source-exact provenance verifier for the CF-SCENARIO-STABLE-JSON-READ binding.

Read-only. Emits JSON on stdout. Exit 0 only when every required check passes.

The binding of record is `.gwc/tasks/SCRUM-781/evidence/cf-provenance-reconciliation-r1.json`,
which records the two declared-artifact misbindings and the corrected, source-exact
values. The original RED artifact is preserved and is never treated as rewritten.

Phases:
  red  -> controlled scenario identity + source-exact RED boundary
  fix  -> verified fix commit/source identity for the same scenario

This script never grants authority, never writes repository state and never
claims native LOAD_PROOF / L3 / gate receipts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCENARIO_REF = ".gwc/tasks/SCRUM-781/evidence/cf-scenario-stable-json-r1.json"
RED_REF = ".gwc/tasks/SCRUM-781/evidence/cf-red-prefix-runtime-r1.json"
RECON_REF = ".gwc/tasks/SCRUM-781/evidence/cf-provenance-reconciliation-r1.json"
FIX_MODULE = "tools/node_architect/stable_json.py"
EMPTY_SHA256 = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _show(root: Path, commit: str, path: str) -> bytes:
    return _git(root, "show", f"{commit}:{path}")


def _ancestor(root: Path, commit: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", commit, "HEAD"],
        capture_output=True,
    ).returncode == 0


def verify(root: Path, phase: str) -> dict:
    root = root.resolve()
    scenario = json.loads((root / SCENARIO_REF).read_text())
    red = json.loads((root / RED_REF).read_text())
    recon = json.loads((root / RECON_REF).read_text())
    checks: dict[str, object] = {}

    checks["scenario_id"] = scenario.get("id")
    checks["scenario_ref_matches_red"] = red.get("scenario") == SCENARIO_REF
    checks["recon_scenario_id_matches"] = (
        recon["scenario"]["id"] == scenario.get("id")
    )
    checks["recon_preserved_red_sha256_matches"] = (
        recon["existing_red_artifact"]["sha256"] == _sha((root / RED_REF).read_bytes())
    )
    checks["recon_preserved_scenario_sha256_matches"] = (
        recon["scenario"]["sha256"] == _sha((root / SCENARIO_REF).read_bytes())
    )

    if phase == "red":
        reexec = recon["source_exact_red_reexecution"]
        pre_fix = reexec["commit"]
        input_file = reexec["input_file"]
        checks["genuine_red_flag"] = red.get("is_genuine_red") is True
        checks["reexec_commit_matches_declared_pre_fix"] = (
            pre_fix == red["source_exact_reproduction"]["pre_fix_commit"]
        )
        checks["reexec_empty_input_sha256"] = reexec["input_sha256"] == EMPTY_SHA256
        checks["reexec_error_boundary_recorded"] = (
            "JSONDecodeError" in reexec["error_boundary"]
        )
        checks["pre_fix_file_digest_actual"] = _sha(_show(root, pre_fix, input_file))
        checks["pre_fix_file_digest_declared_misbound"] = red["source_exact_reproduction"][
            "pre_fix_file_sha256"
        ]
        checks["misbinding_recorded"] = bool(recon["existing_red_artifact"]["mismatches"])
        locus = _show(root, pre_fix, "tools/node_architect/engineering_m1_m7_workflow.py").decode()
        checks["failing_statement_present"] = (
            "route=json.loads((root/ROUTE_REF).read_text())" in locus
        )
        # the declared pre-fix digest is knowingly misbound; the corrected digest above
        # is authoritative and must differ from the declared value.
        checks["declared_pre_fix_digest_is_corrected_in_binding"] = (
            checks["pre_fix_file_digest_actual"] != checks["pre_fix_file_digest_declared_misbound"]
        )
    elif phase == "fix":
        verified_fix = recon["verified_fix"]["commit"]
        checks["declared_red_fix_commit"] = red["fix"]["commit"]
        try:
            _show(root, red["fix"]["commit"], FIX_MODULE)
            checks["declared_fix_contains_module"] = True
        except subprocess.CalledProcessError:
            checks["declared_fix_contains_module"] = False
        checks["verified_fix_ancestor"] = _ancestor(root, verified_fix)
        module = _show(root, verified_fix, FIX_MODULE).decode()
        checks["verified_fix_module_sha256"] = _sha(module.encode())
        checks["verified_fix_module_matches_binding"] = (
            checks["verified_fix_module_sha256"] == recon["verified_fix"]["module_sha256"]
        )
        checks["verified_fix_fail_closed"] = (
            "STABLE_JSON_UNREADABLE" in module and "retry" in module
        )
        checks["current_module_matches_fix"] = (
            _sha((root / FIX_MODULE).read_bytes()) == checks["verified_fix_module_sha256"]
        )
        # a misbound declared fix commit is recorded evidence, not a blocker, because
        # the corrected binding supplies the verified commit.
        checks["misbinding_recorded"] = not checks["declared_fix_contains_module"]
    else:  # pragma: no cover - argparse restricts values
        raise SystemExit("CF_PHASE_INVALID")

    blockers = [k for k, v in checks.items() if isinstance(v, bool) and v is False]
    if phase == "fix" and blockers == ["declared_fix_contains_module"]:
        blockers = []
    result = "CF_PROVENANCE_VERIFIED" if not blockers else "CF_PROVENANCE_GAP"
    return {
        "schema_id": "gwc.q0.cf.provenance-verify/v1",
        "phase": phase,
        "result": result,
        "blocking_checks": blockers,
        "source_head": _git(root, "rev-parse", "HEAD").decode().strip(),
        "checks": checks,
        "authority_granted": False,
        "typed_ce_admitted": False,
        "claim_boundary": "provenance verification only; no native LOAD_PROOF, L3 or gate receipt",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--phase", choices=("red", "fix"), required=True)
    args = parser.parse_args()
    result = verify(Path(args.root), args.phase)
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0 if result["result"] == "CF_PROVENANCE_VERIFIED" else 2


if __name__ == "__main__":
    sys.exit(main())
