# Coding and contract guide

- Follow existing YAML/JSON schema and validator conventions; do not invent a parallel GWC gate format.
- Use exact repository/ref/SHA fields for all provenance; conversation text is never evidence.
- Keep package source under `DW-SuperApps/.dw/powers`; keep target runtime outputs under the selected system root.
- Make ownership and denied-write rules explicit for every integration component.
- Reuse durable checkpoint revision, lease/fencing token, CAS, scope hash and idempotency patterns already present in SCRUM-105/SCRUM-108.
- Treat Jira, Notion and Slack writes as projections only and keep them outside the implementation file list unless separately authorized.
- Preserve legacy target installations and compatibility fallback; do not perform broad cleanup.
