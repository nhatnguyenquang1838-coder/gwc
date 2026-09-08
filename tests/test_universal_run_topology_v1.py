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

def test_22_child_manifest_rejects_parent_self_loop():
    with pytest.raises(UniversalRunKernelError) as e: create_run_manifest_revision(record_id="RM-SELF",run_id="RUN-P",revision=1,run_kind="CHILD",parent_run_ref="RUN-P",invoking_node_allocation_ref="NA-1",created_at=TS,created_by=CREATED)
    assert e.value.code=="CHILD_PARENT_SELF_LOOP"

def test_23_child_materialization_rejects_parent_self_loop():
    with pytest.raises(UniversalRunKernelError) as e: materialize_child_run(record_id="CM-SELF",parent_run_id="RUN-P",child_run_id="RUN-P",node_allocation=work_alloc(),created_at=TS,created_by=CREATED)
    assert e.value.code=="CHILD_PARENT_SELF_LOOP"

def test_24_schema_accepts_valid_initial_receipt():
    jsonschema.validate(_initial_receipt(),_receipt_schema())

def test_25_schema_accepts_valid_rerun_receipt():
    jsonschema.validate(_rerun_receipt(),_receipt_schema())

def test_26_schema_rejects_whitespace_only_rerun_of():
    value=copy.deepcopy(_rerun_receipt()); value.pop("content_digest"); value["rerun_of"]="   "; value=seal_immutable_record(value)
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(value,_receipt_schema())

def test_27_integral_float_generation_is_normalized():
    state=terminal_state(); state["generation"]=2.0
    r=materialize_child_run(record_id="CM-FLOAT",parent_run_id="RUN-P",child_run_id="RUN-C2",node_allocation=work_alloc(),generation_states=[state],reason="RERUN_SUBTREE",created_at=TS,created_by=CREATED)
    assert r["generation"]==3 and type(r["generation"]) is int

def test_28_boolean_generation_is_rejected():
    state=terminal_state(); state["generation"]=True
    with pytest.raises(UniversalRunKernelError) as e: materialize_child_run(record_id="CM-BOOL",parent_run_id="RUN-P",child_run_id="RUN-C2",node_allocation=work_alloc(),generation_states=[state],reason="RERUN_SUBTREE",created_at=TS,created_by=CREATED)
    assert e.value.code=="CHILD_GENERATION_STATE_INVALID"

def test_29_manifest_revision_rejects_bool():
    with pytest.raises(UniversalRunKernelError) as e: create_run_manifest_revision(record_id="RM-BOOL",run_id="RUN-P",revision=True,run_kind="ROOT",created_at=TS,created_by=CREATED)
    assert e.value.code=="RUN_MANIFEST_REVISION_INVALID"

def test_30_manifest_revision_normalizes_integral_float():
    m=create_run_manifest_revision(record_id="RM-FLOAT",run_id="RUN-P",revision=2.0,run_kind="ROOT",created_at=TS,created_by=CREATED)
    assert m["revision"]==2 and type(m["revision"]) is int

def test_31_manifest_rejects_padded_lineage_reference():
    with pytest.raises(UniversalRunKernelError) as e: create_run_manifest_revision(record_id="RM-PAD",run_id="RUN-C",revision=1,run_kind="CHILD",parent_run_ref=" RUN-P ",invoking_node_allocation_ref="NA-1",created_at=TS,created_by=CREATED)
    assert e.value.code=="CHILD_LINEAGE_INVALID"

def test_32_manifest_schema_rejects_whitespace_and_padded_references():
    child=create_run_manifest_revision(record_id="RM-SCHEMA",run_id="RUN-C",revision=1,run_kind="CHILD",parent_run_ref="RUN-P",invoking_node_allocation_ref="NA-1",created_at=TS,created_by=CREATED)
    schema=json.loads((SCHEMA_ROOT/"run-manifest-revision.schema.json").read_text())
    for field,value in (("parent_run_ref","   "),("invoking_node_allocation_ref"," NA-1 ")):
        candidate=copy.deepcopy(child); candidate.pop("content_digest"); candidate[field]=value; candidate=seal_immutable_record(candidate)
        with pytest.raises(jsonschema.ValidationError): jsonschema.validate(candidate,schema)

def test_33_node_allocation_rejects_noncanonical_references():
    with pytest.raises(UniversalRunKernelError) as e: create_node_allocation(record_id="NA-RUN",run_id=" RUN-P ",node_allocation_id="NODE-1",kind="WORK",requirement="REQUIRED",created_at=TS,created_by=CREATED)
    assert e.value.code=="RECORD_ENVELOPE_INVALID"
    with pytest.raises(UniversalRunKernelError) as e: create_node_allocation(record_id="NA-ID",run_id="RUN-P",node_allocation_id=" NODE-1 ",kind="WORK",requirement="REQUIRED",created_at=TS,created_by=CREATED)
    assert e.value.code=="NODE_ALLOCATION_ID_INVALID"
    with pytest.raises(UniversalRunKernelError) as e: create_node_allocation(record_id="NA-COND",run_id="RUN-P",node_allocation_id="NODE-1",kind="WORK",requirement="CONDITIONAL",condition_ref=" ",created_at=TS,created_by=CREATED)
    assert e.value.code=="CONDITION_REF_REQUIRED"
    with pytest.raises(UniversalRunKernelError) as e: create_node_allocation(record_id="NA-CTRL",run_id="RUN-P",node_allocation_id="NODE-1",kind="CONTROL",requirement="REQUIRED",control_justification=" ",created_at=TS,created_by=CREATED)
    assert e.value.code=="CONTROL_JUSTIFICATION_REQUIRED"

def test_34_node_allocation_schema_rejects_noncanonical_references():
    value=work_alloc(); schema=json.loads((SCHEMA_ROOT/"node-allocation.schema.json").read_text())
    for field in ("run_id","node_allocation_id","condition_ref","control_justification"):
        candidate=copy.deepcopy(value); candidate.pop("content_digest"); candidate[field]=" padded "; candidate=seal_immutable_record(candidate)
        with pytest.raises(jsonschema.ValidationError): jsonschema.validate(candidate,schema)

def test_35_nonpadded_references_remain_accepted():
    manifest=create_run_manifest_revision(record_id="RM-VALID",run_id="RUN-C",revision=1,run_kind="CHILD",parent_run_ref="RUN-P",invoking_node_allocation_ref="NA-1",created_at=TS,created_by=CREATED)
    allocation=create_node_allocation(record_id="NA-VALID",run_id="RUN-P",node_allocation_id="NODE-1",kind="CONTROL",requirement="REQUIRED",control_justification="valid justification",created_at=TS,created_by=CREATED)
    assert manifest["parent_run_ref"]=="RUN-P" and allocation["control_justification"]=="valid justification"

def test_36_child_generation_rejects_padded_reference():
    with pytest.raises(UniversalRunKernelError) as e: materialize_child_run(record_id="CM-GEN-PAD",parent_run_id="RUN-P",child_run_id="RUN-C2",node_allocation=work_alloc(),generation_states=[terminal_state(" RUN-C1 ")],reason="RERUN_SUBTREE",created_at=TS,created_by=CREATED)
    assert e.value.code=="CHILD_GENERATION_STATE_INVALID"

def test_37_child_materialization_rejects_padded_ids():
    with pytest.raises(UniversalRunKernelError) as e: materialize_child_run(record_id="CM-ID-PAD",parent_run_id="RUN-P",child_run_id=" RUN-C2 ",node_allocation=work_alloc(),created_at=TS,created_by=CREATED)
    assert e.value.code=="CHILD_RUN_REF_INVALID"

@pytest.mark.parametrize("value", [" padded ", "A\nB", "A\rB", "A\r\nB"])
def test_38_optional_condition_ref_must_be_canonical(value):
    with pytest.raises(UniversalRunKernelError): create_node_allocation(record_id="NA-COND-OPT",run_id="RUN-P",node_allocation_id="NODE-1",kind="WORK",requirement="REQUIRED",condition_ref=value,created_at=TS,created_by=CREATED)

def test_39_optional_control_justification_must_be_canonical():
    for value in (" padded ", "A\nB", "A\rB", "A\r\nB"):
        with pytest.raises(UniversalRunKernelError): create_node_allocation(record_id="NA-CTRL-OPT",run_id="RUN-P",node_allocation_id="NODE-1",kind="WORK",requirement="REQUIRED",control_justification=value,created_at=TS,created_by=CREATED)

def test_40_node_allocation_schema_rejects_embedded_line_terminators():
    value=work_alloc(); schema=json.loads((SCHEMA_ROOT/"node-allocation.schema.json").read_text())
    for field in ("condition_ref","control_justification"):
        for invalid in ("A\nB", "A\rB", "A\r\nB"):
            candidate=copy.deepcopy(value); candidate.pop("content_digest"); candidate[field]=invalid; candidate=seal_immutable_record(candidate)
            with pytest.raises(jsonschema.ValidationError): jsonschema.validate(candidate,schema)

def test_41_optional_references_allow_interior_spaces():
    value=work_alloc(condition_ref="A B",control_justification="A B")
    jsonschema.validate(value,json.loads((SCHEMA_ROOT/"node-allocation.schema.json").read_text()))
    assert value["condition_ref"]=="A B" and value["control_justification"]=="A B"

def test_42_manifest_schema_rejects_embedded_line_terminators():
    child=create_run_manifest_revision(record_id="RM-SCHEMA-LT",run_id="RUN-C",revision=1,run_kind="CHILD",parent_run_ref="RUN-P",invoking_node_allocation_ref="NA-1",created_at=TS,created_by=CREATED)
    schema=json.loads((SCHEMA_ROOT/"run-manifest-revision.schema.json").read_text())
    for field in ("record_id","run_id","parent_run_ref","invoking_node_allocation_ref"):
        candidate=copy.deepcopy(child); candidate.pop("content_digest"); candidate[field]="A\nB"; candidate=seal_immutable_record(candidate)
        with pytest.raises(jsonschema.ValidationError): jsonschema.validate(candidate,schema)
