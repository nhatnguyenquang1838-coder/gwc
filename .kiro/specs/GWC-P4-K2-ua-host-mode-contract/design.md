# Design

UA host mode is a strict non-interactive adapter around the existing UA graph producer. The adapter accepts an exact request envelope, validates target SHA and UA source commit, writes only `.ua/**`, and returns immutable references/digests for downstream consumers.

The adapter cannot mutate product source, `.gwc/**`, `.task-me/**`, Jira, Notion, Slack, Git branches or PR state. Projection systems remain non-authoritative.
