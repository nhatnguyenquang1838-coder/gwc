# G0/G1 Offline Skill Library

This directory is the deterministic offline fallback for GWC G0 and G1 skill patterns.

Runtime order:

```text
1. Query Context7 using /obra/superpowers.
2. Accept live guidance only when the complete compatible bundle is present.
3. If Context7 is forbidden, unavailable, timed out, empty, incomplete, or incompatible, load this pinned bundle.
4. Verify all required files against manifest.yaml.
5. Use exactly one source mode: CONTEXT7_LIVE or OFFLINE_PINNED.
```

The cards are GWC-normalized offline adaptations. They do not override protected-base governance and do not grant execution, merge, deployment, release, production configuration, credential, migration, or production-data authority.