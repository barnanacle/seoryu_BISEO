"""Run synthetic notice-PDF → questionnaire → response → draft → evidence-change checks.
This is a developer test; the real dialogue must wait for the user's own response.
"""
from document_runtime import bootstrap
if __name__=='__main__':
    bootstrap()
    import argparse,copy,json,subprocess,sys,uuid
    from pathlib import Path
    import case_workflow as cw
    import dialogue_flow as flow
    from document_runtime import HERE,temp_root,convert_docx,sha256
    from text_document import write_text_document
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audience',choices=['professional','self','both'],default='both')
    parser.add_argument('--no-render',action='store_true')
    args=parser.parse_args();ex=HERE/'examples/식품위생_가상사례';results=[]
    work=temp_root()/('flow_demo_'+uuid.uuid4().hex[:8]);work.mkdir()
    notice=ex/'01_사전통지.txt'
    if not args.no_render:
        write_text_document(notice.read_text(encoding='utf-8'),work/'가상_사전통지.docx')
        convert_docx(work/'가상_사전통지.docx',work/'가상_사전통지.pdf');notice=work/'가상_사전통지.pdf'
    def cli(*argv,success=True):
        result=subprocess.run([sys.executable,str(HERE/'bin/dialogue_flow.py'),*map(str,argv)],capture_output=True,text=True)
        if (result.returncode==0)!=success:raise AssertionError(result.stdout+result.stderr)
        return result.stdout+result.stderr
    audiences=['professional','self'] if args.audience=='both' else [args.audience]
    for audience in audiences:
        cid='DEMO_'+audience+'_'+uuid.uuid4().hex[:8];conversation='opinion-test-'+cid
        cli('start','--conversation',conversation,'--case-id',cid,'--notice',notice,'--audience',audience,'--demo')
        path=flow.resolve_session(conversation);case=cw.read_case(path);root=path.parent
        assert len(case['sources'])==1 and case['sources'][0]['role']=='notice'
        assert '질문지' in cli('draft','--conversation',conversation,'--no-open',success=False)
        setup=json.loads((ex/'01_질문지설계.json').read_text(encoding='utf-8'))
        for key in ['notice','procedure','legal_review']:case[key]=setup[key]
        case['workflow'].update({key:setup[key] for key in ['criteria','questions']});cw.save_case(path,case)
        cli('questionnaire','--conversation',conversation,*(['--no-render'] if args.no_render else []))
        case=cw.read_case(path);questionnaire=root/case['workflow']['checklists'][-1]['path']
        assert questionnaire.is_file() and '관련 규정' in questionnaire.read_text(encoding='utf-8')
        assert not (root/'초안').exists()
        assert '답변 또는 상담' in cli('draft','--conversation',conversation,'--no-open',success=False)
        cli('respond','--conversation',conversation,ex/'02_답변.txt');case=cw.read_case(path)
        sid=case['workflow']['responses'][-1]['source_id'];assert sid=='S002'
        reviewed=json.loads((ex/'02_초안검토.json').read_text(encoding='utf-8'))
        for key in ['facts','arguments','evidence']:case[key]=reviewed[key]
        case['draft']['fields'].update(reviewed['fields']);case['draft']['fields']['파일명']=cid
        lines=(ex/'02_답변.txt').read_text(encoding='utf-8').splitlines()
        case['workflow']['answers']=[{'question_id':q['id'],'state':'answered','answer':lines[i+1].split('. ',1)[1],
            'source_refs':[{'source_id':sid,'locator':f'{q["id"]} 답변 / {i+2}행'}]} for i,q in enumerate(case['workflow']['questions'])]
        cw.review(case,root,'AI 개발 시험','가상 답변의 범위·불확실성·법령 원문 기록·주위적/예비적 취지와 자료 상태를 대조했다. 실제 사건 판단 아님.')
        cw.save_case(path,case)
        if args.no_render:cw.make_draft(case,path,no_open=True,render=False)
        else:cli('draft','--conversation',conversation,'--no-open')
        v1=root/'초안/v001';snapshot=sha256(v1/'사건_스냅샷.json')
        if not args.no_render:
            result=json.loads((v1/'생성결과.json').read_text(encoding='utf-8'))
            assert result['layout_passed'] and Path(result['full_docx']).is_file()
        assert '소명자료 1' in (v1/'소명자료_요청목록.md').read_text(encoding='utf-8')
        case['evidence'][1]['status']='unavailable'
        case['arguments'][1]['body']+='\n\n정비 사진 확보가 어렵다는 가상 변경 사항을 반영합니다. 정비 사실은 진술 범위로 한정하며 대체 자료는 【확인 필요】입니다.'
        correction=work/(cid+'_정정답변.txt');correction.write_text('가상 정정: 정비 사진을 확보하기 어렵습니다. 다른 작업 기록을 찾아보겠습니다.',encoding='utf-8')
        correction_id=flow.receive_response(case,path,correction)
        case['facts'].append({'id':'F007','text':'가상 정정 답변에서 정비 사진 확보가 어렵다고 말했다.','status':'reported','source_refs':[{'source_id':correction_id,'locator':'1행'}]})
        case['arguments'][1]['fact_ids'].append('F007');cw.save_case(path,case)
        assert '재검토' in cli('draft','--conversation',conversation,'--no-open',success=False)
        cw.review(case,root,'AI 개발 시험','새 답변과 확보 불가 자료에 맞춰 주장을 진술 범위로 한정하고 취지·결어와 대체자료 요청을 재검토했다.')
        cw.save_case(path,case)
        if args.no_render:cw.make_draft(case,path,no_open=True,render=False)
        else:cli('draft','--conversation',conversation,'--no-open')
        assert sha256(v1/'사건_스냅샷.json')==snapshot
        assert '확보 불가' in (root/'초안/v002/소명자료_요청목록.md').read_text(encoding='utf-8')
        results.append({'audience':audience,'case':str(path),'passed':True,'checks':['notice_pdf','questionnaire_first','wait_for_response','same_conversation','answer_citations','editable_docx_pdf','evidence_change_blocks','version_preserved']})
        print(audience,'PASS',path,flush=True)
    report=work/'flow_result.json';report.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FLOW_REPORT',report)
