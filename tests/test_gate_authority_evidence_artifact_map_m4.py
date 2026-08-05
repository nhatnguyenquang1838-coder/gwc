"""Regression tests for SCRUM-189 gate-evidence-artifact-map."""
from __future__ import annotations
import unittest
from tools.node_architect.evidence_artifact_map import build_gate_evidence_artifact_map
BASE="1db5cdde7666e95e0a5d864633a3255a2a6ad40e"; HEAD="f"*40; TASK="SCRUM-189"
COMMON={"task_id":TASK,"repository":"nhatnguyenquang1838-coder/gwc","base_sha":BASE,"head_sha":HEAD,"policy_revision":"gate-lifecycle-v1.1"}
REQUIREMENTS=(("G0_CONTEXT","context-snapshot",f".gwc/tasks/{TASK}/g0/context-snapshot.yaml","CANONICAL_GATE_EVIDENCE",True),("G1_ALIGNMENT","intake",f".gwc/tasks/{TASK}/g1/intake/g1-intake-brief.yaml","CANONICAL_GATE_EVIDENCE",True),("G1_ALIGNMENT","preflight",f".gwc/tasks/{TASK}/g1/preflight/g1-preflight-report.yaml","CANONICAL_GATE_EVIDENCE",True),("G1_ALIGNMENT","options",f".gwc/tasks/{TASK}/g1/brainstorming/g1-options.yaml","CANONICAL_GATE_EVIDENCE",True),("G1_ALIGNMENT","decision",f".gwc/tasks/{TASK}/g1/decision/g1-decision-record.yaml","CANONICAL_GATE_EVIDENCE",True),("G2_EXECUTION","execution-envelope",f".gwc/tasks/{TASK}/g2/execution-envelope.yaml","CANONICAL_AUTHORITY",True),("G3_PR","delivery-record",f".gwc/tasks/{TASK}/g3/delivery-record.yaml","DELIVERY_EVIDENCE",True),("G4_MERGE","merge-approval",f".gwc/tasks/{TASK}/g4/merge-approval.yaml","CANONICAL_AUTHORITY",True))
def candidate(gate,role,target,classification,required,*,digest_char="a",**overrides):
    model={"evidence_key":target,"gate":gate,"artifact_role":role,"artifact_type":role,"classification":classification,"required":required,"source_type":"repository_artifact","target":target,"ref":target,"revision":HEAD if gate in {"G3_PR","G4_MERGE","G5_DEPLOY","G6_PRODUCTION_DATA"} else BASE,"digest":"sha256:"+digest_char*64,"binding_status":"BOUND","freshness_status":"FRESH","materialization_status":"MATERIALIZED","source_of_truth":True}; model.update(overrides); return model
def complete_candidates(): return [candidate(*r,digest_char=hex(i+1)[2:]) for i,r in enumerate(REQUIREMENTS)]
class EvidenceArtifactMapTests(unittest.TestCase):
    def test_complete_map_ready(self):
        o=build_gate_evidence_artifact_map(evidence_candidates=complete_candidates(),**COMMON); self.assertEqual(o["outcome"],"READY")
    def test_each_entry_retains_its_candidate_digest(self):
        cs=complete_candidates(); o=build_gate_evidence_artifact_map(evidence_candidates=cs,**COMMON); self.assertEqual({x["evidence_key"]:x["digest"] for x in o["entries"]},{x["evidence_key"]:x["digest"] for x in cs})
    def test_order_independent_map_digest(self):
        cs=complete_candidates(); self.assertEqual(build_gate_evidence_artifact_map(evidence_candidates=cs,**COMMON)["map_digest"],build_gate_evidence_artifact_map(evidence_candidates=list(reversed(cs)),**COMMON)["map_digest"])
    def test_missing_required_blocks(self):
        o=build_gate_evidence_artifact_map(evidence_candidates=complete_candidates()[1:],**COMMON); self.assertEqual(o["outcome"],"BLOCKED"); self.assertIn("EVIDENCE_REQUIRED_MISSING",o["reason_codes"])
    def test_stale_required_blocks(self):
        cs=complete_candidates(); cs[0]["freshness_status"]="STALE"; self.assertIn("EVIDENCE_STALE",build_gate_evidence_artifact_map(evidence_candidates=cs,**COMMON)["reason_codes"])
    def test_projection_only_blocks(self):
        cs=complete_candidates(); cs[0]["source_type"]="jira_comment"; self.assertIn("EVIDENCE_PROJECTION_ONLY",build_gate_evidence_artifact_map(evidence_candidates=cs,**COMMON)["reason_codes"])
    def test_head_mismatch_blocks(self):
        cs=complete_candidates(); next(x for x in cs if x["gate"]=="G4_MERGE")["revision"]=BASE; o=build_gate_evidence_artifact_map(evidence_candidates=cs,**COMMON); self.assertIn("EVIDENCE_BINDING_MISMATCH",o["reason_codes"]); self.assertIn("EVIDENCE_CI_BINDING_MISMATCH",o["reason_codes"])
    def test_wrong_canonical_role_blocks(self):
        cs=complete_candidates(); cs[0]["artifact_role"]="invented"; self.assertIn("EVIDENCE_BINDING_MISMATCH",build_gate_evidence_artifact_map(evidence_candidates=cs,**COMMON)["reason_codes"])
    def test_g5_observability_incomplete_not_ci_pending(self):
        cs=complete_candidates(); t="actions://g5-status-verify"; cs.append(candidate("G5_DEPLOY","status-verification",t,"DELIVERY_EVIDENCE",False,source_type="github_actions",materialization_status="UNOBSERVED",freshness_status="UNOBSERVED",binding_status="UNOBSERVED")); o=build_gate_evidence_artifact_map(evidence_candidates=cs,**COMMON); self.assertIn("EVIDENCE_OBSERVABILITY_INCOMPLETE",o["reason_codes"]); self.assertNotIn("CI_PENDING",o["reason_codes"])
    def test_duplicate_conflict_blocks(self):
        cs=complete_candidates(); d=dict(cs[0]); d["digest"]="sha256:"+"b"*64; cs.append(d); self.assertIn("EVIDENCE_CONFLICT",build_gate_evidence_artifact_map(evidence_candidates=cs,**COMMON)["reason_codes"])
    def test_invalid_digest_blocks(self):
        cs=complete_candidates(); cs[0]["digest"]="bad"; self.assertIn("EVIDENCE_INPUT_INVALID",build_gate_evidence_artifact_map(evidence_candidates=cs,**COMMON)["reason_codes"])
    def test_malformed_source_of_truth_blocks(self):
        for value in ("false",1,{"value":False}):
            with self.subTest(value=value):
                cs=complete_candidates(); cs[0]["source_of_truth"]=value; o=build_gate_evidence_artifact_map(evidence_candidates=cs,**COMMON); self.assertEqual(o["outcome"],"BLOCKED"); self.assertIn("EVIDENCE_INPUT_INVALID",o["reason_codes"])
    def test_missing_source_of_truth_blocks(self):
        cs=complete_candidates(); del cs[0]["source_of_truth"]; o=build_gate_evidence_artifact_map(evidence_candidates=cs,**COMMON); self.assertEqual(o["outcome"],"BLOCKED"); self.assertIn("EVIDENCE_INPUT_INVALID",o["reason_codes"])
if __name__=="__main__": unittest.main()
