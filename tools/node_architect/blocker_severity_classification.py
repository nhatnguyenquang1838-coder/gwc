"""Replay-safe blocker severity classification for SCRUM-340 (node #275).

Pure-logic classifier (no descriptor file I/O), mirroring the sibling
``evidence_quality_check`` executable: it performs replay-safe, deterministic
classification and never reads or mutates the node descriptor.

The node descriptor ``core/node-architect/node-catalog/validation_quality/
blocker-severity-classification.node.json`` is the catalog *identity* record;
its content (``description`` / ``source``) is a provenance SHA that this module
MUST NOT touch. The classification *policy* -- the ordered severity classes,
the stable rule IDs, their categories and the waivable threshold -- is the
versioned contract owned by this helper module (``POLICY_VERSION``). That keeps
the taxonomy changeable without editing descriptor provenance, and makes
"policy drift" detectable by comparing the caller-supplied ``policy_version``
against ``POLICY_VERSION``.

Fail-closed guarantees (the node contract for SCRUM-340 / node #275):
  * an unmatched authority / evidence / data-integrity finding BLOCKS;
  * any finding in a terminal category (authority / evidence /
    data-integrity) is NEVER waived -- it blocks regardless of severity;
  * conflicting rules for one finding BLOCK;
  * a policy version that does not match ``POLICY_VERSION`` BLOCKS
    (POLICY_DRIFT);
  * an unknown rule ID or a malformed finding BLOCKS (UNMATCHED);
  * the classifier never silently waives a blocker -- PASS only when every
    open finding is matched by a known rule and resolves to an advisory
    (below-threshold, non-terminal) severity.

The node is data-only: it classifies findings and emits a stable decision with
a total next-route outcome. It never grants later-gate authority.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping, MutableMapping

NODE_ID = "validation_quality.blocker-severity-classification"
PASS = "PASS"
BLOCKED = "BLOCKED"
UNMATCHED = "UNMATCHED"

# --- Versioned severity / terminality policy ----------------------------
# This is the authoritative, versioned contract for the node. Changing the
# taxonomy here bumps POLICY_VERSION; it does NOT require editing the
# descriptor provenance SHA.
POLICY_VERSION = "2026-08-14-r10"

# Ordered highest -> lowest severity. Index is the precedence rank.
SEVERITY_CLASSES = ("BLOCKER", "CRITICAL", "HIGH", "MEDIUM", "LOW")

# Terminal categories: authority / evidence / data-integrity findings MUST
# never be waived, independent of their declared severity.
TERMINAL_CATEGORIES = frozenset({"authority", "evidence", "data-integrity"})

# A finding whose resolved severity rank is >= this threshold is terminal
# (blocks). MEDIUM and LOW are advisory / waivable; BLOCKER/CRITICAL/HIGH block.
WAIVABLE_THRESHOLD = "MEDIUM"

# Stable rule IDs -> (category, severity). Rule IDs are stable across policy
# versions; only the mapping values evolve (with a POLICY_VERSION bump).
RULES: dict[str, tuple[str, str]] = {
    "LEAK_AUTHORITY_BOUNDARY": ("authority", "BLOCKER"),
    "LEAK_EVIDENCE_PROVENANCE": ("evidence", "CRITICAL"),
    "LEAK_DATA_INTEGRITY": ("data-integrity", "CRITICAL"),
    "LEAK_SCOPE_DRIFT": ("scope", "HIGH"),
    "LEAK_HEAD_MISMATCH": ("consistency", "HIGH"),
    "LEAK_STALE_REVIEW": ("timeliness", "MEDIUM"),
    "LEAK_ADVISORY_STYLE": ("style", "LOW"),
}


def get_policy() -> dict[str, Any]:
    """Return the current versioned classification policy (read-only copy)."""
    return {
        "policy_version": POLICY_VERSION,
        "severity_classes": list(SEVERITY_CLASSES),
        "terminal_categories": sorted(TERMINAL_CATEGORIES),
        "waivable_threshold": WAIVABLE_THRESHOLD,
        "rules": {k: {"category": c, "severity": s} for k, (c, s) in RULES.items()},
    }


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task_id": str(payload.get("task_id", "")).strip(),
        "repository": str(payload.get("repository", "")).strip(),
        "branch": str(payload.get("branch", "")).strip(),
        "base_sha": str(payload.get("base_sha", "")).strip(),
        "head_sha": str(payload.get("head_sha", "")).strip(),
        "scope_hash": str(payload.get("scope_hash", "")).strip(),
        "graph_revision": str(payload.get("graph_revision", "")).strip(),
        "idempotency_key": str(payload.get("idempotency_key", "")).strip(),
        "pr_number": payload.get("pr_number"),
    }


def _authority_boundary() -> dict[str, bool]:
    return {
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def _ordered(reasons: set[str]) -> list[str]:
    reason_order = ("POLICY_DRIFT", "UNMATCHED", "CONFLICTING_RULES", "BLOCKER_PRESENT", "CLASSIFIED")
    unknown = reasons.difference(reason_order)
    if unknown:
        raise AssertionError(f"reason code escaped closed set: {sorted(unknown)}")
    return [code for code in reason_order if code in reasons]


def _findings_of(payload: Mapping[str, Any]) -> list[Any]:
    findings = payload.get("findings")
    if findings is None:
        return []
    if not isinstance(findings, list):
        return [findings]
    return list(findings)


def _rule_ids_of(finding: Mapping[str, Any]) -> list[str]:
    explicit = finding.get("rule_ids")
    if isinstance(explicit, list) and explicit:
        ids = [str(x).strip() for x in explicit if str(x).strip()]
        if ids:
            return ids
    single = finding.get("rule_id")
    if isinstance(single, str) and single.strip():
        return [single.strip()]
    return []


def classify_blocker_severity(
    evidence: Mapping[str, Any],
    *,
    policy_version: str = "",
    descriptor: Mapping[str, Any] | None = None,
    replay_cache: MutableMapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Classify validation/review findings and return a stable decision.

    ``evidence`` carries ``findings`` (list) plus optional routing identity.
    Each finding is ``{"rule_id" | "rule_ids": ..., "status"?: ..., "resolved"?:
    ...}``; severity/category are derived from the versioned ``RULES`` policy,
    never trusted from the caller. ``policy_version`` (when supplied) must equal
    ``POLICY_VERSION`` or the decision fails closed with POLICY_DRIFT.

    ``descriptor`` is an optional in-memory guard: when provided it is checked
    for node identity / authority-boundary drift (read-only; never mutated).
    The on-disk descriptor is NOT read here -- the taxonomy lives in this
    module's versioned policy.
    """
    if descriptor is not None and not isinstance(descriptor, Mapping):
        raise TypeError("descriptor must be a Mapping when provided")

    payload = deepcopy(dict(evidence))
    identity = _identity(payload)
    input_digest = _digest(payload)
    cache_key = identity["idempotency_key"]

    if replay_cache is not None and cache_key and cache_key in replay_cache:
        cached = replay_cache[cache_key]
        if cached.get("input_digest") == input_digest:
            replay = deepcopy(cached)
            replay["replayed"] = True
            return replay
        return {
            "schema_version": "1.0",
            "artifact_type": "blocker-severity-classification",
            "node_id": NODE_ID,
            **identity,
            "status": BLOCKED,
            "reason_codes": ["POLICY_DRIFT"],
            "input_digest": input_digest,
            "classification_digest": _digest({"identity": identity, "reason_codes": ["POLICY_DRIFT"]}),
            "classification": [],
            "max_severity_rank": -1,
            "replayed": False,
            **_authority_boundary(),
        }

    reasons: set[str] = set()

    # Optional descriptor identity / authority-boundary guard (read-only).
    if descriptor is not None:
        if str(descriptor.get("node_id", "")).strip() and str(descriptor.get("node_id", "")).strip() != NODE_ID:
            reasons.add("POLICY_DRIFT")
        if str(descriptor.get("authority_boundary", "")).strip() and str(descriptor.get("authority_boundary", "")).strip() != "g3_required":
            reasons.add("POLICY_DRIFT")

    # Policy drift: explicit policy_version must match the versioned contract.
    requested = str(policy_version).strip()
    if requested and requested != POLICY_VERSION:
        reasons.add("POLICY_DRIFT")

    severity_rank = {s.upper(): i for i, s in enumerate(SEVERITY_CLASSES)}
    waivable_rank = severity_rank.get(WAIVABLE_THRESHOLD.upper(), len(SEVERITY_CLASSES))

    max_rank = -1
    has_open = False
    classification: list[dict[str, Any]] = []

    for finding in _findings_of(payload):
        if not isinstance(finding, Mapping):
            reasons.add("UNMATCHED")
            classification.append({"finding": finding, "status": UNMATCHED, "reason_code": "UNMATCHED"})
            continue

        status = str(finding.get("status", "OPEN")).strip().upper()
        if status == "CLOSED" or finding.get("resolved") is True:
            classification.append({"status": "CLOSED", "classification": "RESOLVED"})
            continue

        has_open = True
        rule_ids = _rule_ids_of(finding)
        if not rule_ids:
            reasons.add("UNMATCHED")
            classification.append({"status": UNMATCHED, "reason_code": "UNMATCHED"})
            continue

        resolved: list[tuple[str, str, int]] = []
        unknown = False
        for rid in rule_ids:
            spec = RULES.get(rid)
            if spec is None:
                unknown = True
                continue
            category, severity = spec
            rank = severity_rank.get(severity.upper(), None)
            if rank is None:
                unknown = True
                continue
            resolved.append((rid, category, rank))

        if unknown or not resolved:
            reasons.add("UNMATCHED")
            classification.append({"rule_ids": rule_ids, "status": UNMATCHED, "reason_code": "UNMATCHED"})
            continue

        # Conflicting rules: a single finding matched by rules that resolve to
        # differing severities is ambiguous and must fail closed.
        severities = {r[2] for r in resolved}
        if len(severities) > 1:
            reasons.add("CONFLICTING_RULES")
            classification.append({"rule_ids": rule_ids, "status": "OPEN", "reason_code": "CONFLICTING_RULES"})
            continue

        best = max(resolved, key=lambda r: r[2])
        rid, category, rank = best
        # Severities strictly above the waivable threshold (rank below it) are
        # terminal, plus any finding in a terminal category (authority /
        # evidence / data-integrity) regardless of severity.
        terminal = category.lower() in TERMINAL_CATEGORIES or rank < waivable_rank
        label = "BLOCKING" if terminal else "ADVISORY"
        if terminal:
            reasons.add("BLOCKER_PRESENT")
        if rank > max_rank:
            max_rank = rank
        classification.append({"rule_id": rid, "category": category, "severity": SEVERITY_CLASSES[rank], "status": "OPEN", "classification": label})

    if not reasons:
        # No blocker / unmatched / conflict / drift reasons: every open finding
        # resolved to an advisory (sub-threshold, non-terminal) severity, or
        # there were no open findings at all. Clean PASS.
        reasons.add("CLASSIFIED")

    reason_codes = _ordered(reasons)
    status = PASS if reason_codes == ["CLASSIFIED"] else BLOCKED
    basis = {
        "identity": identity,
        "status": status,
        "reason_codes": reason_codes,
        "max_severity_rank": max_rank,
        "waivable_threshold": WAIVABLE_THRESHOLD,
        "classification": classification,
    }
    result = {
        "schema_version": "1.0",
        "artifact_type": "blocker-severity-classification",
        "node_id": NODE_ID,
        **identity,
        "status": status,
        "reason_codes": reason_codes,
        "input_digest": input_digest,
        "classification_digest": _digest(basis),
        "classification": classification,
        "max_severity_rank": max_rank,
        "replayed": False,
        **_authority_boundary(),
    }
    if replay_cache is not None and cache_key:
        replay_cache[cache_key] = deepcopy(result)
    return result


__all__ = [
    "BLOCKED",
    "NODE_ID",
    "PASS",
    "UNMATCHED",
    "classify_blocker_severity",
    "get_policy",
    "POLICY_VERSION",
    "RULES",
    "SEVERITY_CLASSES",
    "TERMINAL_CATEGORIES",
    "WAIVABLE_THRESHOLD",
]
