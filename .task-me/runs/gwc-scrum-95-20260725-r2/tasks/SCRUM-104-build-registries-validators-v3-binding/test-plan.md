# Test Plan

- 81-slot invariant and family distribution.
- No proposed slot presented as stable without promotion evidence.
- Scenario references resolve to existing node/flow/green anchors.
- Visual-only edges cannot enter runtime graph.
- V3 loads full graph and dims inactive nodes without deleting them.

## Repository validation candidates

- `python tools/validate_instructions.py`
- `python tools/build_project_package.py gwc --output dist`
- Applicable focused unit tests discovered from the exact diff

Report unavailable commands honestly; do not claim PASS without captured output.

