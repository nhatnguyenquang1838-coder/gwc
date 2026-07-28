# Test plan

```text
python -m unittest discover -s tests -p 'test_g5_status_resolver.py'
python -m unittest discover -s tests -p 'test_github_g5_g6_jira_projection.py'
python -m unittest discover -s tests -p 'test_exact_state_capture.py'
```

Add manifest-specific schema/hash tests only after the canonical destination and
schema are discovered. Required CI and PR evidence must match the exact current
head SHA; GitHub lookup is currently unavailable and must be retried before
claiming closure.
