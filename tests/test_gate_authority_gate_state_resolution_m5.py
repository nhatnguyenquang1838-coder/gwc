"""SCRUM-184 M5 regression tests for fail-closed gate-state resolution."""
from __future__ import annotations
import copy, hashlib, json, unittest
from pathlib import Path
from jsonschema import Draft202012Validator
import yaml
from tools.node_architect.evidence_artifact_map import build_gate_evidence_artifact_map
from tools.node_architect.gate_state_resolution import GATE_ORDER, resolve_gate_state
from tools.node_architect.scope_hash_calculation import calculate_gate_scope_identity

ROOT=Path(__file__).parents[1]; BASE="9a7fd18af8f1b9dac4f5bc2774f4e0f602216624"; HEAD="f"*40
REPO="nhatnguyenquang1838-coder/gwc"; TASK="SCRUM-184"; BRANCH="fastlane/scrum-184-gate-state-resolution-m5-20260804"
REQ=(
("G0_CONTEXT","context-snapshot",f".gwc/tasks/{TASK}/g0/context-snapshot.yaml","CANONICAL_GATE_EVIDENCE",True),
("G1_ALIGNMENT","intake",f".gwc/tasks/{TASK}/g1/intake/g1-intake-brief.yaml","CANONICAL_GATE_EVIDENCE",True),
("G1_ALIGNMENT","preflight",f".gwc/tasks/{TASK}/g1/preflight/g1-preflight-report.yaml","CANONICAL_GATE_EVIDENCE",True),
("G1_ALIGNMENT","options",f".gwc/tasks/{TASK}/g1/brainstorming/g1-options.yaml","CANONICAL_GATE_EVIDENCE",True),
("G1_ALIGNMENT","decision",f".gwc/tasks/{TASK}/g1/decision/g1-decision-record.yaml","CANONICAL_GATE_EVIDENCE",True),
("G2_EXECUTION","execution-envelope",f".gwc/tasks/{TASK}/g2/execution-envelope.yaml","CANONICAL_AUTHORITY",True),
("G3_PR","delivery-record",f".gwc/tasks/{TASK}/g3/delivery-record.yaml","DELIVERY_EVIDENCE",True),
("G4_MERGE","merge-approval",f".gwc/tasks/{TASK}/g4/merge-approval.yaml","CANONICAL_AUTHORITY",True))
PATHS=["schemas/gate-state-resolution.schema.json","tests/test_gate_authority_evidence_artifact_map_m4.py","tests/test_gate_authority_gate_state_resolution_m5.py","tools/node_architect/evidence_artifact_map.py","tools/node_architect/gate_state_resolution.py"]

def tmap(): return yaml.safe_load((ROOT/"core/task-lifecycle/gate-transition-map.yaml").read_text())
def scope(**o):
 d=dict(task_id=TASK,repository=REPO,base_ref="main",base_sha=BASE,working_branch=BRANCH,head_sha=HEAD,risk_class="R2",authorized_paths=PATHS,authorized_actions=["modify_approved_files"],excluded_actions=["merge_approved_pr"],additional_bindings=[{"key":"pr_number","value":"211"}],calculated_at="2026-08-04T13:50:00Z"); d.update(o); return calculate_gate_scope_identity(**d)
def cand(g,r,t,c,q,**o):
 d=dict(evidence_key=t,gate=g,artifact_role=r,artifact_type=r,classification=c,required=q,source_type="repository_artifact",target=t,ref=t,revision=HEAD if g in {"G3_PR","G4_MERGE","G5_DEPLOY","G6_PRODUCTION_DATA"} else BASE,digest="sha256:"+hashlib.sha256(t.encode()).hexdigest(),binding_status="BOUND",freshness_status="FRESH",materialization_status="MATERIALIZED",source_of_truth=True); d.update(o); return d
def candidates(g6=False):
 x=[cand(*r) for r in REQ]; x.append(cand("G5_DEPLOY","status-verification","actions://g5-status-verify","DELIVERY_EVIDENCE",False,source_type="github_actions",artifact_type="ci-status"))
 if g6: x.append(cand("G6_PRODUCTION_DATA","production-approval",f".gwc/tasks/{TASK}/g6/production-approval.yaml","CANONICAL_AUTHORITY",False))
 return x
def emap(cs=None,repo=REPO,g6=False): return build_gate_evidence_artifact_map(task_id=TASK,repository=repo,base_sha=BASE,head_sha=HEAD,evidence_candidates=cs if cs is not None else candidates(g6),policy_revision="gate-transition-map@1.0.1",mapped_at="2026-08-04T13:50:00Z")
def redigest(m):
 s={k:m[k] for k in ("task_id","repository","base_sha","head_sha","policy_revision","requirements","missing_required","stale_required","projection_only")}; s["entries"]=sorted(m["entries"],key=lambda e:(str(e.get("gate")),str(e.get("evidence_key")))); m["map_digest"]="sha256:"+hashlib.sha256(json.dumps(s,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def resolve(**o):
 d=dict(task_id=TASK,repository=REPO,current_base_sha=BASE,scope_identity=scope(),evidence_map=emap(),transition_map=tmap(),task_projection=None,event_id_or_idempotency_key="event-1",prior_resolution=None,observed_at="2026-08-04T13:50:00Z"); d.update(o); return resolve_gate_state(**d)

class GateStateResolutionTests(unittest.TestCase):
 def test_happy_schema_flags_and_order(self):
  out=resolve(); self.assertEqual((out["current_gate"],out["gate_status"],out["last_passed_gate"]),("G6_PRODUCTION_DATA","NOT_APPLICABLE","G5_DEPLOY")); self.assertEqual(GATE_ORDER[0],"G0_CONTEXT"); self.assertEqual(GATE_ORDER[-1],"G6_PRODUCTION_DATA")
  schema=json.loads((ROOT/"schemas/gate-state-resolution.schema.json").read_text()); Draft202012Validator.check_schema(schema); self.assertEqual(list(Draft202012Validator(schema).iter_errors(out)),[])
  for f in ("authority_granted","write_authority_granted","pr_authority_granted","merge_authority_granted","deployment_authority_granted","production_authority_granted"): self.assertIs(out[f],False)
 def test_earliest_missing_and_later_inheritance(self):
  for gate,current,last in (("G0_CONTEXT","G0_CONTEXT",None),("G2_EXECUTION","G2_EXECUTION","G1_ALIGNMENT")):
   with self.subTest(gate=gate):
    out=resolve(evidence_map=emap([x for x in candidates() if x["gate"]!=gate])); self.assertEqual((out["current_gate"],out["last_passed_gate"]),(current,last)); self.assertEqual(out["gate_status"],"BLOCKED")
  self.assertIn("GATE_STATE_LATER_GATE_INHERITANCE_REJECTED",resolve(evidence_map=emap([x for x in candidates() if x["gate"]!="G0_CONTEXT"]))["reason_codes"])
 def test_precedence_and_drift(self):
  cs=candidates(); cs[5]["freshness_status"]="STALE"; self.assertEqual(resolve(evidence_map=emap(cs))["primary_reason_code"],"GATE_STATE_EVIDENCE_STALE")
  cs=candidates(); dup=copy.deepcopy(cs[0]); dup["digest"]="sha256:"+"b"*64; cs.append(dup); self.assertEqual(resolve(evidence_map=emap(cs),current_base_sha="1"*40)["primary_reason_code"],"GATE_STATE_EVIDENCE_CONFLICT")
  cs=candidates(); cs[0]["binding_status"]="MISMATCHED"; self.assertEqual(resolve(evidence_map=emap(cs))["primary_reason_code"],"GATE_STATE_BINDING_MISMATCH")
  out=resolve(current_base_sha="1"*40); self.assertEqual((out["primary_reason_code"],out["current_gate"],out["last_passed_gate"]),("GATE_STATE_DRIFT","G0_CONTEXT",None))
 def test_malformed_inputs_fail_closed(self):
  cases=[]
  m=emap(); m["requirements"]=m["requirements"][1:]; redigest(m); cases.append(dict(evidence_map=m))
  m=emap(); del m["entries"][0]["artifact_type"]; redigest(m); cases.append(dict(evidence_map=m))
  m=emap(); m["map_digest"]="sha256:"+"0"*64; cases.append(dict(evidence_map=m))
  s=scope(); s["scope_hash"]="sha256:"+"0"*64; cases.append(dict(scope_identity=s))
  s=scope(); s["invented"]=True; cases.append(dict(scope_identity=s))
  tm=tmap(); tm["rules"]=tm["rules"][:-1]; cases.append(dict(transition_map=tm))
  for i,case in enumerate(cases):
   with self.subTest(case=i): self.assertEqual(resolve(**case)["primary_reason_code"],"GATE_STATE_INPUT_INVALID")
 def test_projection_is_warning_only(self):
  out=resolve(task_projection={"task_id":TASK,"current_gate":"G2_EXECUTION","status":"RUNNING"}); self.assertEqual(out["gate_status"],"NOT_APPLICABLE"); self.assertIn("GATE_STATE_PROJECTION_MISMATCH",out["reason_codes"])
  self.assertIn("PROJECTION_STATE_UNKNOWN",resolve(task_projection={"task_id":TASK,"state":"invented"})["projection_warnings"])
  self.assertIn("CANCELLED_PROJECTION_WITHOUT_CANONICAL_EVIDENCE",resolve(task_projection={"task_id":TASK,"state":"cancelled"})["projection_warnings"])
 def test_read_only_g5_and_production_boundaries(self):
  ro=scope(working_branch=None,head_sha=None,authorized_paths=[],authorized_actions=["verify_post_merge_ci"],additional_bindings=[]); self.assertEqual(resolve(scope_identity=ro)["primary_reason_code"],"GATE_STATE_RESOLVED")
  out=resolve(); self.assertEqual(next(x for x in out["gate_evaluations"] if x["gate"]=="G5_DEPLOY")["status"],"PASS"); self.assertFalse(out["deployment_authority_granted"])
  ps=scope(working_branch=None,head_sha=None,authorized_paths=["production/op.json"],authorized_actions=["production_data_write"],additional_bindings=[]); out=resolve(scope_identity=ps,evidence_map=emap(g6=True)); self.assertEqual((out["gate_status"],out["last_passed_gate"]),("PASS","G6_PRODUCTION_DATA")); self.assertFalse(out["production_authority_granted"])
  ps=scope(working_branch=None,head_sha=None,authorized_paths=["production/config.json"],authorized_actions=["production_config_change"],additional_bindings=[]); self.assertEqual(resolve(scope_identity=ps,evidence_map=emap())["gate_status"],"BLOCKED")
 def test_replay_and_determinism(self):
  a=resolve(observed_at="2026-08-04T00:00:00Z"); b=resolve(observed_at="2026-08-05T00:00:00Z"); self.assertEqual(a["resolution_digest"],b["resolution_digest"])
  r=resolve(prior_resolution=a); self.assertEqual((r["replay_status"],r["resolution_digest"]),("IDEMPOTENT_REPLAY",a["resolution_digest"]))
  cs=candidates(); cs[0]["freshness_status"]="STALE"; r=resolve(evidence_map=emap(cs),prior_resolution=a); self.assertEqual((r["replay_status"],r["primary_reason_code"]),("REPLAY_CONFLICT","GATE_STATE_REPLAY_CONFLICT"))
  m=emap(); m["entries"]=list(reversed(m["entries"])); redigest(m); self.assertEqual(resolve(evidence_map=m)["canonical_evidence_refs"],a["canonical_evidence_refs"])
 def test_every_top_level_blocker_fails_closed(self):
  for blocker in ("EVIDENCE_INPUT_INVALID","EVIDENCE_BINDING_MISMATCH","EVIDENCE_CONFLICT","EVIDENCE_PROJECTION_ONLY","EVIDENCE_STALE","EVIDENCE_REQUIRED_MISSING","EVIDENCE_OBSERVABILITY_INCOMPLETE","EVIDENCE_CI_BINDING_MISMATCH"):
   with self.subTest(blocker=blocker):
    m=emap(); m["outcome"]="BLOCKED"; m["reason_codes"]=[blocker,"EVIDENCE_G6_NOT_APPLICABLE"]; redigest(m); out=resolve(evidence_map=m); self.assertEqual(out["gate_status"],"BLOCKED"); self.assertNotEqual(out["primary_reason_code"],"GATE_STATE_RESOLVED")
 def test_map_head_must_bind_scope_head(self):
  m=emap(); m["head_sha"]=None; redigest(m); out=resolve(evidence_map=m); self.assertEqual(out["primary_reason_code"],"GATE_STATE_BINDING_MISMATCH"); self.assertIn("HEAD_SHA_DRIFT",out["drift_decision"]["reason_codes"])
 def test_required_entry_semantics_exact_bound(self):
  for field,value in (("artifact_role","wrong"),("classification","DELIVERY_EVIDENCE"),("required",False),("evidence_key","wrong"),("ref","wrong"),("revision","e"*40)):
   with self.subTest(field=field):
    m=emap(); m["entries"][0][field]=value; redigest(m); out=resolve(evidence_map=m); self.assertEqual((out["gate_status"],out["primary_reason_code"]),("BLOCKED","GATE_STATE_BINDING_MISMATCH"))
 def test_invalid_digest_and_blocked_extra_field(self):
  m=emap(); m["entries"][0]["digest"]="bad"; redigest(m); self.assertEqual(resolve(evidence_map=m)["primary_reason_code"],"GATE_STATE_INPUT_INVALID")
  m=emap(); m["entries"][5]["status"]="BLOCKED"; redigest(m); self.assertEqual(resolve(evidence_map=m)["primary_reason_code"],"GATE_STATE_INPUT_INVALID")
 def test_g3_and_later_bind_exact_head(self):
  m=emap(); g3=next(x for x in m["entries"] if x["gate"]=="G3_PR"); self.assertEqual(g3["revision"],HEAD); g3["revision"]=BASE; redigest(m); self.assertEqual(resolve(evidence_map=m)["primary_reason_code"],"GATE_STATE_BINDING_MISMATCH")
 def test_dependency_builder_preserves_distinct_digests(self):
  cs=candidates(); out=emap(cs); self.assertEqual({x["evidence_key"]:x["digest"] for x in out["entries"]},{x["evidence_key"]:x["digest"] for x in cs})

if __name__=="__main__": unittest.main()
