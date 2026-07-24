# GWC skills-only Power distribution

- Added a strict GWC G0/G1 skills-only provider recipe for DW Power Distribution v1.
- Added host-neutral runtime defaults and a JSON Schema contract.
- Added a reusable publishing workflow pinned to DW-SuperApps commit `4e552ea3d915a4790814b08b3155c66e3c5736a1`.
- Added provider tests for dependency closure, forbidden content, runtime ownership, workflow immutability, and authority preservation.
- Future release asset contract: `gwc-{version}.zip` with `gwc-{version}.zip.sha256`; optional distribution branch: `power-dist`.
- No release, distribution-branch publication, PR, merge, deployment, or production operation occurred as part of DW-PDIST-02.
