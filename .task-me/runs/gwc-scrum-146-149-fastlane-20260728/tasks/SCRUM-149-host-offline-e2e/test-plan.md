# Test plan

```text
python -m unittest discover -s tests -p 'test_dw_super_e2e_pilot.py'
python -m unittest discover -s tests -p 'test_ua_host_contract.py'
python -m unittest discover -s tests -p 'test_task_me_host_contract.py'
python -m unittest discover -s tests -p 'test_kiro_local_agent_package.py'
```

Record the offline workspace path, package checksum, provider-call evidence,
replay readback, and all skipped live-host checks. No product build/E2E claim
may be inferred from validator-only PASS.
