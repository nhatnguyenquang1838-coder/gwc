# SCRUM-116 impact analysis

The requested outcome is a contract and ownership boundary, not an implementation adapter. The direct impact is the GWC governance contract surface, the DW-SuperApps distribution/control-plane contract, and the target-owned runtime roots. The transitive impact is to SCRUM-117 through SCRUM-121, which consume the boundary; SCRUM-120 is explicitly blocked by SCRUM-116.

UA read-only mapping identifies existing authority/source-of-truth traceability for GWC, UA, Task-Me, BMAD and GitHub/Jira, plus runtime checkpoint CAS and lease nodes. Existing durable-runtime designs support checkpoint revision, lease/fencing token, scope hash and idempotency boundaries. These are evidence to reuse and extend, not permission to change them in G1.

The main unknowns are final contract filenames, the absent DW-SuperApps/boilerplate branch, and BMAD `ready-unpublished` publication state. They are discovery/compatibility items for G2, not reasons to invent a replacement topology now.
