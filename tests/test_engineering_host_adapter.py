"""Local host parser/executor boundary; no background observer or typed parsing."""
import pytest
from test_engineering_m1_m7_workflow import binding
from tools.node_architect.engineering_host_adapter import select_human_communication


def test_one_shot_parser_filters_typed_history_and_binds_real_comment(tmp_path):
    c=binding(tmp_path)
    body='<!-- dw.taskcontroller.communication/v2 -->\n### A2A v2 · CORRECTION #43\nrun: '+c['run']['id']+'\nseq: 43\nfrom: GPT\nto: Hermes\nkind: CORRECTION\nsource_ref: github://owner/repo/issues/1\nreply_to: https://github.com/owner/repo/issues/1#issuecomment-99\n\nFix workflow routing.'
    rows=[{'body':'{"protocol":"typed-machine-record","payload":{"DO_NOT_PARSE":true}}'},
          {'body':body.replace('seq: 43','seq: 42').replace('github://owner/repo/issues/1','historical-other-source'),'id':122,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-122','user':{'login':'owner'}},
          {'body':body,'id':123,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-123','user':{'login':'owner'}}]
    r=select_human_communication(rows,c)
    assert r['seq']==43 and r['comment_id']==123 and r['evidence_class']=='HUMAN_COMMUNICATION_ONLY'
    assert 'typed-machine-record' not in str(r)


def test_duplicate_human_sequence_fails_closed(tmp_path):
    c=binding(tmp_path)
    body='<!-- dw.taskcontroller.communication/v2 -->\nrun: '+c['run']['id']+'\nseq: 43\nfrom: GPT\nto: Hermes\nkind: COMMAND\nsource_ref: github://owner/repo/issues/1\nreply_to: https://github.com/owner/repo/issues/1#issuecomment-1\n\nWork'
    row={'body':body,'id':123,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-123','user':{'login':'owner'}}
    with pytest.raises(ValueError,match='HUMAN_COMMUNICATION_DUPLICATE_SEQ'):
        select_human_communication([row,row],c)


def test_controller_disposition_is_advisory_not_command(tmp_path):
    """ACK #77-80 are CONTROLLER_DISPOSITION, never promoted to COMMAND."""
    c=binding(tmp_path)
    cmd='<!-- dw.taskcontroller.communication/v2 -->\nrun: '+c['run']['id']+'\nseq: 1\nfrom: GPT\nto: Hermes\nkind: COMMAND\nsource_ref: github://owner/repo/issues/1\nreply_to: https://github.com/owner/repo/issues/1#issuecomment-1\n\nDo work'
    ack='<!-- dw.taskcontroller.communication/v2 -->\nrun: '+c['run']['id']+'\nseq: 2\nfrom: GPT Controller\nto: Hermes Mac\nkind: CONTROLLER_DISPOSITION\nsource_ref: github://owner/repo/issues/1\nreply_to: https://github.com/owner/repo/issues/1#issuecomment-1\n\nEngineering Delivery Closed; Local Evidence Package Accepted.'
    rows=[{'body':cmd,'id':100,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-100','user':{'login':'owner'}},
          {'body':ack,'id':101,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-101','user':{'login':'owner'}}]
    r=select_human_communication(rows,c)
    # The disposition is advisory correlation evidence only.
    assert r['seq']==1 and r['kind']=='COMMAND' and r['evidence_class']=='HUMAN_COMMUNICATION_ONLY'
    assert r['latest_communication_seq']==2
    assert len(r['dispositions'])==1
    d=r['dispositions'][0]
    assert d['seq']==2 and d['kind']=='CONTROLLER_DISPOSITION'
    assert d['evidence_class']=='CONTROLLER_DISPOSITION_ADVISORY'
    assert d['authority_granted'] is False and d['typed_ce_admitted'] is False
    assert d['workflow_resume_allowed'] is False
    # The disposition must never be reachable as an executable command.
    assert r['comment_id']==100


def test_disposition_missing_source_ref_fails_closed(tmp_path):
    c=binding(tmp_path)
    ack='<!-- dw.taskcontroller.communication/v2 -->\nrun: '+c['run']['id']+'\nseq: 2\nfrom: GPT Controller\nto: Hermes Mac\nkind: CONTROLLER_DISPOSITION\nreply_to: https://github.com/owner/repo/issues/1#issuecomment-1\n\nClosed'
    with pytest.raises(ValueError,match='DISPOSITION_SOURCE_BINDING_INVALID'):
        select_human_communication([{'body':ack,'id':101,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-101','user':{'login':'owner'}}],c)


def test_disposition_unknown_actor_label_fails_closed(tmp_path):
    c=binding(tmp_path)
    ack='<!-- dw.taskcontroller.communication/v2 -->\nrun: '+c['run']['id']+'\nseq: 2\nfrom: Attacker Bot\nto: Hermes Mac\nkind: CONTROLLER_DISPOSITION\nsource_ref: github://owner/repo/issues/1\nreply_to: https://github.com/owner/repo/issues/1#issuecomment-1\n\nClosed'
    with pytest.raises(ValueError,match='DISPOSITION_ACTOR_LABEL_INVALID'):
        select_human_communication([{'body':ack,'id':101,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-101','user':{'login':'owner'}}],c)


def test_disposition_duplicate_sequence_fails_closed(tmp_path):
    c=binding(tmp_path)
    ack='<!-- dw.taskcontroller.communication/v2 -->\nrun: '+c['run']['id']+'\nseq: 2\nfrom: GPT Controller\nto: Hermes Mac\nkind: CONTROLLER_DISPOSITION\nsource_ref: github://owner/repo/issues/1\nreply_to: https://github.com/owner/repo/issues/1#issuecomment-1\n\nClosed'
    with pytest.raises(ValueError,match='DISPOSITION_DUPLICATE_SEQ'):
        select_human_communication([
            {'body':ack,'id':101,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-101','user':{'login':'owner'}},
            {'body':ack,'id':102,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-102','user':{'login':'owner'}}],c)


def test_disposition_wrong_issue_binding_fails_closed(tmp_path):
    c=binding(tmp_path)
    ack='<!-- dw.taskcontroller.communication/v2 -->\nrun: '+c['run']['id']+'\nseq: 2\nfrom: GPT Controller\nto: Hermes Mac\nkind: CONTROLLER_DISPOSITION\nsource_ref: github://owner/repo/issues/999\nreply_to: https://github.com/owner/repo/issues/999#issuecomment-1\n\nClosed'
    with pytest.raises(ValueError,match='DISPOSITION_SOURCE_BINDING_INVALID'):
        select_human_communication([{'body':ack,'id':101,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-101','user':{'login':'owner'}}],c)
