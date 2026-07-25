# Test Plan

- Schema meta-validation.
- Positive and negative fixtures for every contract.
- Reject free-form executable guards.
- Reject promoted nodes without evidence contract and implementation owner.

## Repository validation candidates

- `python tools/validate_instructions.py`
- `python tools/build_project_package.py gwc --output dist`
- Applicable focused unit tests discovered from the exact diff

Report unavailable commands honestly; do not claim PASS without captured output.
