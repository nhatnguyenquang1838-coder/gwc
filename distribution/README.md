# GWC skills-only distribution

This directory defines the provider-owned package consumed by DW Power Distribution v1.

## Included

- `skills/gwc-g0/**` and `skills/gwc-g1/**`;
- verified core contracts, agent instructions, project guidance, schemas, templates, generators, validators, and the pinned offline G0/G1 skill library;
- neutral consumer configuration defaults and schema.

## Excluded

The package never contains `.gwc` task or gate evidence, `.ua`, `.task-me`, Kiro feature specs, generated tasks or plans, dashboards, frontends, tests, releases, caches, logs, secrets, or populated runtime data.

## Runtime ownership

Installation places package files under the consumer's `.dw/powers/gwc` installation and creates only an empty consumer-owned `.gwc` runtime root. It does not create a Jira task, GWC gate, approval envelope, branch, pull request, release, deployment, Slack message, or other external write.

## Build and publication

The caller workflow pins DW-SuperApps commit `4e552ea3d915a4790814b08b3155c66e3c5736a1`. The shared workflow validates one staging tree and uses it for both the deterministic release ZIP and optional `power-dist` projection.

During DW-PDIST-02 implementation, publication inputs remain disabled and no artifact is released.
