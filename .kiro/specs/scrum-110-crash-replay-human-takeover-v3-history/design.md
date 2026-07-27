# SCRUM-110 Design

The provider-neutral harness composes exact-state capture, bounded-write classification and durable checkpoint/CAS/lease/fencing primitives. Crash injection is deterministic and side-effect free. Human takeover is emitted only when live state cannot prove PASS or safe retry. The v3 history adapter overlays durable history on the canonical 81-node registry while retaining visual-only edge semantics.
