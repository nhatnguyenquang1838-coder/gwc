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
