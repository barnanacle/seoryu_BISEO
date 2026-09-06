#!/usr/bin/env python3
"""사건별 원문 보존·법률검토·논거와 증빙 연결·초안 버전 관리.
내용 해석과 법령 조회는 담당 AI/행정사가 수행한다. 이 CLI는 그 결과를 검증·출력한다.
"""
import argparse,copy,datetime,hashlib,json,re,shutil,sys
from pathlib import Path
from build_pdf import HERE,OUTDIR,UNKNOWN,build,checked_output

EVIDENCE_STATES={'planned':'요청 예정','requested':'요청함','received':'수령·미검토','verified':'검토 완료','unavailable':'확보 불가','replaced':'교체됨','withdrawn':'철회'}
FACT_STATES={'reported','verified','disputed','unknown'}
ARG_STATES={'active','hold','withdrawn'}
PROCEDURES={'general','hearing','fine','special','unconfirmed'}

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read_case(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def index(items):return {x['id']:x for x in items}

def save_case(path,case,old_hash=None):
 path=Path(path).resolve();checked_output(path.parent)
 if path.exists() and old_hash and file_hash(path)!=old_hash:raise ValueError('사건 파일이 외부에서 변경되었습니다. 다시 읽고 수정하십시오.')
 # 교체 전 JSON도 버전으로 남긴다. 원문은 절대 갱신하지 않는다.
 if path.exists():
  history=checked_output(path.parent/'기록');n=len(list(history.glob('case_*.json')))+1
  with (history/('case_%04d.json'%n)).open('x',encoding='utf-8') as f:f.write(path.read_text(encoding='utf-8'))
 temp=path.with_name('.case_write.json')
 with temp.open('x',encoding='utf-8') as f:json.dump(case,f,ensure_ascii=False,indent=2)
 temp.replace(path)

def guarded_input(path):
 requested=Path(path).expanduser();p=requested.resolve()
 if any(x in {'.private','credentials','.codex','.claude'} or x.startswith('.env') for x in requested.parts+p.parts) or requested.name=='.claude.json' or p.name=='.claude.json':raise ValueError('비밀값·설정 경로는 입력할 수 없습니다.')
 if not p.is_file():raise ValueError('입력 파일 없음: '+str(p))
 if p.suffix.lower() not in {'.pdf','.md','.txt','.json','.csv','.docx','.xlsx','.png','.jpg','.jpeg','.webp'}:raise ValueError('지원 원문: PDF·텍스트·문서·표·이미지. 음성은 확인된 전사문을 넣으십시오.')
 return p

def add_source(case,root,path,role):
 p=guarded_input(path);sid='S%03d'%(max([int(s['id'][1:]) for s in case['sources']]+[0])+1)
 raw=checked_output(Path(root)/'원문');name=sid+'_'+p.name;target=raw/name
 if target.exists():raise ValueError('원문 대상 경로가 이미 있습니다.')
 shutil.copy2(p,target)
 case['sources'].append({'id':sid,'role':role,'path':str(target.relative_to(root)),'sha256':file_hash(target),'received_at':now()})
 return sid

def new_case(case_id,mode='real'):
 from dialogue_flow import initial_state
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}',case_id):raise ValueError('사건 ID는 영문·숫자·밑줄·하이픈 1~60자입니다.')
 return {'schema_version':2,'case_id':case_id,'mode':mode,'created_at':now(),
  'notice':{'title':UNKNOWN,'document_number':UNKNOWN,'issued_date':UNKNOWN,'received_date':UNKNOWN,'deadline':UNKNOWN,'recipient':UNKNOWN,'authority':UNKNOWN,'department':UNKNOWN,'submission_method':UNKNOWN,'sanctions':[],'stage':'pre_notice'},
  'procedure':{'kind':'unconfirmed','analysis':UNKNOWN,'law_ids':[],'form':{'type':'unconfirmed','reviewed':False,'basis':UNKNOWN}},
  'sources':[],'facts':[],'legal_review':[],'issues':[],'arguments':[],'evidence':[],
  'draft':{'fields':{'의견제출인_성명':UNKNOWN,'의견제출인_명칭':UNKNOWN,'의견제출인_주소':UNKNOWN,'의견제출인_전화번호':UNKNOWN,'당사자_명칭':UNKNOWN,'당사자_주소':UNKNOWN,'당사자_전화번호':UNKNOWN,'의견제출인_서명':UNKNOWN,'작성일':UNKNOWN,'처분의_제목':UNKNOWN,'처분청':UNKNOWN,'수신':UNKNOWN,'건명':UNKNOWN,'대상_표시':'','취지':UNKNOWN,'결어':UNKNOWN,'의견':'별지로 작성','기타':'별지로 작성','파일명':case_id}},
  'document_review':{},'events':[],'workflow':initial_state()}

def dependency_payload(case,arg):
 payload={k:arg.get(k) for k in ['id','title','body','status','fact_ids','law_ids','evidence_ids']}
 for target,ref in [('facts','fact_ids'),('legal_review','law_ids'),('evidence','evidence_ids')]:
  source=index(case[target]);payload[target]=[source.get(k,{'missing':k}) for k in arg.get(ref,[])]
 payload['notice']=case['notice'];payload['procedure']=case['procedure'];payload['sources']=case['sources']
 return payload

def argument_fingerprint(case,arg):return digest(dependency_payload(case,arg))
def document_fingerprint(case):return digest({k:case[k] for k in ['notice','procedure','draft','sources','facts','legal_review','evidence']}|{'arguments':[{k:v for k,v in a.items() if k!='review'} for a in case['arguments']],'workflow':case.get('workflow')})

def validate(case,root,require_review=True):
 errors=[];warnings=[];root=Path(root).resolve()
 if case.get('schema_version')!=2:errors.append('schema_version은 2여야 합니다.')
 for field in ['sources','facts','legal_review','issues','arguments','evidence']:
  if not isinstance(case.get(field),list):errors.append(field+'는 배열이어야 합니다.');continue
  ids=[x.get('id') for x in case[field] if isinstance(x,dict)]
  if len(ids)!=len(case[field]) or len(ids)!=len(set(ids)) or any(not x for x in ids):errors.append(field+'의 ID가 없거나 중복되었습니다.')
 if errors:return errors,warnings
 sources=index(case['sources']);facts=index(case['facts']);laws=index(case['legal_review']);evidence=index(case['evidence'])
 for s in sources.values():
  p=(root/s.get('path','')).resolve()
  if root not in p.parents:errors.append(s['id']+': 원문은 사건 폴더 안이어야 합니다.');continue
  if not p.is_file() or file_hash(p)!=s.get('sha256'):errors.append(s['id']+': 원문이 없거나 내용이 바뀌었습니다. 새 원문 ID로 추가하십시오.')
 for f in facts.values():
  if f.get('status') not in FACT_STATES:errors.append(f['id']+': 사실 확인 상태 오류')
  if not f.get('source_refs'):errors.append(f['id']+': 진술/공문/증빙의 출처 위치 필요')
  for ref in f.get('source_refs',[]):
   if ref.get('source_id') not in sources or not ref.get('locator'):errors.append(f['id']+': source_id와 쪽·행·시각 필요')
 for law in laws.values():
  if law.get('status') not in {'verified','unverified'}:errors.append(law['id']+': 법령 확인 상태 오류')
  if law.get('status')=='verified' and any(not law.get(k) or law.get(k)==UNKNOWN for k in ['citation','source_url','source_excerpt','as_of','version','checked_at','analysis']):errors.append(law['id']+': 확인한 원문·시행 버전·기준일·출처·적용 판단 필요')
 for e in evidence.values():
  if e.get('status') not in EVIDENCE_STATES:errors.append(e['id']+': 자료 상태 오류')
  if e.get('status') in {'received','verified'} and not e.get('source_ids'):errors.append(e['id']+': 실제 수령 파일의 source_ids 필요')
  if e.get('status')=='verified' and (e.get('finding') not in {'supports','partial','contradicts'} or not e.get('review_note')):errors.append(e['id']+': 자료 검토 결과와 메모 필요')
  for sid in e.get('source_ids',[]):
   if sid not in sources:errors.append(e['id']+': 없는 원문 ID '+sid)
  if e.get('include_in_attachment') and e.get('status')!='verified':errors.append(e['id']+': 검토 완료한 자료만 첨부 예정으로 지정 가능')
  if e.get('finding') in {'contradicts','partial'}:warnings.append(e['id']+': 주장과 '+('불일치' if e['finding']=='contradicts' else '부분 일치')+' — 논거 재검토')
 active=[]
 for a in case['arguments']:
  if a.get('status') not in ARG_STATES:errors.append(a['id']+': 주장 상태 오류')
  if a.get('status')!='active':continue
  active.append(a)
  if not a.get('title') or not a.get('body'):errors.append(a['id']+': 제목·본문 필요')
  for refs,items in [('fact_ids',facts),('law_ids',laws),('evidence_ids',evidence)]:
   if not isinstance(a.get(refs,[]),list):errors.append(a['id']+': '+refs+' 배열 필요');continue
   for rid in a.get(refs,[]):
    if rid not in items:errors.append(a['id']+': 없는 참조 '+rid)
  for lid in a.get('law_ids',[]):
   if lid in laws and laws[lid].get('status')!='verified':errors.append(a['id']+': 미확인 법령 '+lid+'를 확정 근거로 사용할 수 없습니다.')
  for fid in a.get('fact_ids',[]):
   if fid in facts and facts[fid].get('status') in {'unknown','disputed'} and UNKNOWN not in a.get('body',''):errors.append(a['id']+': 미확인/상충 사실 '+fid+'의 본문에 확인 필요 표시가 필요합니다.')
  if not a.get('fact_ids') and not a.get('law_ids'):warnings.append(a['id']+': 사실·법령 근거가 없는 논거')
  if require_review and a.get('review',{}).get('fingerprint')!=argument_fingerprint(case,a):errors.append(a['id']+': 신규/변경 논거·증빙에 대한 본문 재검토 필요')
 if not active:warnings.append('활성화된 소명 논거가 없습니다.')
 proc=case.get('procedure',{});form=proc.get('form',{})
 if proc.get('kind') not in PROCEDURES:errors.append('절차 분류 오류')
 if case.get('notice',{}).get('stage') not in {'pre_notice','hearing_notice'}:errors.append('사전 의견제출 단계가 아닙니다. 확정 처분·불복·민원 절차는 별도 검토하십시오.')
 if form.get('type') not in {'standard11','custom','unconfirmed'}:errors.append('서식 종류 오류')
 if form.get('type')!='unconfirmed':
  if not form.get('reviewed') or not form.get('basis') or form.get('basis')==UNKNOWN:errors.append('공식 서식 사용 근거와 적용 검토 완료 표시 필요')
  if proc.get('kind')=='unconfirmed':errors.append('절차 미분류 상태에서 공식 서식을 확정할 수 없습니다.')
  if not proc.get('law_ids'):errors.append('서식 적용의 확인된 법령 ID 필요')
  for lid in proc.get('law_ids',[]):
   if lid not in laws or laws[lid].get('status')!='verified':errors.append('절차 근거 미확인: '+lid)
 if form.get('type')=='custom' and (not form.get('source_id') or form.get('source_id') not in sources or not form.get('boxes')):errors.append('기관 서식의 보존 원문 source_id와 검토된 boxes 필요')
 if form.get('type')=='unconfirmed':warnings.append('제출 서식 미확인: 법정서식으로 표시하지 않는 일반 표지를 생성합니다.')
 fields=case.get('draft',{}).get('fields',{})
 for k in ['작성일','처분의_제목','처분청','의견제출인_성명','취지','결어']:
  if not fields.get(k) or fields[k]==UNKNOWN:warnings.append(k+': '+UNKNOWN)
 if case.get('mode')=='real':
  deadline=case['notice'].get('deadline','')
  if re.fullmatch(r'\d{4}-\d{2}-\d{2}',deadline) and datetime.date.fromisoformat(deadline)<datetime.date.today():warnings.append('통지서 제출기한이 지났습니다. 현 절차·기한 연장 승인 여부를 확인하십시오.')
 if require_review and case.get('document_review',{}).get('fingerprint')!=document_fingerprint(case):errors.append('취지·결어·서식·전체 주장에 대한 최종 초안 재검토 필요')
 return errors,warnings

def review(case,root,reviewer,note):
 errors,_=validate(case,root,require_review=False)
 if errors:raise ValueError('\n'.join(errors))
 if not reviewer.strip() or not note.strip():raise ValueError('검토자와 본문 검토 메모가 필요합니다.')
 for a in case['arguments']:
  if a.get('status')=='active':a['review']={'fingerprint':argument_fingerprint(case,a),'reviewer':reviewer,'note':note,'at':now()}
 case['document_review']={'fingerprint':document_fingerprint(case),'reviewer':reviewer,'note':note,'at':now()}
 case['events'].append({'at':now(),'event':'draft_review','reviewer':reviewer,'note':note})

def used_evidence(case):
 ids={i for a in case['arguments'] if a.get('status')=='active' for i in a.get('evidence_ids',[])}
 return [e for e in case['evidence'] if e['id'] in ids]

def evidence_display_order(case):
 # Internal E IDs stay stable; each output version gets ordinary document numbers.
 return sorted(used_evidence(case),key=lambda e:not(e.get('status')=='verified' and e.get('include_in_attachment')))

def evidence_display_labels(case):
 return {e['id']:f'소명자료 {n}' for n,e in enumerate(evidence_display_order(case),1)}

def public_evidence_references(text,labels):
 # Only explicit reference tokens are replaced. Product/model codes such as E001 stay literal.
 for eid,label in labels.items():
  text=text.replace('['+eid+']',label)
 return text

def compiled_fields(case,root):
 f=copy.deepcopy(case['draft']['fields']);f['소명']=[]
 labels=evidence_display_labels(case)
 for key in ['취지','결어']:
  if key in f:f[key]=public_evidence_references(f[key],labels)
 for a in case['arguments']:
  if a.get('status')=='active':
   refs=' · '.join(labels[i] for i in a.get('evidence_ids',[]))
   f['소명'].append({'제목':a['title'],'본문':public_evidence_references(a['body'],labels)+ ('\n\n관련 자료: '+refs if refs else '')})
 attached=[];pending=[]
 for e in evidence_display_order(case):
  line=labels[e['id']]+'. '+e['title']
  if e.get('status')=='verified' and e.get('include_in_attachment'):attached.append(line+' — 검토 완료·첨부 예정')
  else:pending.append(line+' — '+EVIDENCE_STATES[e['status']]+'; '+UNKNOWN)
 f['소명자료_목록']='검토 완료·첨부 예정 자료\n'+('\n'.join(attached) if attached else '현재 지정된 자료 없음')+'\n\n추가 확보·검토할 자료\n'+('\n'.join(pending) if pending else '없음')+'\n\n※ 증빙은 별도로 첨부해야 합니다. 실제 첨부 여부 '+UNKNOWN+'.'
 f['자료목록_제목']='소명자료 검토 및 첨부 예정 목록'
 f['서식']=copy.deepcopy(case['procedure']['form'])
 if f['서식']['type']=='custom':f['서식']['pdf']=str((Path(root)/index(case['sources'])[f['서식']['source_id']]['path']).resolve())
 return f

def reports(case,root,warnings):
 args={a['id']:a for a in case['arguments']};evidence=evidence_display_order(case);labels=evidence_display_labels(case)
 requests=['# 소명자료 요청목록 초안','','아래 자료는 주장을 확인하기 위한 요청 목록입니다. 자동 발송하지 않습니다. 이미 확보한 자료는 추가 제출할 필요가 있는 부분만 확인합니다. 원본은 보존하고, 관련 없는 개인정보는 제출 사본에서 가립니다.','']
 matrix=['# 논거와 사실 법령 소명자료 대조표','']
 for e in evidence:
  if e.get('status') in {'withdrawn','replaced'}:continue
  related=[a['title'] for a in args.values() if a.get('status')=='active' and e['id'] in a.get('evidence_ids',[])]
  requests+=['## '+labels[e['id']]+'. '+e['title'],'','- 확인 목적: '+e.get('purpose',UNKNOWN),'- 관련 의견: '+' / '.join(related),'- 요청 내용: '+e.get('request',UNKNOWN),'- 범위·기간·필수 페이지: '+e.get('scope',UNKNOWN),'- 보유자·발급처: '+e.get('holder',UNKNOWN),'- 요청 기한: '+e.get('due_date',UNKNOWN),'- 현재 상태: '+EVIDENCE_STATES[e['status']],'- 대체 자료·확보 불가 시 대응: '+e.get('alternative',UNKNOWN),'']
 for a in args.values():matrix+=['## '+a['id']+' '+a['title']+' ['+a['status']+']','','- 사실: '+', '.join(a.get('fact_ids',[])),'- 법령: '+', '.join(a.get('law_ids',[])),'- 소명자료: '+', '.join(i+' ('+labels.get(i,'이번 버전 미표시')+')' for i in a.get('evidence_ids',[])),'- 본문 검토: '+a.get('review',{}).get('note',UNKNOWN),'']
 laws=['# 사건 법률검토','','절차: '+case['procedure']['kind'],'',case['procedure'].get('analysis',UNKNOWN),'']
 for law in case['legal_review']:laws+=['## '+law['id']+' '+law.get('citation',UNKNOWN),'','- 기준일: '+law.get('as_of',UNKNOWN),'- 시행 버전: '+law.get('version',UNKNOWN),'- 확인 상태: '+law.get('status',UNKNOWN),'- 공식 출처: '+law.get('source_url',UNKNOWN),'- 확인한 원문 요지: '+law.get('source_excerpt',UNKNOWN),'- 사건 적용 판단: '+law.get('analysis',UNKNOWN),'']
 for issue in case['issues']:laws+=['## '+issue['id']+' '+issue.get('title',UNKNOWN),'',issue.get('finding',UNKNOWN),'','추가 확인: '+' / '.join(issue.get('questions',[])),'']
 checks=['# 제출 전 확인사항','','이 결과물은 초안입니다. '+('본인이 사실을 확인하고 필요한 법률 쟁점은 전문가에게 검토받습니다.' if case.get('workflow',{}).get('audience')=='self' else '법률 판단·원문 의미의 정확성은 담당 행정사가 확인합니다.'),'']+['- '+w for w in warnings]+['','- 실제 작성일·당사자·서명권자·기한·수신처 확인','- 위반 인정 범위, 주위적·예비적 요청 및 근거의 정합성 확인','- 확보 불가·불일치 자료와 관련 문구가 함께 수정되었는지 확인','- 별지의 자료 목록과 실제 첨부 파일·쪽수 일치 확인','- 의뢰인 사실 확인, 서명·날인, 발송 및 기관 접수는 별도 수행']
 numbering=[{'internal_id':e['id'],'document_label':labels[e['id']],'title':e['title'],'status':e['status']} for e in evidence]
 return {'소명자료_요청목록.md':'\n'.join(requests),'논거_증빙_대조표.md':'\n'.join(matrix),'법률검토.md':'\n'.join(laws),'제출전_확인사항.md':'\n'.join(checks),'소명자료_번호대조표.json':json.dumps(numbering,ensure_ascii=False,indent=2)}

def changes(previous,current):
 if not previous:return '최초 초안입니다. 상담 진술과 실제 확보한 증빙을 구분하여 확인하십시오.'
 lines=[]
 for key in ['notice','procedure','draft','sources','facts','legal_review','arguments','evidence','workflow']:
  old=previous.get(key);new=current.get(key)
  if old==new:continue
  if isinstance(new,list) and all(isinstance(x,dict) and 'id' in x for x in new):
   before=index(old or []);after=index(new)
   for uid in sorted(set(before)|set(after)):
    a={k:v for k,v in before.get(uid,{}).items() if k!='review'};b={k:v for k,v in after.get(uid,{}).items() if k!='review'}
    if a!=b:
     labels=[k for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)]
     lines.append('- '+key+' '+uid+': '+', '.join(labels)+' 변경')
  else:lines.append('- '+key+' 변경')
 return '\n'.join(lines) or '내용 변경 없음. 검토 이력만 갱신되었습니다.'

def make_draft(case,path,no_open=False,render=True):
 from dialogue_flow import assert_draft_ready
 assert_draft_ready(case,path)
 root=Path(path).resolve().parent;errors,warnings=validate(case,root)
 if errors:raise ValueError('\n'.join(errors))
 versions=checked_output(root/'초안');dirs=sorted(x for x in versions.glob('v[0-9][0-9][0-9]') if x.is_dir())
 n=max([int(x.name[1:]) for x in dirs]+[0])+1
 if n>999:raise ValueError('버전이 999개를 초과했습니다.')
 previous=read_case(dirs[-1]/'사건_스냅샷.json') if dirs and (dirs[-1]/'사건_스냅샷.json').exists() else None
 out=versions/('v%03d'%n);out.mkdir()
 try:
  f=compiled_fields(case,root)
  for name,content in reports(case,root,warnings).items():(out/name).write_text(content+'\n',encoding='utf-8')
  (out/'수정내역.md').write_text('# 초안 수정내역\n\n'+changes(previous,case)+'\n',encoding='utf-8')
  (out/'fields.json').write_text(json.dumps(f,ensure_ascii=False,indent=2),encoding='utf-8')
  (out/'사건_스냅샷.json').write_text(json.dumps(case,ensure_ascii=False,indent=2),encoding='utf-8')
  result=build(f,out,no_open=no_open) if render else {'mode':'검증용 PDF 미생성'}
  (out/'생성결과.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 except Exception:
  (out/'생성실패.txt').write_text('생성 미완료. 이 버전은 제출용으로 사용하지 마십시오.\n')
  raise
 print('초안 버전:',out)
 return out

def intake(case,path):
 from dialogue_flow import issue_checklist
 return issue_checklist(case,path)

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
 a=sub.add_parser('init');a.add_argument('case_id');a.add_argument('--mode',choices=['real','demo'],default='real');a.add_argument('--notice',action='append',default=[]);a.add_argument('--consultation',action='append',default=[])
 for cmd in ['validate','review','build','intake','add-source','evidence']:
  a=sub.add_parser(cmd);a.add_argument('case')
  if cmd=='review':a.add_argument('--reviewer',required=True);a.add_argument('--note',required=True)
  if cmd=='build':a.add_argument('--no-open',action='store_true')
  if cmd=='add-source':a.add_argument('file');a.add_argument('--role',choices=['notice','consultation','evidence','form'],required=True)
  if cmd=='evidence':a.add_argument('id');a.add_argument('--status',choices=EVIDENCE_STATES,required=True);a.add_argument('--note',required=True);a.add_argument('--source',action='append');a.add_argument('--finding',choices=['supports','partial','contradicts','unreviewed'])
 a=p.parse_args(argv)
 if a.cmd=='init':
  c=new_case(a.case_id,a.mode);root=OUTDIR/'사건'/a.case_id
  if root.exists():raise ValueError('이미 존재하는 사건 ID입니다.')
  checked_output(root)
  for role,paths in [('notice',a.notice),('consultation',a.consultation)]:
   for path in paths:add_source(c,root,path,role)
  save_case(root/'case.json',c);print(root/'case.json');return
 path=Path(a.case).resolve();old=file_hash(path);c=read_case(path);root=path.parent
 if a.cmd=='validate':
  errors,warnings=validate(c,root)
  print(json.dumps({'errors':errors,'warnings':warnings},ensure_ascii=False,indent=2))
  if errors:raise SystemExit(1)
 elif a.cmd=='review':review(c,root,a.reviewer,a.note);save_case(path,c,old);print('초안 검토 기록 완료. 제출 승인과 별개입니다.')
 elif a.cmd=='build':make_draft(c,path,a.no_open)
 elif a.cmd=='intake':
  directory=intake(c,path);save_case(path,c,old);print(directory)
 elif a.cmd=='add-source':
  sid=add_source(c,root,a.file,a.role);c['events'].append({'at':now(),'event':'source_added','id':sid});save_case(path,c,old);print('추가된 원문:',sid,'기존 논거 재검토 필요')
 elif a.cmd=='evidence':
  if a.id not in index(c['evidence']):raise ValueError('없는 소명자료 ID')
  e=index(c['evidence'])[a.id];e.update({'status':a.status,'review_note':a.note})
  if a.source is not None:e['source_ids']=a.source
  if a.finding:e['finding']=a.finding
  if a.status!='verified':e['include_in_attachment']=False
  errors,_=validate(c,root,False)
  if errors:raise ValueError('\n'.join(errors))
  c['events'].append({'at':now(),'event':'evidence_changed','id':a.id,'note':a.note})
  save_case(path,c,old)
  print('재검토할 논거:',', '.join(x['id'] for x in c['arguments'] if a.id in x.get('evidence_ids',[])))
  print('취지·결어·관련 본문 수정 후 review → build. 자료 목록만 바꿔 재생성할 수 없습니다.')
if __name__=='__main__':
 from document_runtime import bootstrap
 bootstrap()
 try:main()
 except (ValueError,KeyError,RuntimeError) as e:print('오류:',e,file=sys.stderr);sys.exit(1)
