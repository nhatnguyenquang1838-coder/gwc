# Test Plan

- Every state-changing operation resolves to exactly one authority owner.
- Jira and external projections cannot grant G0-G6 authority.
- Task-Me and BMAD outputs cannot mutate canonical GWC state.

## Repository validation candidates

- `python tools/validate_instructions.py`
- `python tools/build_project_package.py gwc --output dist`
- Applicable focused unit tests discovered from the exact diff

Report unavailable commands honestly; do not claim PASS without captured output.
