# Impact analysis

Direct impact is the scenario registry, backward graph compiler, runtime
registry validator and focused P3 tests. SCRUM-149 consumes the resulting
deterministic decisions. The principal risk is accidentally turning a
projection edge or human/unsafe route into an executable path; this is a
hard acceptance failure.
