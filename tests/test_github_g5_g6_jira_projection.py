import importlib.util,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("v",ROOT/"tools/validate_github_g5_g6_jira_projection.py"); v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
SHA1="1"*40; SHA2="2"*40
def rec(): return {"schema_version":"0.1","repository":"nhatnguyenquang1838-coder/gwc","evidence_type":"post_merge","expected":{"main_sha":SHA1,"merge_sha":SHA1},"observed":{"main_sha":SHA1,"merge_sha":SHA1},"ci":{"required":True,"workflow_runs":[{"status":"completed","conclusion":"success","jobs":[{"status":"completed","conclusion":"success"}]}]},"projection":{"authority":"projection","grants_gate_authority":False}}
class T(unittest.TestCase):
 def codes(self,x): return {i["code"] for i in x}
 def test_positive(self): self.assertEqual([],v.validate_github_evidence(rec()))
 def test_pr_drift(self): r=rec(); r.update({"evidence_type":"pr_head","expected":{"head_sha":SHA1},"observed":{"head_sha":SHA2}}); self.assertIn("PR_HEAD_DRIFT",self.codes(v.validate_github_evidence(r)))
 def test_ci_absent(self): r=rec(); r["ci"]={"required":True,"workflow_runs":[]}; self.assertIn("CI_UNAVAILABLE_AT_CHECK",self.codes(v.validate_github_evidence(r)))
 def test_projection_leak(self): r=rec(); r["projection"]={"authority":"canonical","grants_gate_authority":True}; self.assertIn("PROJECTION_AUTHORITY_LEAKAGE",self.codes(v.validate_github_evidence(r)))
 def test_g6_required(self): self.assertIn("G6_REQUIRED",self.codes(v.validate_g5_verification({"g6_excluded":False,"merge_sha":SHA1,"current_main_sha":SHA1,"action_class":"deploy"})))
 def test_suite(self): self.assertTrue(v.run_suite(ROOT)["valid"])
if __name__=="__main__": unittest.main()
