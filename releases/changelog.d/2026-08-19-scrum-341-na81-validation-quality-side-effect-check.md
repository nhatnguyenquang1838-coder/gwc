# SCRUM-341 M‑05 validation-quality side-effect-check NA81 semantics

## Type

```text
feature
```

## Summary

Implements the `validation_quality.side-effect-check` NA81 node executable
(SCRUM-341, node #276). The descriptor
(`core/node-architect/node-catalog/validation_quality/side-effect-check.node.json`)
is READ-ONLY and was not edited — provenance-SHA trap avoided.

The node verifies validation-related external observations/effects through
authoritative readback and classifies each as confirmed / pending / failed /
unknown / duplicate-equivalent. It is pure, deterministic, and replay-safe:

- Unknown or interrupted outcomes are flagged `UNKNOWN_OUTCOME_UNRECONCILED` and
  BLOCKED — they MUST reconcile before any retry and never silently become
  confirmed.
- Identical replay MUST NOT duplicate effects: `duplicate-equivalent`
  observations are flagged `DUPLICATE_EFFECT` and BLOCKED, and a same-input
  replay returns the cached decision verbatim (no re-applied effect).
- Authoritative readback is required and matched against the declared intent;
  any mismatch is `READBACK_MISMATCH` (BLOCKED). A readback taken under an
  expired fence/scoped window is `STALE_FENCE` (BLOCKED). Timeout/interrupted
  observations are classified `unknown`.

Every authority field is fixed `False`; the check never grant merge,
deployment, or production authority (family invariants). The decision carries a
stable `decision_digest` and `input_digest` and embeds the canonical
reason/provenance/evidence following the `evidence_quality_check.py` pattern.

## Deliverables

- New helper `tools/node_architect/side_effect_check.py`
  (`check_side_effects`) returning a deterministic
  `{status, reason_codes, verdicts, decision_digest, ...}` decision.
- New focused test `tests/test_validation_quality_side_effect_check_m5.py`
  covering confirmed / pending / failed / unknown / duplicate, timeout /
  interruption, stale fence, readback mismatch, and replay idempotency
  (identical replay must not duplicate effects).
- Changelog fragment only; no `*.node.json` `description`/`source` fields edited
  and no registry `source_sha` mutated (provenance-SHA trap avoided).

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-341.
Targets pre-prod only; main is FORBIDDEN.
