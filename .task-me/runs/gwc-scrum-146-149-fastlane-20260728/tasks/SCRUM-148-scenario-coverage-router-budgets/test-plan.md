# Test plan

```text
python -m unittest discover -s tests -p 'test_p3_scenario_registry.py'
python -m unittest discover -s tests -p 'test_p3_backward_graph.py'
python -m unittest discover -s tests -p 'test_runtime_registry_validation.py'
```

Add tests for every materialized scenario, deterministic tie ordering, cycles,
dense branches, budget overflow, typed guard mismatch, human/blocked/unsafe
authority stops, and immutable decision history.
