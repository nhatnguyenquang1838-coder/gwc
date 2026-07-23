# REVAMP-GWC-025 — scale_control node catalog

- Adds the ninth controlled node family with nine descriptors for admission, cardinality, throttling, exact-head observability, rollout projection, and independent-audit handoff.
- Completes the package export surface for 81 unique runtime nodes while keeping `scale_81_nodes_allowed` false pending independent audit.
- Tracks connector implementation for post-merge push-run discovery separately in Jira SCRUM-69.
- Does not add runtime engine, scheduler, worker, merge, deploy, release, production configuration/data, credential, secret, or migration authority.
