"""Deterministic M5 unit-test-mapping for validation_quality.unit-test-mapping.

Maps changed runtime catalog artifacts to the MINIMUM mandatory executable
unit tests, with explicit rule IDs and a policy digest. This is a data-only,
fail-closed decision helper: it never calls GitHub, the network, or grants
later-gate authority.

Semantics (SCRUM-336 brief):
  * Given changed paths/behaviors and a test inventory, compute the minimum
    mandatory executable tests per artifact via deterministic path/behavior
    rules, each carrying an explicit rule_id and a DELTA_REQUIRED /
    VERIFIED_REUSE classification (historical SCRUM-213 is reuse evidence).
  * Unmapped runtime behavior BLOCKS (UNMAPPED_CHANGE).
  * A mapped required test that is absent from the inventory BLOCKS
    (MISSING_REQUIRED_TEST) -- covers deleted/missing tests.
  * Overlapping/ambiguous rules for one artifact BLOCK (MAPPING_CONFLICT).
  * Docs-only changes (markdown / docs dir / README / CHANGELOG) are handled
    EXPLICITLY (DOCS_ONLY) and never guessed into requiring tests.
  * Policy drift is detected against an expected policy digest (POLICY_DRIFT).
  * Invalid identity / policy input fails closed (INVALID_INPUT).
  * Replay cache: identical idempotency_key + input_digest yields an identical
    evidence_digest with replayed=True; a conflicting identity under the same
    key fails closed (CONFLICTING_IDENTITY).

No merge / deployment / production authority is ever granted.
"""

from __future__ import annotations

from copy import deepcopy
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from .ci_run_capture import digest_payload

NODE_ID = "validation_quality.unit-test-mapping"

PASS = "PASS"
BLOCKED = "BLOCKED"

# Closed reason-code set. Every terminal decision must use one of these.
REASON_CODES = frozenset({
    "MAPPED_PASS",
    "DOCS_ONLY",
    "UNMAPPED_CHANGE",
    "MISSING_REQUIRED_TEST",
    "MAPPING_CONFLICT",
    "POLICY_DRIFT",
    "INVALID_INPUT",
    "CONFLICTING_IDENTITY",
})

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SCOPE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# Per-artifact mapping status enum (mirrored in the schema).
_MAP_STATUS = frozenset({"MAPPED", "DOCS_ONLY", "UNMAPPED", "MISSING_TEST", "CONFLICT"})


@dataclass(frozen=True)
class _Rule:
    pattern: str
    rule_id: str
    classification: str  # DELTA_REQUIRED | VERIFIED_REUSE
    required_tests: tuple[str, ...]
    docs_only: bool


# Deterministic path/behavior -> test rule table.
#
# Classification legend:
#   VERIFIED_REUSE  -- existing mapping logic reused as evidence (SCRUM-213
#                      reuse lineage); no new behavior introduced.
#   DELTA_REQUIRED  -- the missing deterministic rule implemented by this
#                      SCRUM-336 route (no fake coverage, no no-op mapping).
#
# The overlap pair (RULE_SHARED_MODULE_A / RULE_SHARED_MODULE_B) exists to make
# overlap/conflict detection deterministic and testable: a path beneath
# tools/.../shared/ matches BOTH and is reported as MAPPING_CONFLICT.
# Rules are mutually exclusive except for the intentional overlap pair
# (RULE_SHARED_MODULE_A / RULE_SHARED_MODULE_B) which exercises conflict
# detection. The docs-only rules use negative lookaheads so a doc under
# docs/ or a top-level README only matches its single intended rule.
RULES: tuple[_Rule, ...] = (
    # --- docs-only handling (explicit, never guessed) ---
    _Rule(r"(^|/)docs/.*", "RULE_DOCS_DIR", "VERIFIED_REUSE", (), True),
    _Rule(r"(^|/)(README|CHANGELOG|CONTRIBUTING|LICENSE)(\.[A-Za-z]+)?$", "RULE_DOCS_PROSE", "VERIFIED_REUSE", (), True),
    _Rule(r"^releases/changelog\.d/.*\.md$", "RULE_CHANGELOG_FRAGMENT", "DELTA_REQUIRED", ("tests/test_changelog_fragment_hygiene.py",), False),
    # Any other *.md that is not under docs/, not a changelog fragment and not a
    # top-level prose file is treated as docs-only.
    _Rule(r"^(?:(?!docs/)(?!.*/docs/)(?!releases/changelog\.d/)(?!.*/changelog\.d/)(?!.*(?:README|CHANGELOG|CONTRIBUTING|LICENSE)\.).*)\.md$", "RULE_DOCS_MARKDOWN", "VERIFIED_REUSE", (), True),
    # --- runtime catalog artifact -> focused unit-test rules ---
    _Rule(r"^schemas/.*\.json$", "RULE_SCHEMA_CONTRACT", "VERIFIED_REUSE", ("tests/test_canonical_runtime_schema_contracts.py",), False),
    _Rule(r"^tools/node_architect/.*\.py$", "RULE_NODE_ARCHITECT_RUNTIME", "VERIFIED_REUSE", ("tests/test_node_architect_runtime_m5.py",), False),
    _Rule(r"^core/node-architect/.*$", "RULE_CORE_NODE_ARCHITECT", "DELTA_REQUIRED", ("tests/test_validation_quality_unit_test_mapping_m5.py",), False),
    # --- overlap pair for conflict detection ---
    _Rule(r".*/shared/.*\.py$", "RULE_SHARED_MODULE_A", "DELTA_REQUIRED", ("tests/test_shared_module_a.py",), False),
    _Rule(r"^tools/.*shared.*$", "RULE_SHARED_MODULE_B", "VERIFIED_REUSE", ("tests/test_shared_module_b.py",), False),
)


def _identity(payload: Mapping[str, Any]) -> dict[str, str]:
    return {
        field: str(payload.get(field, "")).strip()
        for field in (
            "task_id", "run_id", "repository", "branch",
            "base_sha", "head_sha", "scope_hash", "graph_revision",
            "policy_digest", "idempotency_key",
        )
    }


def _authority_boundary() -> dict[str, bool]:
    return {
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def _entry(
    artifact: str, rule_id: str | None, classification: str | None,
    docs_only: bool, required: Sequence[str], present: Sequence[str],
    missing: Sequence[str], status: str,
) -> dict[str, Any]:
    return {
        "artifact": artifact,
        "rule_id": rule_id,
        "classification": classification,
        "docs_only": docs_only,
        "required_tests": list(required),
        "present_tests": list(present),
        "missing_tests": list(missing),
        "status": status,
    }


def _build(
    identity: Mapping[str, str], input_digest: str, status: str,
    reason_code: str, mapping: Sequence[Mapping[str, Any]], mapped_test_ids: Iterable[str],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_type": "unit-test-mapping-decision",
        "node_id": NODE_ID,
        **identity,
        "status": status,
        "reason_code": reason_code,
        "input_digest": input_digest,
        "evidence_digest": digest_payload({
            "identity": dict(identity),
            "status": status,
            "reason_code": reason_code,
            "mapping": [dict(m) for m in mapping],
            "mapped_test_ids": sorted(mapped_test_ids),
        }),
        "mapping": [dict(m) for m in mapping],
        "mapped_test_ids": sorted(mapped_test_ids),
        "replayed": False,
        **_authority_boundary(),
    }


def map_unit_tests(
    evidence: Mapping[str, Any],
    *,
    expected_policy_digest: str | None = None,
    replay_cache: MutableMapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Map changed artifacts to mandatory unit tests (fail-closed, deterministic).

    Pure and read-only: no connector call, network request, filesystem mutation,
    Jira transition, branch/PR action, approval, merge, deployment or production
    operation. The returned decision is the closed, schema-valid
    ``unit-test-mapping-decision`` artifact. No later-gate authority is granted.
    """
    payload = deepcopy(dict(evidence))
    identity = _identity(payload)
    input_digest = digest_payload(payload)
    cache_key = identity["idempotency_key"]

    if replay_cache is not None and cache_key and cache_key in replay_cache:
        cached = replay_cache[cache_key]
        if cached.get("input_digest") == input_digest:
            replay = deepcopy(cached)
            replay["replayed"] = True
            return replay
        return _build(identity, input_digest, BLOCKED, "CONFLICTING_IDENTITY", [], [])

    def _finish(status: str, reason_code: str, mapping: list[dict[str, Any]], mapped_test_ids: Sequence[str]) -> dict[str, Any]:
        if reason_code not in REASON_CODES:
            raise AssertionError(f"reason code escaped closed set: {reason_code}")
        decision = _build(identity, input_digest, status, reason_code, mapping, list(mapped_test_ids))
        if replay_cache is not None and cache_key:
            replay_cache[cache_key] = deepcopy(decision)
        return decision

    # --- fail-closed input validation ---
    reasons: set[str] = set()
    if any(not value for value in identity.values()):
        reasons.add("INVALID_INPUT")
    if identity["base_sha"] and not _SHA_RE.fullmatch(identity["base_sha"]):
        reasons.add("INVALID_INPUT")
    if identity["head_sha"] and not _SHA_RE.fullmatch(identity["head_sha"]):
        reasons.add("INVALID_INPUT")
    if identity["scope_hash"] and not _SCOPE_RE.fullmatch(identity["scope_hash"]):
        reasons.add("INVALID_INPUT")
    if identity["policy_digest"] and not _SCOPE_RE.fullmatch(identity["policy_digest"]):
        reasons.add("INVALID_INPUT")

    if "INVALID_INPUT" not in reasons:
        if expected_policy_digest is not None and identity["policy_digest"] != expected_policy_digest:
            reasons.add("POLICY_DRIFT")

    if "INVALID_INPUT" in reasons:
        return _finish(BLOCKED, "INVALID_INPUT", [], [])
    if "POLICY_DRIFT" in reasons:
        return _finish(BLOCKED, "POLICY_DRIFT", [], [])

    # --- deterministic artifact -> test mapping ---
    changed = [str(a) for a in (payload.get("changed_artifacts") or [])]
    inventory_set = {str(t) for t in (payload.get("test_inventory") or [])}

    mapping: list[dict[str, Any]] = []
    mapped_test_ids: set[str] = set()

    for artifact in changed:
        matches = [r for r in RULES if re.search(r.pattern, artifact)]
        if not matches:
            mapping.append(_entry(artifact, None, None, False, [], [], [], "UNMAPPED"))
            reasons.add("UNMAPPED_CHANGE")
            continue
        if len(matches) > 1:
            mapping.append(_entry(artifact, None, None, False, [], [], [], "CONFLICT"))
            reasons.add("MAPPING_CONFLICT")
            continue
        rule = matches[0]
        if rule.docs_only:
            mapping.append(_entry(artifact, rule.rule_id, rule.classification, True, [], [], [], "DOCS_ONLY"))
            continue
        present = [t for t in rule.required_tests if t in inventory_set]
        missing = [t for t in rule.required_tests if t not in inventory_set]
        status = "MAPPED" if not missing else "MISSING_TEST"
        mapping.append(_entry(artifact, rule.rule_id, rule.classification, False, rule.required_tests, present, missing, status))
        mapped_test_ids.update(present)
        if missing:
            reasons.add("MISSING_REQUIRED_TEST")

    if reasons & {"UNMAPPED_CHANGE", "MISSING_REQUIRED_TEST", "MAPPING_CONFLICT"}:
        if "UNMAPPED_CHANGE" in reasons:
            return _finish(BLOCKED, "UNMAPPED_CHANGE", mapping, mapped_test_ids)
        if "MISSING_REQUIRED_TEST" in reasons:
            return _finish(BLOCKED, "MISSING_REQUIRED_TEST", mapping, mapped_test_ids)
        return _finish(BLOCKED, "MAPPING_CONFLICT", mapping, mapped_test_ids)

    has_runtime = any(m["status"] == "MAPPED" or m["status"] == "MISSING_TEST" for m in mapping)
    if has_runtime:
        return _finish(PASS, "MAPPED_PASS", mapping, mapped_test_ids)
    # only docs-only / empty change set -> explicit docs-only handling
    return _finish(PASS, "DOCS_ONLY", mapping, mapped_test_ids)


__all__ = ["BLOCKED", "NODE_ID", "PASS", "REASON_CODES", "RULES", "map_unit_tests"]
