# Impact analysis

Direct impact is limited to the verified durable runtime and replay harness,
their focused tests, and any existing runtime schema/fixture required to make
the integrated evidence executable. Downstream consumers are SCRUM-149 E2E and
SCRUM-146 closure evidence. Reuse the existing `DurableCheckpointStore` and
`CrashReplayHarness`; do not introduce a competing state authority.
