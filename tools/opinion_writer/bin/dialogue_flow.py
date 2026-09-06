"""Notice → legal questionnaire → answers in the same conversation → editable opinion.

This module enforces the order and preserves the case binding. The conversational
AI reads the supplied documents and uses legal tools; this script does not infer law.
"""
from __future__ import annotations
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from document_runtime import HERE, bootstrap

CATEGORIES={'non_imposition':'불처분·예정 처분 철회 또는 변경','mitigation':'감경','exemption':'면제','substitution':'과징금 등 대체 처분','procedure':'절차·권한·기간'}
ASSESSMENTS={'unknown':'답변·추가 검토 필요','possible':'요건 충족 여부 확인','not_applicable':'현재 확인 범위에서 적용 곤란'}
ANSWER_STATES={'answered','unknown','not_applicable'}


def initial_state(audience='professional'):
    return {'version':1,'audience':audience,'criteria':[],'questions':[],'answers':[],
            'checklists':[],'responses':[]}


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def checklist_payload(case):
    flow=case['workflow']
    law_ids=set(case['procedure'].get('law_ids',[]))
    for criterion in flow['criteria']:law_ids.update(criterion.get('law_ids',[]))
    return {'notice':case['notice'],'procedure':case['procedure'],'audience':flow['audience'],
            'criteria':flow['criteria'],'questions':flow['questions'],
            'laws':[x for x in case['legal_review'] if x['id'] in law_ids],
            'notices':[x for x in case['sources'] if x['role']=='notice']}


def validate_questionnaire(case):
    import case_workflow as cw
    errors=[]
    flow=case.get('workflow')
    if not flow:return ['질문지 우선 흐름이 없는 이전 사건입니다. 새 사건으로 시작하거나 명시적으로 이전하세요.']
    if flow.get('audience') not in {'professional','self'}:errors.append('이용자 유형은 professional 또는 self입니다.')
    if not any(s.get('role')=='notice' for s in case['sources']):errors.append('처분청 통지 원문이 필요합니다.')
    for key in ['title','authority','deadline']:
        if not case['notice'].get(key):errors.append('공문에서 '+key+'를 확인하거나 확인 필요로 적으세요.')
    if not case['notice'].get('sanctions'):errors.append('통지된 처분의 종류·범위·기간 또는 금액을 먼저 기록하세요.')
    criteria=flow.get('criteria',[]);questions=flow.get('questions',[])
    if not {'non_imposition','mitigation'}<={x.get('category') for x in criteria}:
        errors.append('불처분·철회/변경과 감경 요건의 검토 결과가 각각 필요합니다. 근거가 없으면 적용 곤란/확인 필요로 기록하세요.')
    cids=[x.get('id') for x in criteria];qids=[x.get('id') for x in questions]
    if not cids or len(cids)!=len(set(cids)) or None in cids:errors.append('요건 ID가 없거나 중복되었습니다.')
    if not qids or len(qids)!=len(set(qids)) or None in qids:errors.append('질문 ID가 없거나 중복되었습니다.')
    laws=cw.index(case['legal_review'])
    required=['citation','source_url','source_excerpt','as_of','version','checked_at','analysis']
    for law in laws.values():
        if law.get('status')=='verified' and any(not law.get(k) or law.get(k)==cw.UNKNOWN for k in required):
            errors.append(law['id']+': 확인한 법령의 원문·출처·시행 버전·기준일·검토 기록이 필요합니다.')
    for c in criteria:
        if c.get('category') not in CATEGORIES or c.get('assessment') not in ASSESSMENTS:errors.append(c.get('id','요건')+': 검토 구분 오류')
        if not c.get('requirement') or not c.get('analysis'):errors.append(c.get('id','요건')+': 법적 요건과 이 사건에서 확인할 이유가 필요합니다.')
        if c.get('assessment')!='unknown' and not c.get('law_ids'):errors.append(c['id']+': 적용 가능/곤란 판단의 법령 근거가 필요합니다.')
        for lid in c.get('law_ids',[]):
            if lid not in laws:errors.append(c['id']+': 없는 법령 ID '+lid)
            elif c.get('assessment')!='unknown' and laws[lid].get('status')!='verified':errors.append(c['id']+': 법령 미확인 상태에서 요건을 단정할 수 없습니다.')
    for q in questions:
        if not q.get('question') or not q.get('why'):errors.append(q.get('id','질문')+': 질문과 확인 이유가 필요합니다.')
        if not q.get('criterion_ids'):errors.append(q.get('id','질문')+': 연결 법적 요건이 필요합니다.')
        for cid in q.get('criterion_ids',[]):
            if cid not in cids:errors.append(q['id']+': 없는 법적 요건 '+cid)
    for c in criteria:
        if not any(c['id'] in q.get('criterion_ids',[]) for q in questions):errors.append(c['id']+': 확인할 상담 질문이 없습니다.')
    return errors


def _raw_integrity(case,root):
    import case_workflow as cw
    for source in case['sources']:
        path=(Path(root)/source['path']).resolve()
        if Path(root).resolve() not in path.parents or not path.is_file() or cw.file_hash(path)!=source['sha256']:
            raise ValueError('원문이 누락되거나 변경되었습니다: '+source['id'])


def questionnaire_markdown(case,checklist_id):
    import case_workflow as cw
    flow=case['workflow'];self_mode=flow['audience']=='self';notice=case['notice'];laws=cw.index(case['legal_review'])
    lines=['# 행정처분 사전통지 대응 질문지','',f'질문지 번호: {checklist_id} / 사건: {case["case_id"]}',
           '이용 방식: '+('본인이 직접 답하는 질문지' if self_mode else '행정사가 잠재 의뢰인에게 확인할 상담 질문지'),'',
           '공문에 적힌 위반은 처분청의 주장입니다. 이 질문지는 사실을 인정하도록 요구하는 문서가 아닙니다. 사실과 다른 부분, 기억나지 않는 부분, 반대 자료도 함께 적어 주세요.',
           '답변을 이 대화창에 그대로 붙여 넣거나, 질문지를 바탕으로 한 상담 채팅·녹취 전사문을 첨부하면 같은 사건의 초안 작성으로 이어집니다. 모르면 모름, 해당하지 않으면 해당 없음과 이유를 적습니다.','',
           '## 통지서에서 확인한 내용','',
           '- 통지 제목: '+notice.get('title',cw.UNKNOWN),'- 처분청: '+notice.get('authority',cw.UNKNOWN),
           '- 문서번호·시행일: '+notice.get('document_number',cw.UNKNOWN)+' / '+notice.get('issued_date',cw.UNKNOWN),
           '- 실제 받은 날: '+notice.get('received_date',cw.UNKNOWN),'- 의견제출기한: '+notice.get('deadline',cw.UNKNOWN),
           '- 제출처·방법: '+notice.get('department',cw.UNKNOWN)+' / '+notice.get('submission_method',cw.UNKNOWN)]
    for index,item in enumerate(notice['sanctions'],1):
        lines += [f'- 예정 처분 {index}: '+'; '.join(f'{key}: {value}' for key,value in item.items())]
    lines += ['', '사전통지 단계에서는 “처분하지 않거나 예정 내용을 철회·변경해 달라”는 요청을 검토합니다. 이미 확정된 처분의 취소·행정심판·소송과는 절차가 다릅니다.','','## 관련 규정과 확인할 요건','']
    for c in flow['criteria']:
        lines += ['### '+c['id']+' '+CATEGORIES[c['category']]+': '+c.get('title',''),'',
                  '- 규정상 요건: '+c['requirement'],'- 현재 검토: '+ASSESSMENTS[c['assessment']],'- 이 사건에서 확인할 점: '+c['analysis']]
        if not c.get('law_ids'):lines.append('- 근거 확인: '+cw.UNKNOWN+' — 확인 전에는 법령상 요건으로 단정하지 않습니다.')
        for lid in c.get('law_ids',[]):
            law=laws[lid]
            lines += ['- 근거: '+law.get('citation',cw.UNKNOWN)+' / '+law.get('version',cw.UNKNOWN),
                      '- 적용 기준일: '+law.get('as_of',cw.UNKNOWN),'- 확인한 원문 요지: '+law.get('source_excerpt',cw.UNKNOWN),
                      '- 출처: '+law.get('source_url',cw.UNKNOWN)]
        lines.append('')
    lines += ['## 답변할 질문','']
    for q in flow['questions']:
        lines += ['### '+q['id']+' '+q['question'],'','- 왜 확인하나요: '+q['why'],
                  '- 연결 요건: ',]
        lines[-1]='- 연결 요건: '+', '.join(q['criterion_ids'])
        if q.get('evidence_request'):lines.append('- 준비할 자료: '+q['evidence_request'])
        lines += ['- 답변: □ 예 □ 아니오 □ 모름 □ 해당 없음',
                  '- 구체적인 날짜·경위·설명: ____________________',
                  '- 자료가 있나요 / 파일명 또는 발급처: ____________________','']
    lines += ['## 다음 단계','',
              '1. 위 질문 번호와 함께 답변하거나 상담 기록을 같은 대화에 넣습니다.',
              '2. AI가 답변의 출처를 기록하고, 다툴 부분·감경 요건·추가 자료를 대조합니다.',
              '3. 미확인 내용은 확인 필요로 남긴 의견제출서와 별지, 수정 가능한 DOCX 및 소명자료 요청목록을 만듭니다.',
              '4. '+('본인이 사실·기한·첨부·서명을 확인하고 필요한 쟁점은 전문가에게 검토받습니다.' if self_mode else '담당 행정사가 법률 판단·진술·첨부·서명을 최종 확인합니다.'),
              '5. 발송·기관 접수는 별도 단계입니다. 이 도구는 자동 제출하지 않습니다.','']
    return '\n'.join(lines)


def validate_questionnaire_layout(pdf_path,questions):
    import pdfplumber
    ids={q['id'] for q in questions};seen=[];errors=[];pending=None
    with pdfplumber.open(pdf_path) as pdf:
        for page_index,page in enumerate(pdf.pages,1):
            for line in (page.extract_text() or '').splitlines():
                start=next((qid for qid in ids if re.match(r'^'+re.escape(qid)+r'\s',line)),None)
                if start:
                    if pending:errors.append(pending[0]+': 답변란 끝을 찾지 못했습니다.')
                    pending=(start,page_index);seen.append(start)
                if '자료가있나요/파일명또는발급처:' in re.sub(r'\s+','',line) and pending:
                    if pending[1]!=page_index:errors.append(pending[0]+': 질문과 답변란이 다른 쪽입니다.')
                    pending=None
    if pending:errors.append(pending[0]+': 답변란 끝을 찾지 못했습니다.')
    if set(seen)!=ids or len(seen)!=len(ids):errors.append('질문 ID 누락 또는 중복')
    return {'passed':not errors,'errors':errors,'questions':seen}


def issue_checklist(case,path,render=True):
    import case_workflow as cw
    errors=validate_questionnaire(case)
    if errors:raise ValueError('\n'.join(errors))
    root=Path(path).resolve().parent;_raw_integrity(case,root)
    flow=case['workflow'];number=len(flow['checklists'])+1;cid=f'QSET-{number:03d}'
    while (root/'상담준비'/cid).exists():
        number+=1;cid=f'QSET-{number:03d}'
    directory=cw.checked_output(root/'상담준비'/cid)
    text=questionnaire_markdown(case,cid)
    markdown=directory/'상담_질문지.md';markdown.write_text(text,encoding='utf-8')
    answers={'case_id':case['case_id'],'checklist_id':cid,'answers':[{'question_id':q['id'],'answer':'','state':'unknown'} for q in flow['questions']]}
    (directory/'답변_양식.json').write_text(json.dumps(answers,ensure_ascii=False,indent=2),encoding='utf-8')
    if render:
        from text_document import write_text_document
        from document_runtime import convert_docx
        write_text_document(text,directory/'상담_질문지.docx')
        convert_docx(directory/'상담_질문지.docx',directory/'상담_질문지.pdf')
        layout=validate_questionnaire_layout(directory/'상담_질문지.pdf',flow['questions'])
        (directory/'질문지_레이아웃_검증.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2),encoding='utf-8')
        if not layout['passed']:raise ValueError('질문지 레이아웃 검증 실패: '+'; '.join(layout['errors']))
    record={'id':cid,'fingerprint':digest(checklist_payload(case)),'created_at':cw.now(),'path':str(markdown.relative_to(root))}
    flow['checklists'].append(record)
    case['events'].append({'at':cw.now(),'event':'questionnaire_generated','id':cid})
    return directory


def current_checklist(case):
    flow=case.get('workflow',{})
    if not flow.get('checklists'):raise ValueError('공문 분석·법률검토 후 질문지를 먼저 생성해야 합니다.')
    latest=flow['checklists'][-1]
    if latest['fingerprint']!=digest(checklist_payload(case)):
        raise ValueError('공문·법률 요건·질문이 바뀌었습니다. 새 질문지를 먼저 생성하고 답변을 다시 대조하세요.')
    return latest


def receive_response(case,path,source_path):
    import case_workflow as cw
    latest=current_checklist(case);root=Path(path).resolve().parent;_raw_integrity(case,root)
    sid=cw.add_source(case,root,source_path,'consultation')
    case['workflow']['responses'].append({'source_id':sid,'checklist_id':latest['id'],'received_at':cw.now()})
    case['events'].append({'at':cw.now(),'event':'questionnaire_response_received','source_id':sid,'checklist_id':latest['id']})
    return sid


def assert_draft_ready(case,path):
    import case_workflow as cw
    latest=current_checklist(case);flow=case['workflow'];_raw_integrity(case,Path(path).resolve().parent)
    responses=[r for r in flow['responses'] if r['checklist_id']==latest['id']]
    if not responses:raise ValueError('질문지에 대한 답변 또는 상담 기록을 먼저 받아야 합니다. 공문만으로 소명을 만들지 않습니다.')
    sources=cw.index(case['sources']);response_ids={r['source_id'] for r in responses}
    if any(sid not in sources or sources[sid]['role']!='consultation' for sid in response_ids):raise ValueError('답변 원문 연결이 잘못되었습니다.')
    questions={q['id'] for q in flow['questions']};answers={a.get('question_id'):a for a in flow.get('answers',[])}
    if set(answers)!=questions or len(answers)!=len(flow['answers']):raise ValueError('질문별 답변을 대조해야 합니다. 답하지 않은 질문은 unknown으로 기록하세요.')
    for qid,answer in answers.items():
        if answer.get('state') not in ANSWER_STATES or not answer.get('answer'):raise ValueError(qid+': 답변 또는 확인 필요 설명이 없습니다.')
        if answer['state']!='unknown':
            refs=answer.get('source_refs',[])
            if not refs or any(r.get('source_id') not in response_ids or not r.get('locator') for r in refs):
                raise ValueError(qid+': 받은 상담 원문의 쪽·행·시각을 연결하세요.')
    return latest


def session_path(conversation):
    import case_workflow as cw
    if not conversation:raise ValueError('같은 대화의 식별자를 --conversation으로 지정하세요. 여러 대화가 공유하는 임의 기본값을 사용하지 않습니다.')
    root=cw.checked_output(cw.OUTDIR/'대화연결')
    return root/(hashlib.sha256(conversation.encode()).hexdigest()+'.json')


def resolve_session(conversation):
    p=session_path(conversation)
    if not p.is_file():raise ValueError('이 대화에 연결된 사건이 없습니다. start로 통지서를 먼저 등록하세요.')
    record=json.loads(p.read_text());path=Path(record['case_path'])
    import case_workflow as cw
    if cw.OUTDIR.resolve() not in path.resolve().parents or not path.is_file():raise ValueError('대화의 사건 경로가 올바르지 않습니다.')
    return path


def status(case):
    flow=case.get('workflow',{})
    if not flow.get('checklists'):return '공문 분석과 법률검토를 마친 뒤 질문지 생성'
    try:current_checklist(case)
    except ValueError:return '공문 또는 질문 변경: 새 질문지 생성'
    if not any(r['checklist_id']==flow['checklists'][-1]['id'] for r in flow['responses']):return '같은 대화에서 질문지 답변 또는 상담 기록 대기'
    return '질문별 답변·사실·논거·소명자료 대조 후 초안 검토 및 생성'


def main():
    import case_workflow as cw
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
    start=sub.add_parser('start');start.add_argument('--conversation',default=os.environ.get('CODEX_THREAD_ID'));start.add_argument('--case-id');start.add_argument('--audience',choices=['professional','self'],default='professional');start.add_argument('--notice',action='append',required=True);start.add_argument('--new-case',action='store_true');start.add_argument('--demo',action='store_true')
    for command in ['status','questionnaire','respond','draft']:
        parser=sub.add_parser(command);parser.add_argument('--conversation',default=os.environ.get('CODEX_THREAD_ID'));parser.add_argument('--case')
        if command=='questionnaire':parser.add_argument('--no-render',action='store_true')
        if command=='respond':parser.add_argument('source')
        if command=='draft':parser.add_argument('--no-open',action='store_true')
    a=p.parse_args()
    if a.cmd=='start':
        binding=session_path(a.conversation)
        if binding.exists() and not a.new_case:raise ValueError('이 대화에는 이미 사건이 있습니다. status로 확인하거나 새 사건임을 확인한 뒤 --new-case를 지정하세요.')
        case_id=a.case_id or datetime.date.today().strftime('%Y%m%d')+'_'+uuid.uuid4().hex[:8]
        case=cw.new_case(case_id,'demo' if a.demo else 'real');case['workflow']=initial_state(a.audience)
        directory=cw.OUTDIR/'사건'/case_id
        if directory.exists():raise ValueError('같은 사건 ID가 이미 있습니다.')
        cw.checked_output(directory)
        for source in a.notice:cw.add_source(case,directory,source,'notice')
        path=directory/'case.json';cw.save_case(path,case)
        if binding.exists():
            archive=binding.with_name(binding.stem+'_'+uuid.uuid4().hex[:8]+'.json');archive.write_bytes(binding.read_bytes())
        binding.write_text(json.dumps({'case_id':case_id,'case_path':str(path.resolve())},ensure_ascii=False,indent=2))
        print(json.dumps({'case':str(path),'next':status(case)},ensure_ascii=False));return
    path=Path(a.case).resolve() if a.case else resolve_session(a.conversation)
    old=cw.file_hash(path);case=cw.read_case(path)
    if a.cmd=='status':print(json.dumps({'case':str(path),'next':status(case)},ensure_ascii=False));return
    if a.cmd=='questionnaire':
        directory=issue_checklist(case,path,not a.no_render);cw.save_case(path,case,old);print(directory);print(status(case))
    elif a.cmd=='respond':
        sid=receive_response(case,path,a.source);cw.save_case(path,case,old);print('답변 원문',sid);print(status(case))
    elif a.cmd=='draft':
        assert_draft_ready(case,path);cw.make_draft(case,path,no_open=a.no_open)


if __name__=='__main__':
    bootstrap()
    try:main()
    except (ValueError,KeyError,RuntimeError) as error:raise SystemExit(str(error))
