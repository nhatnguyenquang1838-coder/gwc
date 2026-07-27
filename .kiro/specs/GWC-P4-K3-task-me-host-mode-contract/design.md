# Design

Task-Me host mode is a strict planner adapter. It consumes immutable UA snapshot references and produces task packages, impact analysis, dependency DAGs, estimates, coding guides and validation plans under `.task-me/**`.

The adapter is derived and non-authoritative. GWC gate artifacts and GitHub exact evidence remain authoritative. Jira, Notion and Slack remain projection/communication layers.
