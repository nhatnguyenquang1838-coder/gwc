# SCRUM-122 through SCRUM-126 Requirements - Evaluation and Controlled Self-Improvement

The P5 chain MUST define and implement a governed evaluation layer for planning, runtime, outcome and catalog-quality signals without introducing production authority.

Acceptance criteria:
- SCRUM-122: planning, runtime, outcome and catalog-quality metrics are explicitly defined, versioned and source-backed.
- SCRUM-123: improvement proposal lifecycle, stable-versus-candidate boundaries, shadow no-side-effect rules, bounded canary eligibility, minimum evidence, human review, rollback, deprecation and retirement policy are explicit.
- SCRUM-124: durable run/history records capture route, decision, evidence and checkpoint evolution, and replay comparison aggregates expected versus observed outcomes.
- SCRUM-125: shadow planning and confidence calibration are deterministic, side-effect free for ineligible routes, and stable fallback is available when confidence or eligibility is insufficient.
- SCRUM-126: promotion workflow covers experimental -> candidate -> pilot -> stable -> deprecated -> retired, requires human approval, never auto-promotes, and exposes stable-vs-candidate graph, route, metric and promotion-status comparisons in the v3 view.
- Jira, Slack and Notion remain projection layers only; GitHub retains repository, PR and CI truth.
- No production deploy, release, migration, secrets or destructive operation is introduced.

