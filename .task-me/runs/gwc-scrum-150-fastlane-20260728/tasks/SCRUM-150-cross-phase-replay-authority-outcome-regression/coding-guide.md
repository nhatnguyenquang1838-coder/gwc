# Coding guide

- Keep the validator deterministic and side-effect free, following the style of
  `tools/validate_p5_evaluation.py` and the other `validate_*` modules.
- Use explicit issue codes and locations; do not silently coerce missing facts
  into PASS.
- Treat each dependency's source/base/head/merge/CI binding independently,
  then require the composite run to reference the same observed evidence.
- Require every metric to carry numerator, denominator, observed event IDs and
  a value matching the calculation; reject a value-only constant.
- Preserve `authority=projection` and `grants_gate_authority=false` for all
  Jira/Slack/Notion records.
- Keep G4/G5/G6 as excluded authority boundaries. The validator can verify
  envelopes but cannot issue approval or transition a gate.
