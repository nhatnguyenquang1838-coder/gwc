# Requirements Tracer (Analysis Skill)
The `requirements-tracer` provides automated verification of implementation progress against the agreed-upon scope in G1.

## Usage
Run this when you have a complex diff or are preparing to move from **G2 (Execution)** to **G3 (Submission)**.

```bash
/requirements-tracer <task_id> <diff>
```

## How it works
It performs a three-pass analysis:
1.  **Positive Matching**: Maps each `acceptance_criteria` item to the specific lines in your diff that satisfy it.
2.  **Negative Enforcement**: Scans for any changes related to defined **Non-Goals**. Any matches here are flagged as "Scope Violations."
3.  **Context Check**: Validates that all changes are constrained to the `in_scope` file paths and modules identified in your G1 record.

## Reporting Format
The skill returns a table:
- ✅ MATCHED: Full alignment with an AC.
- ⚠️ PARTIAL: Work started but lacks critical details or verification.
- ❌ VIOLATION: A change was detected that violates a Non-Goal or is outside the requested scope.
