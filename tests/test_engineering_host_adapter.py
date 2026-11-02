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


def test_terminal_controller_disposition_is_separate_from_executable_command(tmp_path):
    c=binding(tmp_path)
    command='<!-- dw.taskcontroller.communication/v2 -->\nrun: '+c['run']['id']+'\nseq: 79\nfrom: GPT\nto: Hermes\nkind: COMMAND\nsource_ref: github://owner/repo/issues/1\nreply_to: https://github.com/owner/repo/issues/1#issuecomment-6290784422\n\nWork'
    disposition=('<!-- dw.taskcontroller.communication/v2 -->\n### A2A v2 · ACK #80\nrun: '+c['run']['id']+
        '\nseq: 80\nfrom: GPT Controller\nto: Hermes Mac / DWA\nkind: CONTROLLER_DISPOSITION\n'
        'source_ref: github://owner/repo/issues/1\nreply_to: https://github.com/owner/repo/issues/1#issuecomment-6290623979\n\n'
        'FINAL CONTROLLER DISPOSITION: ACCEPT LOCAL_EVIDENCE ENGINEERING CAMPAIGN AS TERMINAL; '
        'NO FURTHER ENGINEERING/CONTROLLER ITERATION REQUIRED. Parent UR.G2 / RUN_NOT_COMPLETE.')
    rows=[{'body':command,'id':6290784422,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-6290784422','user':{'login':'owner'}},
          {'body':disposition,'id':6290784423,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-6290784423','user':{'login':'owner'}}]
    result=select_human_communication(rows,c)
    assert result['comment_id']==6290784422 and result['kind']=='COMMAND'
    assert result['latest_communication_seq']==80
    assert result['dispositions'][0]['comment_id']==6290784423
    assert result['dispositions'][0]['kind']=='CONTROLLER_DISPOSITION'
    assert result['dispositions'][0]['child_terminal_accepted'] is True
    assert result['dispositions'][0]['parent_terminal'] is False
    assert result['dispositions'][0]['evidence_class']=='CONTROLLER_DISPOSITION_ADVISORY'


@pytest.mark.parametrize('mutation', ['source','actor','author','run','seq','comment_url','reply_to','marker'])
def test_terminal_disposition_malformed_or_spoofed_fails_closed(tmp_path,mutation):
    c=binding(tmp_path)
    body=('<!-- dw.taskcontroller.communication/v2 -->\nrun: '+c['run']['id']+
          '\nseq: 80\nfrom: GPT Controller\nto: Hermes Mac / DWA\nkind: CONTROLLER_DISPOSITION\n'
          'source_ref: github://owner/repo/issues/1\nreply_to: https://github.com/owner/repo/issues/1#issuecomment-6290623979\n\n'
          'FINAL CONTROLLER DISPOSITION: ACCEPT LOCAL_EVIDENCE ENGINEERING CAMPAIGN AS TERMINAL; '
          'NO FURTHER ENGINEERING/CONTROLLER ITERATION REQUIRED.')
    row={'body':body,'id':6290784423,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-6290784423','user':{'login':'owner'}}
    if mutation=='source':row['body']=body.replace('github://owner/repo/issues/1','github://owner/repo/issues/2')
    elif mutation=='actor':row['body']=body.replace('GPT Controller','Unknown Controller')
    elif mutation=='author':row['user']['login']='attacker'
    elif mutation=='run':row['body']=body.replace(c['run']['id'],'other-run')
    elif mutation=='seq':row['body']=body.replace('seq: 80','seq: not-a-number')
    elif mutation=='comment_url':row['html_url']='https://github.com/owner/repo/issues/1#issuecomment-7'
    elif mutation=='reply_to':row['body']=body.replace('issues/1#issuecomment','issues/2#issuecomment')
    elif mutation=='marker':row['body']=body.replace('<!-- dw.taskcontroller.communication/v2 -->','<!-- other -->')
    with pytest.raises(ValueError):
        select_human_communication([row],c)


def test_stale_terminal_disposition_cannot_override_newer_command(tmp_path):
    c=binding(tmp_path)
    command='<!-- dw.taskcontroller.communication/v2 -->\nrun: '+c['run']['id']+'\nseq: 81\nfrom: GPT\nto: Hermes\nkind: COMMAND\nsource_ref: github://owner/repo/issues/1\nreply_to: https://github.com/owner/repo/issues/1#issuecomment-6290784422\n\nContinue'
    disposition=('<!-- dw.taskcontroller.communication/v2 -->\nrun: '+c['run']['id']+
        '\nseq: 80\nfrom: GPT Controller\nto: Hermes Mac / DWA\nkind: CONTROLLER_DISPOSITION\n'
        'source_ref: github://owner/repo/issues/1\nreply_to: https://github.com/owner/repo/issues/1#issuecomment-6290623979\n\n'
        'FINAL CONTROLLER DISPOSITION: ACCEPT LOCAL_EVIDENCE ENGINEERING CAMPAIGN AS TERMINAL; '
        'NO FURTHER ENGINEERING/CONTROLLER ITERATION REQUIRED.')
    rows=[{'body':command,'id':6290784422,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-6290784422','user':{'login':'owner'}},
          {'body':disposition,'id':6290784423,'html_url':'https://github.com/owner/repo/issues/1#issuecomment-6290784423','user':{'login':'owner'}}]
    with pytest.raises(ValueError,match='DISPOSITION_STALE'):
        select_human_communication(rows,c)
