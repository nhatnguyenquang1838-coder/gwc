# P3 Scenario Routing Contract

SCRUM-112 freezes scenario routing semantics. Scenarios define activation source, safety class, retry semantics, authority impact and evidence needs. Typed guards fail closed on unsupported type/operator pairs. Routes classify as VALID_AUTO, VALID_HUMAN, CONDITIONAL, BLOCKED or UNSAFE. Ranking is deterministic by safety, authority distance, missing facts, dependency hops, cost/time, profile priority and stable route id.
