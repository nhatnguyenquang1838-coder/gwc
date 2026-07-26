# SCRUM-136 G0/G1 Human Review Tasks

## SCRUM-138

Implement schema contracts for Task Me/UA impact provenance and the normalized G0/G1 human-review projection.

Deliverables:

- `schemas/g1-option-impact.schema.json`
- `schemas/g01-human-review.schema.json`
- `tests/test_g01_human_review_contracts.py`

Rules:

- Task Me must be represented as invoked when applicable and available.
- UA `STALE`, `PARTIAL`, `EMPTY`, and `MISSING` states must remain visible.
- Synthetic UA knowledge graph nodes are forbidden.
- HTML/chat/Slack projections do not grant gate authority.

## SCRUM-139

Build the deterministic HTML renderer in a separate envelope after SCRUM-138 is complete.

## SCRUM-140

Integrate G1/chat/Slack/package behavior in a separate envelope after SCRUM-138 and SCRUM-139 are complete.
