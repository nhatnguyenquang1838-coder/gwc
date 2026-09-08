from __future__ import annotations
import copy, json
from pathlib import Path
import jsonschema, pytest
from tools.node_architect.universal_run_kernel import UniversalRunKernelError, seal_immutable_record, verify_record_digest
from tools.node_architect.universal_run_topology import create_node_allocation, create_run_manifest_revision, materialize_child_run
ROOT=Path(__file__).resolve().parents[1]; SCHEMA_ROOT=ROOT/"schemas"/"node-architect"/"universal-run"; CREATED={"kind":"agent","id":"ChatGPT"}; TS="2026-09-08T03:30:00+07:00"
def root_manifest(): return create_run_manifest_revision(record_id="RM-1",run_id="RUN-P",revision=1,run_kind="ROOT",created_at=TS,created_by=CREATED)
def work_alloc(**kw):
    p=dict(record_id="NA-1",run_id="RUN-P",node_allocation_id="NODE-1",kind="WORK",requirement="REQUIRED",created_at=TS,created_by=CREATED); p.update(kw); return create_node_allocation(**p)
def terminal_state(ref="RUN-C1",gen=1,state="ACCEPTED"): return {"child_run_ref":ref,"generation":gen,"terminal_state":state}
def test_01_valid_root_manifest():
    m=root_manifest(); assert m["run_kind"]=="ROOT" and m["parent_run_ref"] is None and m["invoking_node_allocation_ref"] is None and verify_record_digest(m)
def test_02_valid_child_manifest_requires_parent_and_invoking_allocation():
    m=create_run_manifest_revision(record_id="RM-C",run_id="RUN-C",revision=1,run_kind="CHILD",parent_run_ref="RUN-P",invoking_node_allocation_ref="NA-1",created_at=TS,created_by=CREATED); assert m["parent_run_ref"]=="RUN-P" and m["invoking_node_allocation_ref"]=="NA-1"
def test_03_root_with_parent_refs_rejected():
    with pytest.raises(UniversalRunKernelError) as e: create_run_manifest_revision(record_id="RM-X",run_id="RUN-X",revision=1,run_kind="ROOT",parent_run_ref="RUN-P",invoking_node_allocation_ref="NA-1",created_at=TS,created_by=CREATED)
    assert e.value.code=="ROOT_LINEAGE_INVALID"
def test_04_child_missing_parent_rejected():
    with pytest.raises(UniversalRunKernelError) as e: create_run_manifest_revision(record_id="RM-X",run_id="RUN-X",revision=1,run_kind="CHILD",parent_run_ref=None,invoking_node_allocation_ref="NA-1",created_at=TS,created_by=CREATED)
    assert e.value.code=="CHILD_LINEAGE_INVALID"
def test_05_work_materializes_initial_generation_one():
    r=materialize_child_run(record_id="CM-1",parent_run_id="RUN-P",child_run_id="RUN-C1",node_allocation=work_alloc(),created_at=TS,created_by=CREATED); assert (r["generation"],r["materialization_reason"],r["rerun_of"])==(1,"INITIAL",None)
def test_06_control_child_materialization_rejected():
    a=create_node_allocation(record_id="NA-C",run_id="RUN-P",node_allocation_id="NODE-C",kind="CONTROL",requirement="REQUIRED",control_justification="inline bookkeeping",created_at=TS,created_by=CREATED)
    with pytest.raises(UniversalRunKernelError) as e: materialize_child_run(record_id="CM-X",parent_run_id="RUN-P",child_run_id="RUN-C",node_allocation=a,created_at=TS,created_by=CREATED)
    assert e.value.code=="CONTROL_CHILD_MATERIALIZATION_FORBIDDEN"
def test_07_control_without_justification_rejected():
    with pytest.raises(UniversalRunKernelError) as e: create_node_allocation(record_id="NA-C",run_id="RUN-P",node_allocation_id="NODE-C",kind="CONTROL",requirement="REQUIRED",created_at=TS,created_by=CREATED)
    assert e.value.code=="CONTROL_JUSTIFICATION_REQUIRED"
def test_08_control_independent_boundary_requires_work():
    with pytest.raises(UniversalRunKernelError) as e: create_node_allocation(record_id="NA-C",run_id="RUN-P",node_allocation_id="NODE-C",kind="CONTROL",requirement="REQUIRED",control_justification="inline",independent_boundary_reasons=["INDEPENDENT_AUTHORITY"],created_at=TS,created_by=CREATED)
    assert e.value.code=="CONTROL_REQUIRES_WORK"
    sealed=create_node_allocation(record_id="NA-C2",run_id="RUN-P",node_allocation_id="NODE-C2",kind="CONTROL",requirement="REQUIRED",control_justification="inline",created_at=TS,created_by=CREATED)
    tampered=copy.deepcopy(sealed); tampered.pop("content_digest"); tampered["independent_boundary_reasons"]=["INDEPENDENT_AUTHORITY"]; tampered=seal_immutable_record(tampered)
    with pytest.raises(UniversalRunKernelError) as e: __import__("tools.node_architect.universal_run_topology",fromlist=["validate_node_allocation"]).validate_node_allocation(tampered,independent_boundary_reasons=[])
    assert e.value.code=="INDEPENDENT_BOUNDARY_OVERRIDE_MISMATCH"
def test_09_conditional_without_condition_ref_rejected():
    with pytest.raises(UniversalRunKernelError) as e: create_node_allocation(record_id="NA-Q",run_id="RUN-P",node_allocation_id="NODE-Q",kind="WORK",requirement="CONDITIONAL",created_at=TS,created_by=CREATED)
    assert e.value.code=="CONDITION_REF_REQUIRED"
def test_10_second_nonterminal_generation_rejected():
    with pytest.raises(UniversalRunKernelError) as e: materialize_child_run(record_id="CM-2",parent_run_id="RUN-P",child_run_id="RUN-C2",node_allocation=work_alloc(),generation_states=[terminal_state(state="OPEN")],reason="RERUN_SUBTREE",created_at=TS,created_by=CREATED)
    assert e.value.code=="CHILD_RUN_ALREADY_ACTIVE"
def test_11_terminal_prior_allows_rerun_subtree():
    r=materialize_child_run(record_id="CM-2",parent_run_id="RUN-P",child_run_id="RUN-C2",node_allocation=work_alloc(),generation_states=[terminal_state()],reason="RERUN_SUBTREE",created_at=TS,created_by=CREATED); assert r["materialization_reason"]=="RERUN_SUBTREE"
def test_12_rerun_new_child_generation_and_rerun_of():
    r=materialize_child_run(record_id="CM-2",parent_run_id="RUN-P",child_run_id="RUN-C2",node_allocation=work_alloc(),generation_states=[terminal_state()],reason="RERUN_SUBTREE",created_at=TS,created_by=CREATED); assert r["child_run_ref"]=="RUN-C2" and r["generation"]==2 and r["rerun_of"]=="RUN-C1"
    history=[terminal_state("RUN-C1",1,"ACCEPTED"),terminal_state("RUN-C2",2,"FAILED")]
    with pytest.raises(UniversalRunKernelError) as e: materialize_child_run(record_id="CM-3",parent_run_id="RUN-P",child_run_id="RUN-C1",node_allocation=work_alloc(),generation_states=history,reason="RERUN_SUBTREE",created_at=TS,created_by=CREATED)
    assert e.value.code=="CHILD_RUN_REF_REUSED"
def test_13_node_allocation_immutable_across_rerun():
    a=work_alloc(); before=copy.deepcopy(a); materialize_child_run(record_id="CM-2",parent_run_id="RUN-P",child_run_id="RUN-C2",node_allocation=a,generation_states=[terminal_state()],reason="RERUN_SUBTREE",created_at=TS,created_by=CREATED); assert a==before
def test_14_all_e3_artifacts_seal_via_e1_e2_envelope():
    m=root_manifest(); a=work_alloc(); r=materialize_child_run(record_id="CM-1",parent_run_id="RUN-P",child_run_id="RUN-C1",node_allocation=a,created_at=TS,created_by=CREATED); assert all(verify_record_digest(x) for x in (m,a,r))
def test_15_tampered_e3_record_fails_existing_digest_verification():
    a=work_alloc(); t=copy.deepcopy(a); t["kind"]="CONTROL"; assert not verify_record_digest(t)
def test_16_schema_rejects_unknown_child_instance_policy():
    a=work_alloc(); a["child_instance_policy"]="MULTI_ACTIVE"; schema=json.loads((SCHEMA_ROOT/"node-allocation.schema.json").read_text());
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(a,schema)
def test_17_schema_malformed_records_fail_closed():
    manifest=root_manifest(); alloc=work_alloc(); receipt=materialize_child_run(record_id="CM-1",parent_run_id="RUN-P",child_run_id="RUN-C1",node_allocation=alloc,created_at=TS,created_by=CREATED)
    control=create_node_allocation(record_id="NA-C",run_id="RUN-P",node_allocation_id="NODE-C",kind="CONTROL",requirement="REQUIRED",control_justification="inline",created_at=TS,created_by=CREATED)
    conditional=work_alloc(record_id="NA-Q",node_allocation_id="NODE-Q",requirement="REQUIRED"); conditional.pop("content_digest"); conditional["requirement"]="CONDITIONAL"; conditional["condition_ref"]=""; conditional=seal_immutable_record(conditional)
    child=create_run_manifest_revision(record_id="RM-C",run_id="RUN-C",revision=1,run_kind="CHILD",parent_run_ref="RUN-P",invoking_node_allocation_ref="NA-1",created_at=TS,created_by=CREATED)
    bad_control=copy.deepcopy(control); bad_control.pop("content_digest"); bad_control["control_justification"]=None; bad_control=seal_immutable_record(bad_control)
    bad_control_reasons=copy.deepcopy(control); bad_control_reasons.pop("content_digest"); bad_control_reasons["independent_boundary_reasons"]=["INDEPENDENT_AUTHORITY"]; bad_control_reasons=seal_immutable_record(bad_control_reasons)
    bad_root=copy.deepcopy(manifest); bad_root.pop("content_digest"); bad_root["parent_run_ref"]="RUN-P"; bad_root["invoking_node_allocation_ref"]="NA-1"; bad_root=seal_immutable_record(bad_root)
    bad_child=copy.deepcopy(child); bad_child.pop("content_digest"); bad_child["parent_run_ref"]=None; bad_child=seal_immutable_record(bad_child)
    cases=[("run-manifest-revision.schema.json",{k:v for k,v in manifest.items() if k!="run_kind"}),("node-allocation.schema.json",{**alloc,"unexpected":1}),("child-run-materialization-receipt.schema.json",{**receipt,"generation":0}),("node-allocation.schema.json",bad_control),("node-allocation.schema.json",bad_control_reasons),("node-allocation.schema.json",conditional),("run-manifest-revision.schema.json",bad_root),("run-manifest-revision.schema.json",bad_child)]
    for name,value in cases:
        schema=json.loads((SCHEMA_ROOT/name).read_text())
        with pytest.raises(jsonschema.ValidationError): jsonschema.validate(value,schema)

def _receipt_schema():
    return json.loads((SCHEMA_ROOT/"child-run-materialization-receipt.schema.json").read_text())

def _initial_receipt():
    return materialize_child_run(record_id="CM-F4-I",parent_run_id="RUN-P",child_run_id="RUN-C1",node_allocation=work_alloc(),created_at=TS,created_by=CREATED)

def _rerun_receipt():
    return materialize_child_run(record_id="CM-F4-R",parent_run_id="RUN-P",child_run_id="RUN-C2",node_allocation=work_alloc(),generation_states=[terminal_state()],reason="RERUN_SUBTREE",created_at=TS,created_by=CREATED)

def test_18_schema_rejects_initial_with_rerun_of():
    value=copy.deepcopy(_initial_receipt()); value.pop("content_digest"); value["rerun_of"]="RUN-OLD"; value=seal_immutable_record(value)
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(value,_receipt_schema())

def test_19_schema_rejects_rerun_without_rerun_of():
    value=copy.deepcopy(_rerun_receipt()); value.pop("content_digest"); value["rerun_of"]=None; value=seal_immutable_record(value)
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(value,_receipt_schema())

def test_20_schema_rejects_initial_generation_two():
    value=copy.deepcopy(_initial_receipt()); value.pop("content_digest"); value["generation"]=2; value=seal_immutable_record(value)
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(value,_receipt_schema())

def test_21_schema_rejects_rerun_generation_one():
    value=copy.deepcopy(_rerun_receipt()); value.pop("content_digest"); value["generation"]=1; value=seal_immutable_record(value)
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(value,_receipt_schema())
