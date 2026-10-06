# Test Plan

- Lifecycle transition positive/negative tests.
- Authority mismatch and expired approval tests.
- Canonical/legacy workspace compatibility tests.
- G3 stale-head and Draft/ready transition tests.
- Package manifest/checksum drift tests.

## Repository validation candidates

- `python tools/validate_instructions.py`
- `python tools/build_project_package.py gwc --output dist`
- Applicable focused unit tests discovered from the exact diff

Report unavailable commands honestly; do not claim PASS without captured output.

