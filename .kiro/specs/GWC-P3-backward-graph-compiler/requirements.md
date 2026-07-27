# Requirements — SCRUM-97 P3 Backward Graph Compiler & Scenario Decision Engine

FastLane P3 runs two contract threads before implementation.

- Thread A / SCRUM-111: compiler request/result, backward derivation, dependency closure, deterministic ordering and planning evidence.
- Thread B / SCRUM-112: scenario taxonomy, typed guards, route classification/ranking, authority stops and dominance pruning.

SCRUM-113 and SCRUM-114 stay blocked until K1/K2 contracts freeze. SCRUM-115 stays blocked until I1/I2 complete. No runtime implementation code is allowed in this envelope.
