# Coding guide

- Keep the no-production boundary enforced by `tools/validate_dw_super_e2e_pilot.py`.
- Reuse the request/result shapes under `examples/integrations/ua-host` and
  `examples/integrations/task-me-host`; do not widen output roots beyond
  target-owned `.ua/**` and `.task-me/**` in the host contracts.
- Treat `examples/**` as deterministic fixtures and label any real-provider
  evidence separately.
- Offline installation must verify checksum, version, source provenance and
  backward compatibility without network acquisition.
