# Validation plan

- `python3 tools/validate_g01.py --workspace .gwc/tasks/SCRUM-116 --json` before G2 and again with `--gate G2_EXECUTION` before the first write.
- Validate every new schema/fixture with the repository's existing JSON/YAML validators.
- Run focused governance, provenance, checkpoint/CAS/lease and package/distribution tests.
- Run Python compile checks, `git diff --check`, secret/unauthorized-file checks and complete diff review.
- Verify exact PR-head CI evidence at G3; G1 does not claim product/runtime or CI success.
