import unittest
from tools.node_architect.select_approved_research import select_approved_research
from tools.node_architect.materialize_research_execution import materialize_research_execution
from tools.node_architect.run_research_execution_flow import run_research_execution_flow

import hashlib, json
from datetime import datetime, timezone

NOW = datetime(2026, 8, 8, 14, 0, tzinfo=timezone.utc)

def digest(value):
    raw=json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:"+hashlib.sha256(raw).hexdigest()

def research_and_approval(*, g3=True):
    scope = {
        "scope_id": "round-1",
        "objective": "Implement bounded trace contract",
        "implementation_guidance": ["add schema", "add validator"],
        "acceptance_criteria": ["tests pass", "no authority elevation"],
        "dependencies": ["SCRUM-274"],
        "risk_class": "R2",
        "authorized_paths": ["schemas/node-architect/**", "tools/node_architect/**", "tests/**"],
        "excluded_actions": ["merge", "deploy", "production_data_write"],
    }
    scope["scope_digest"] = digest(scope)
    research = {
        "research_ref":"SCRUM-279","research_digest":digest({"research":"trace"}),"repository":"nhatnguyenquang1838-coder/gwc",
        "lane":"node-architect-research","status":"In Review","priority":"High","dependencies":["SCRUM-274"],"scopes":{"round-1":dict(scope)},
    }
    approval = {
        "schema_version":"1.0","artifact_type":"research-execution-approval","approval_id":"RESEARCH-APPROVAL-279-R1",
        "issued_at":"2026-08-08T13:00:00Z","expires_at":"2026-08-09T13:00:00Z","authority_revision":"1",
        "research_ref":research["research_ref"],"research_digest":research["research_digest"],"repository":research["repository"],"base_ref":"main","base_sha":"2e20badf04b4d84bf8a2e88d6e1e88d540745d35","active_lane":research["lane"],
        "approved_scope":dict(scope),"delegated_g2_actions":["create_guarded_branch_or_worktree","modify_approved_files","run_sandboxed_validation","create_commit","push_working_branch"],
        "delegated_g3_actions":["open_or_update_draft_pr","monitor_exact_head_ci","repair_within_approved_scope","run_independent_read_only_review","mark_pr_ready_for_review"] if g3 else [],
        "scope_hash":digest({"authority":"279-r1"}),"human_approval":{"source":"human_exact_command","exact_command_digest":digest("APPROVE RESEARCH"),"trusted_readback":True},"g4_g5_g6_authority_granted":False,
    }
    return research, approval

def dep_ok():
    return {"jira_status":"Done","semantic_state":"deliverable","repository_implementation":True,"exact_sha_verified":True,"evidence_refs":["main@2e20badf"]}

class FlowTests(unittest.TestCase):
    def base(self, trigger="immediate_after_approval"):
        r,a=research_and_approval(); return r,a,{"run_id":"run-1","dispatch_id":"dispatch-1","trigger_mode":trigger,"active_lane":"node-architect-research","excluded_lanes":["other"],"research_records":[r],"approvals":[a],"dependency_evidence":{"SCRUM-274":dep_ok()}}
    def test_immediate_and_scheduled_selection_identical(self):
        r,a,p=self.base(); i=select_approved_research({k:v for k,v in p.items() if k not in {"dispatch_id"}},now=NOW); p["trigger_mode"]="scheduled_poll"; s=select_approved_research({k:v for k,v in p.items() if k not in {"dispatch_id"}},now=NOW); self.assertEqual(i["selected_research"],s["selected_research"])
    def test_unsafe_done_dependency_rejected(self):
        r,a,p=self.base(); p["dependency_evidence"]["SCRUM-274"]={"jira_status":"Done","semantic_state":"superseded","repository_implementation":True,"exact_sha_verified":True,"evidence_refs":["x"]}; out=run_research_execution_flow(p); self.assertEqual(out["outcome"],"IDLE")
    def test_full_external_sequence_stops_at_g4(self):
        r,a,p=self.base(); one=run_research_execution_flow(p); self.assertEqual(one["outcome"],"ACTION_REQUIRED"); cp=one["checkpoint"]; key=cp["materialization_key"]
        gh={"id":"325","materialization_key":key,"origin_research_ref":"SCRUM-279"}; jr={"id":"SCRUM-285","materialization_key":key,"origin_research_ref":"SCRUM-279"}
        p2={**p,"dispatch_id":"dispatch-2","checkpoint":cp,"projection_readbacks":{"github":[gh],"jira":[jr]}}; two=run_research_execution_flow(p2); self.assertEqual(two["reason_code"],"EXECUTION_TASK_CLAIM_REQUIRED"); cp2=two["checkpoint"]
        claim={"status":"CLAIMED","materialization_key":key,"execution_task_ids":{"github":"325","jira":"SCRUM-285"}}
        p3={**p,"dispatch_id":"dispatch-3","checkpoint":cp2,"projection_readbacks":{"github":[gh],"jira":[jr]},"claim_readback":claim}; three=run_research_execution_flow(p3); self.assertEqual(three["outcome"],"HANDOFF"); self.assertEqual(three["gwc_handoff"]["stop_before"],"G4_MERGE")
        cp3=three["checkpoint"]; runtime={"status":"G3_PASS","materialization_key":key,"pr_number":400,"head_sha":"a"*40,"scope_hash":"sha256:"+"b"*64}
        p4={**p,"dispatch_id":"dispatch-4","checkpoint":cp3,"projection_readbacks":{"github":[gh],"jira":[jr]},"claim_readback":claim,"gwc_runtime_readback":runtime}; four=run_research_execution_flow(p4); self.assertEqual(four["outcome"],"HUMAN_REQUIRED"); self.assertEqual(four["reason_code"],"HUMAN_AUTHORITY_REQUIRED"); self.assertEqual(four["g4_request"]["head_sha"],"a"*40)
    def test_duplicate_dispatch_fenced_after_effect(self):
        r,a,p=self.base(); one=run_research_execution_flow(p); p2={**p,"checkpoint":one["checkpoint"]}; two=run_research_execution_flow(p2); self.assertEqual(two["outcome"],"FENCED")
if __name__ == "__main__": unittest.main()
