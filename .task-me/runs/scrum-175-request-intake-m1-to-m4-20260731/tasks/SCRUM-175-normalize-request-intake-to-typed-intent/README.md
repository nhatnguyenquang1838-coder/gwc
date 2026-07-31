# SCRUM-175

Normalize `intake_context.request-intake` into a typed G0 intake step that can turn a user request into a bounded fact set with explicit intent, outcomes, constraints, exclusions, guards, and reason codes.

Keep the work inside the existing `intake_context` family and its validator/test surface. Do not expand authority beyond `G0_CONTEXT`, do not add production behavior, and do not introduce a parallel node family.
