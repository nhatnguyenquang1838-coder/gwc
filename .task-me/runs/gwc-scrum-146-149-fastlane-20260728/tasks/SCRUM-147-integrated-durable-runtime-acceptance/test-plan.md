# Test plan

```text
python -m unittest discover -s tests -p 'test_durable_checkpoint_runtime.py'
python -m unittest discover -s tests -p 'test_crash_replay_harness.py'
python -m unittest discover -s tests -p 'test_durable_runtime_contracts.py'
```

Also run the repository’s applicable schema/package checks and record exact
commands and limitations. Runtime/E2E claims require executable evidence, not
fixture-only PASS.
