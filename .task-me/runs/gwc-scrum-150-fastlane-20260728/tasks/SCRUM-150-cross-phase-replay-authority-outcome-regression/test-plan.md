# Test plan

Run from the GWC repository root:

```bash
python3 -m unittest -v tests.test_scrum_150_cross_phase
python3 tools/validate_scrum_150_cross_phase.py --suite --json
python3 tools/validate_dw_super_e2e_pilot.py --root . --json
python3 tools/validate_p5_evaluation.py --suite --json
python3 tools/validate_github_g5_g6_jira_projection.py --suite --json
git diff --check
```

Expected evidence is a PASS for the contract-positive fixture and stable typed
failures for stale exact-head state, replay divergence, duplicate effects,
metric fabrication, promotion bypass, and projection authority leakage. No
live provider or production test is implied.
