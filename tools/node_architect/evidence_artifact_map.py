"""Canonical gate evidence artifact map for SCRUM-189 (MAT-F2-N06)."""
from __future__ import annotations
import hashlib
import json
from typing import Any, Sequence

EVIDENCE_CLASSES = frozenset({"CANONICAL_AUTHORITY","CANONICAL_GATE_EVIDENCE","DELIVERY_EVIDENCE","AUDIT_PROJECTION","RESUME_HINT"})
PROJECTION_SOURCE_TYPES = frozenset({"jira_comment","slack_message","notion_page","dashboard","chat_message"})
_GATE_REQUIREMENTS: tuple[dict[str, str], ...] = (
    {"gate":"G0_CONTEXT","artifact_role":"context-snapshot","target":".gwc/tasks/<task-id>/g0/context-snapshot.yaml","class_":"CANONICAL_GATE_EVIDENCE","required":"true"},
    {"gate":"G1_ALIGNMENT","artifact_role":"intake","target":".gwc/tasks/<task-id>/g1/intake/g1-intake-brief.yaml","class_":"CANONICAL_GATE_EVIDENCE","required":"true"},
    {"gate":"G1_ALIGNMENT","artifact_role":"preflight","target":".gwc/tasks/<task-id>/g1/preflight/g1-preflight-report.yaml","class_":"CANONICAL_GATE_EVIDENCE","required":"true"},
    {"gate":"G1_ALIGNMENT","artifact_role":"options","target":".gwc/tasks/<task-id>/g1/brainstorming/g1-options.yaml","class_":"CANONICAL_GATE_EVIDENCE","required":"true"},
    {"gate":"G1_ALIGNMENT","artifact_role":"decision","target":".gwc/tasks/<task-id>/g1/decision/g1-decision-record.yaml","class_":"CANONICAL_GATE_EVIDENCE","required":"true"},
    {"gate":"G2_EXECUTION","artifact_role":"execution-envelope","target":".gwc/tasks/<task-id>/g2/execution-envelope.yaml","class_":"CANONICAL_AUTHORITY","required":"true"},
    {"gate":"G3_PR","artifact_role":"delivery-record","target":".gwc/tasks/<task-id>/g3/delivery-record.yaml","class_":"DELIVERY_EVIDENCE","required":"true"},
    {"gate":"G4_MERGE","artifact_role":"merge-approval","target":".gwc/tasks/<task-id>/g4/merge-approval.yaml","class_":"CANONICAL_AUTHORITY","required":"true"},
    {"gate":"G5_DEPLOY","artifact_role":"deployment-approval","target":".gwc/tasks/<task-id>/g5/deployment-approval.yaml","class_":"CANONICAL_AUTHORITY","required":"false"},
    {"gate":"G6_PRODUCTION_DATA","artifact_role":"production-approval","target":".gwc/tasks/<task-id>/g6/production-approval.yaml","class_":"CANONICAL_AUTHORITY","required":"false"},
)
_REASON_PRECEDENCE=["EVIDENCE_INPUT_INVALID","EVIDENCE_BINDING_MISMATCH","EVIDENCE_CONFLICT","EVIDENCE_PROJECTION_ONLY","EVIDENCE_STALE","EVIDENCE_REQUIRED_MISSING","EVIDENCE_OBSERVABILITY_INCOMPLETE","EVIDENCE_CI_BINDING_MISMATCH","EVIDENCE_G6_NOT_APPLICABLE"]

def _canonical_json_bytes(model: dict[str, Any]) -> bytes:
    return json.dumps(model,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode("utf-8")

def _min_class_priority(class_name: str) -> int:
    order=["RESUME_HINT","AUDIT_PROJECTION","DELIVERY_EVIDENCE","CANONICAL_GATE_EVIDENCE","CANONICAL_AUTHORITY"]
    return order.index(class_name) if class_name in order else len(order)

def build_gate_evidence_artifact_map(*,task_id:str,repository:str,base_sha:str,evidence_candidates:list[dict[str,object]],policy_revision:str,head_sha:str|None=None,mapped_at:str|None=None)->dict[str,object]:
    reasons=[]
    def valid_sha(value:object)->bool:
        return isinstance(value,str) and len(value)==40 and all(c in "0123456789abcdef" for c in value)
    def valid_digest(value:object)->bool:
        return isinstance(value,str) and value.startswith("sha256:") and len(value)==71 and all(c in "0123456789abcdef" for c in value[7:])
    if not isinstance(task_id,str) or not task_id.strip(): reasons.append("EVIDENCE_INPUT_INVALID")
    if not isinstance(repository,str) or "/" not in repository.strip().lstrip(): reasons.append("EVIDENCE_INPUT_INVALID")
    if not valid_sha(base_sha): reasons.append("EVIDENCE_INPUT_INVALID")
    if head_sha is not None and not valid_sha(head_sha): reasons.append("EVIDENCE_INPUT_INVALID")
    if not isinstance(policy_revision,str) or not policy_revision.strip(): reasons.append("EVIDENCE_INPUT_INVALID")
    if not isinstance(evidence_candidates,list): reasons.append("EVIDENCE_INPUT_INVALID")
    requirements=[]; requirement_policy={}
    for requirement in _GATE_REQUIREMENTS:
        target=requirement["target"].replace("<task-id>",task_id or "<task-id>")
        public={"gate":requirement["gate"],"artifact_role":requirement["artifact_role"],"target":target,"required":requirement.get("required","true")=="true"}
        requirements.append(public); requirement_policy[target]={**public,"classification":requirement["class_"]}
    norm_candidates=[]
    if isinstance(evidence_candidates,list):
        for candidate in evidence_candidates:
            if not isinstance(candidate,dict): reasons.append("EVIDENCE_INPUT_INVALID"); continue
            norm_candidates.append(candidate)
    if not any(c.get("gate")=="G6_PRODUCTION_DATA" for c in norm_candidates): reasons.append("EVIDENCE_G6_NOT_APPLICABLE")
    seen_digests={}
    for candidate in norm_candidates:
        key=candidate.get("evidence_key"); digest=candidate.get("digest")
        if not isinstance(key,str) or not key: reasons.append("EVIDENCE_INPUT_INVALID"); continue
        if key in seen_digests and seen_digests[key]!=digest: reasons.append("EVIDENCE_CONFLICT")
        seen_digests[key]=digest if isinstance(digest,str) else ""
    entries=[]; matched_targets=set()
    for candidate in norm_candidates:
        gate=candidate.get("gate"); classification=candidate.get("classification"); source_type=candidate.get("source_type"); target=candidate.get("target"); reference=candidate.get("ref"); evidence_key=candidate.get("evidence_key"); revision=candidate.get("revision"); digest=candidate.get("digest"); artifact_role=candidate.get("artifact_role"); artifact_type=candidate.get("artifact_type"); required=candidate.get("required"); materialization=candidate.get("materialization_status","UNOBSERVED"); freshness=candidate.get("freshness_status","UNOBSERVED"); binding=candidate.get("binding_status","UNOBSERVED"); raw_source_of_truth=candidate.get("source_of_truth")
        source_of_truth=raw_source_of_truth if isinstance(raw_source_of_truth,bool) else False
        entry_reasons=[]; is_projection_source=source_type in PROJECTION_SOURCE_TYPES; is_canonical_class=classification in {"CANONICAL_AUTHORITY","CANONICAL_GATE_EVIDENCE","DELIVERY_EVIDENCE"}
        required_strings=(evidence_key,gate,artifact_role,artifact_type,classification,source_type,target,reference,revision,digest)
        structural_invalid=(any(not isinstance(v,str) or not v for v in required_strings) or not isinstance(required,bool) or not isinstance(raw_source_of_truth,bool) or classification not in EVIDENCE_CLASSES or not valid_sha(revision) or not valid_digest(digest) or binding not in {"BOUND","MISMATCHED","UNOBSERVED","NOT_APPLICABLE"} or freshness not in {"FRESH","STALE","UNOBSERVED"} or materialization not in {"MATERIALIZED","MISSING","UNOBSERVED"})
        if structural_invalid: reasons.append("EVIDENCE_INPUT_INVALID"); continue
        if is_projection_source and is_canonical_class: entry_reasons.append("EVIDENCE_PROJECTION_ONLY")
        if binding=="MISMATCHED": entry_reasons.append("EVIDENCE_BINDING_MISMATCH")
        if freshness=="STALE": entry_reasons.append("EVIDENCE_STALE")
        if materialization=="MISSING": entry_reasons.append("EVIDENCE_REQUIRED_MISSING")
        if materialization=="UNOBSERVED" or freshness=="UNOBSERVED" or binding=="UNOBSERVED": entry_reasons.append("EVIDENCE_OBSERVABILITY_INCOMPLETE")
        policy=requirement_policy.get(target) if isinstance(target,str) else None
        if policy is not None:
            expected_revision=head_sha if head_sha is not None and gate in {"G3_PR","G4_MERGE","G5_DEPLOY","G6_PRODUCTION_DATA"} else base_sha
            if gate!=policy["gate"] or artifact_role!=policy["artifact_role"] or classification!=policy["classification"] or required is not policy["required"] or evidence_key!=target or reference!=target or revision!=expected_revision: entry_reasons.append("EVIDENCE_BINDING_MISMATCH")
        else:
            is_g5_status=(gate=="G5_DEPLOY" and artifact_role=="status-verification" and classification=="DELIVERY_EVIDENCE" and required is False and source_type=="github_actions" and evidence_key==target==reference and revision==(head_sha or base_sha))
            if not is_g5_status: entry_reasons.append("EVIDENCE_BINDING_MISMATCH")
        if gate in {"G4_MERGE","G5_DEPLOY"} and revision!=(head_sha or base_sha): entry_reasons.append("EVIDENCE_CI_BINDING_MISMATCH")
        entry_reasons=sorted(set(entry_reasons),key=lambda c:(_REASON_PRECEDENCE.index(c) if c in _REASON_PRECEDENCE else len(_REASON_PRECEDENCE))); reasons.extend(entry_reasons)
        entry={"evidence_key":evidence_key,"gate":gate,"artifact_role":artifact_role,"artifact_type":artifact_type,"classification":classification,"required":required,"source_type":source_type,"target":target,"ref":reference,"revision":revision,"digest":digest,"binding_status":binding,"freshness_status":freshness,"materialization_status":materialization,"source_of_truth":source_of_truth and not is_projection_source,"reason_codes":entry_reasons}
        entries.append(entry)
        if policy is not None and materialization=="MATERIALIZED" and source_of_truth and not entry_reasons: matched_targets.add(str(target))
    missing_required=sorted({str(r["target"]) for r in requirements if r["required"] and r["target"] not in matched_targets})
    stale_required=sorted({str(e["target"]) for e in entries if e.get("target") and e.get("freshness_status")=="STALE"})
    projection_only=sorted({str(e["target"]) for e in entries if e.get("target") and "EVIDENCE_PROJECTION_ONLY" in e["reason_codes"]})
    if missing_required: reasons.append("EVIDENCE_REQUIRED_MISSING")
    if stale_required: reasons.append("EVIDENCE_STALE")
    if projection_only: reasons.append("EVIDENCE_PROJECTION_ONLY")
    sorted_reasons=sorted(set(reasons),key=lambda r:(_REASON_PRECEDENCE.index(r) if r in _REASON_PRECEDENCE else len(_REASON_PRECEDENCE)))
    blocking=[r for r in sorted_reasons if r!="EVIDENCE_G6_NOT_APPLICABLE"]
    outcome="BLOCKED" if blocking else "READY"; reported=blocking or ["EVIDENCE_MAP_READY"]
    if "EVIDENCE_G6_NOT_APPLICABLE" in sorted_reasons: reported.append("EVIDENCE_G6_NOT_APPLICABLE")
    sorted_entries=sorted(entries,key=lambda e:(str(e.get("gate")),str(e.get("evidence_key"))))
    map_model={"task_id":task_id,"repository":repository,"base_sha":base_sha,"head_sha":head_sha,"policy_revision":policy_revision,"requirements":requirements,"entries":sorted_entries,"missing_required":missing_required,"stale_required":stale_required,"projection_only":projection_only}
    map_digest="sha256:"+hashlib.sha256(_canonical_json_bytes(map_model)).hexdigest()
    return {"schema_version":"1.0","artifact_type":"gate-evidence-artifact-map","task_id":task_id,"repository":repository,"base_sha":base_sha,"head_sha":head_sha,"policy_revision":policy_revision,"mapped_at":mapped_at,"outcome":outcome,"reason_codes":reported,"entries":sorted_entries,"requirements":requirements,"missing_required":missing_required,"stale_required":stale_required,"projection_only":projection_only,"map_digest":map_digest,"authority_granted":False}
