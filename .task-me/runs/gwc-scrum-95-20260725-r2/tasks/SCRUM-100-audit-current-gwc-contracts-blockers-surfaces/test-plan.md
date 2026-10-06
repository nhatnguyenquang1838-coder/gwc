# Test Plan

- Path existence checks for every cited file.
- Cross-check audit statements against current tests and schemas.
- No inferred implementation may be labelled canonical.

## Repository validation candidates

- `python tools/validate_instructions.py`
- `python tools/build_project_package.py gwc --output dist`
- Applicable focused unit tests discovered from the exact diff

Report unavailable commands honestly; do not claim PASS without captured output.

