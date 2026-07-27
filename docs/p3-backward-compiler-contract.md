# P3 Backward Compiler Contract

SCRUM-111 freezes compiler semantics. A compiler request binds task, repository, base SHA, graph revision, desired outcome, safe-failure outcome, authority boundaries and planning evidence. The compiler derives capabilities by walking predecessor dependencies, closes dependencies, applies profile overlays, rejects unsafe candidates, and emits selected/rejected node rationale in deterministic order. Failure modes include MISSING_TERMINAL, MISSING_DEPENDENCY, CYCLE_UNSAFE, AUTHORITY_MISMATCH, PROFILE_MISMATCH and UNSAFE_TERMINAL.
