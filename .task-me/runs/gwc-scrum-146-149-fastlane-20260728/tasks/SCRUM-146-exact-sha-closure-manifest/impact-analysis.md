# Impact analysis

This is the final integration/evidence lane. It consumes exact branch, PR head,
merge, main and CI evidence plus the three prerequisite acceptance records. It
must not retroactively mark stale evidence as current and must not use Jira or
projection state as gate authority. Any base/head drift invalidates downstream
head-bound evidence and requires revalidation.
