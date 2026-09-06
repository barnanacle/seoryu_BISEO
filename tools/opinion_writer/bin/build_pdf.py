#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""의견제출서 렌더러. 법률 판단·상담 해석은 하지 않는다.
기존 fields 문자열 키 및 임의 개수의 소명 배열을 지원한다.
신규 사건은 case_workflow.py로 원문·논거·증빙을 검토한 뒤 생성한다.
"""
import argparse,copy,json,logging,re,shutil,sys,tempfile,zipfile
from pathlib import Path
from xml.sax.saxutils import escape
logging.getLogger('pypdf').setLevel(logging.ERROR)
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/'bin/_vendor'))
OUTDIR=HERE/'산출'
FORM_PDF=HERE/'서식/별지11호_의견제출서_공식서식.pdf'
FORM_PNG=HERE/'서식/별지11호_의견제출서_공식서식_배경.png'
ANNEX_DOCX=HERE/'서식/별지_상세의견서_템플릿.docx'
UNKNOWN='【확인 필요】'
FORM_KEYS=list(json.loads((HERE/'서식/layout_profile.json').read_text())['form'])

def normalize_fields(fields):
 f=copy.deepcopy(fields)
 if '소명' not in f:
  ix=sorted({int(m.group(1)) for k in f for m in [re.match(r'소명(\d+)_',k)] if m})
  f['소명']=[{'제목':f.get('소명%d_제목'%n,UNKNOWN),'본문':f.get('소명%d_본문'%n,UNKNOWN)} for n in ix]
 if not isinstance(f['소명'],list):raise ValueError('소명은 배열이어야 합니다.')
 for s in f['소명']:
  if not isinstance(s,dict) or not all(isinstance(s.get(k),str) for k in ['제목','본문']):raise ValueError('소명 항목에 제목·본문 문자열이 필요합니다.')
 f.setdefault('별지_제목','처분사전통지에 대한 상세 의견서')
 f.setdefault('대상_표시',f.get('해당_품목',''))
 if f['대상_표시'] and not f['대상_표시'].lstrip().startswith('('):f['대상_표시']='('+f['대상_표시']+')'
 from form_layout import normalized_address
 f['별지_주소']=normalized_address(f.get('의견제출인_주소') or UNKNOWN)
 date_match=re.fullmatch(r'\s*(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D*',str(f.get('작성일','')))
 f['별지_작성일']='.   '.join(str(int(x)) for x in date_match.groups())+'.' if date_match else UNKNOWN
 f.setdefault('별지_서명',f.get('의견제출인_서명') or str(f.get('의견제출인_명칭',UNKNOWN))+(' 대표 '+f['대표자'] if f.get('대표자') else ''))
 f.setdefault('자료목록_제목','소명자료 확보 및 제출 예정 목록')
 for k in FORM_KEYS+['취지','결어','건명','처분청','의견제출인_명칭','소명자료_목록']:
  if not str(f.get(k,'')).strip():f[k]=UNKNOWN
 return f



def _xml_lines(v):return '</w:t><w:br/><w:t xml:space="preserve">'.join(escape(x) for x in str(v).split('\n'))
def build_annex_docx(fields,out_path):
 f=normalize_fields(fields)
 with zipfile.ZipFile(ANNEX_DOCX) as z:xml=z.read('word/document.xml').decode()
 para_re=r'<w:p\b(?:(?!</w:p>).)*?</w:p>'
 paras=re.findall(para_re,xml,flags=re.S)
 title=next(p for p in paras if '{{소명_제목}}' in p)
 body=next(p for p in paras if '{{소명_본문}}' in p)
 def rep(m):
  p=m.group(0)
  if p==body:return ''
  if p==title:
   parts=[]
   for i,s in enumerate(f['소명'],1):
    parts.append(title.replace('{{소명_제목}}',_xml_lines(str(i)+'. '+s['제목'])))
    parts.extend(body.replace('{{소명_본문}}',_xml_lines(b)) for b in re.split(r'\n\s*\n',s['본문'].strip()))
   return ''.join(parts) or body.replace('{{소명_본문}}',UNKNOWN)
  keys=re.findall(r'\{\{([^{}]+)\}\}',p)
  if not keys:return p
  key=keys[0];value=str(f.get(key,UNKNOWN))
  if key=='소명자료_목록':
   blocks=[line for line in value.split('\n') if line.strip()]
   pieces=[]
   for i,block in enumerate(blocks):
    paragraph=p
    if i>=max(0,len(blocks)-2):
     if '<w:keepNext' in paragraph:paragraph=re.sub(r'<w:keepNext[^>]*/>','<w:keepNext/>',paragraph)
     else:paragraph=paragraph.replace('<w:pPr>','<w:pPr><w:keepNext/>',1)
    pieces.append(re.sub(r'\{\{([^{}]+)\}\}',lambda n:_xml_lines(block if n.group(1)==key else f.get(n.group(1),UNKNOWN)),paragraph))
   return ''.join(pieces)
  blocks=re.split(r'\n\s*\n',value.strip()) if key in ('취지','결어') else [value]
  return ''.join(re.sub(r'\{\{([^{}]+)\}\}',lambda n:_xml_lines(b if n.group(1)==key else f.get(n.group(1),UNKNOWN)),p) for b in blocks)
 xml=re.sub(para_re,rep,xml,flags=re.S)
 with zipfile.ZipFile(ANNEX_DOCX) as zi,zipfile.ZipFile(out_path,'w',zipfile.ZIP_DEFLATED) as zo:
  for item in zi.infolist():zo.writestr(item,xml.encode() if item.filename=='word/document.xml' else zi.read(item.filename))
 return Path(out_path)

def checked_output(path):
 path=Path(path).resolve()
 if path!=OUTDIR.resolve() and OUTDIR.resolve() not in path.parents:raise ValueError('산출 경로는 도구/산출 안이어야 합니다.')
 path.mkdir(parents=True,exist_ok=True);return path

def build(fields, output_dir=None, no_open=False, force_raster=False):
    from pypdf import PdfReader, PdfWriter
    from document_runtime import convert_docx, sha256
    from form_layout import create_overlay
    from validate_layout import validate
    from editable_document import make_full_docx,validate_full_docx

    f = normalize_fields(fields)
    out = checked_output(output_dir or OUTDIR)
    temp_root = checked_output(OUTDIR / '_tmp')
    name = re.sub(r'[\\/:*?"<>|]', '', str(f.get('파일명') or f['의견제출인_명칭'])).strip() or '초안'
    suffix = ''; n = 1
    while any((out/(prefix+name+suffix+extension)).exists() for prefix,extension in [('의견제출서_','.pdf'),('별지_상세의견서_','.docx'),('의견제출서_전체편집본_','.docx')]) or (out/('검증'+suffix)).exists():
        n += 1; suffix = '_v%03d' % n
    final = out / ('의견제출서_' + name + suffix + '.pdf')
    docx = out / ('별지_상세의견서_' + name + suffix + '.docx')
    full_docx=out/('의견제출서_전체편집본_'+name+suffix+'.docx')
    form = f.get('서식', {'type': 'standard11'})
    mode = form.get('type', 'unconfirmed')
    if mode not in ('standard11', 'custom', 'unconfirmed'):
        raise ValueError('서식.type 오류')
    profile=json.loads((HERE/'서식/layout_profile.json').read_text())
    if mode=='standard11' and sha256(FORM_PDF)!=profile['official_form_sha256']:
        raise ValueError('공식 서식 원본이 기준 파일과 다릅니다. 좌표를 다시 확인해야 합니다.')
    with tempfile.TemporaryDirectory(prefix='opinion_', dir=temp_root) as directory:
        tmp = Path(directory)
        (tmp / 'fields.json').write_text(json.dumps(f, ensure_ascii=False, indent=2), encoding='utf-8')
        # One authoring source: write the delivered DOCX, then convert those exact bytes.
        build_annex_docx(f, tmp / 'annex.docx')
        conversion = convert_docx(tmp / 'annex.docx', tmp / 'annex.pdf')
        cover = PdfWriter(); overlays = []
        if mode == 'unconfirmed':
            make_full_docx(tmp/'annex.docx',None,[],tmp/'generic_full.docx',f)
            convert_docx(tmp/'generic_full.docx',tmp/'generic_full.pdf')
            generic_pages=PdfReader(tmp/'generic_full.pdf').pages
            annex_count=len(PdfReader(tmp/'annex.pdf').pages)
            if len(generic_pages)<=annex_count:raise ValueError('일반 초안 표지가 생성되지 않았습니다.')
            for page in generic_pages[:-annex_count]:cover.add_page(page)
            composition = 'generic (제출 서식 확인 필요)'
        else:
            original = FORM_PDF if mode == 'standard11' else Path(form['pdf'])
            reader = PdfReader(original)
            if mode == 'custom':
                if not form.get('boxes'):
                    raise ValueError('기관별 서식은 pdf와 검토된 boxes가 필요합니다.')
                for box in form['boxes'].values():
                    if not isinstance(box, list) or len(box) != 7 or not isinstance(box[0], int) or not 0 <= box[0] < len(reader.pages):
                        raise ValueError('boxes: [쪽번호0부터,x,y,너비,높이,글자크기,정렬]')
            for index, page in enumerate(reader.pages):
                if page.rotation:
                    page.transfer_rotation_to_content()
                boxes = None if mode == 'standard11' else {k: v[1:] for k, v in form['boxes'].items() if v[0] == index}
                if boxes is None or boxes:
                    overlay = tmp / ('form_overlay_%d.pdf' % index)
                    placement = create_overlay(f, overlay, ANNEX_DOCX, tmp,
                                               boxes, (float(page.mediabox.width), float(page.mediabox.height)))
                    placement['page_index']=index
                    overlays.append((overlay, placement))
                    if mode == 'standard11' and force_raster:
                        from reportlab.pdfgen import canvas
                        raster = tmp / 'raster_form.pdf'
                        c = canvas.Canvas(str(raster), pagesize=(595, 842))
                        c.drawImage(str(FORM_PNG), 0, 0, width=595, height=842); c.save()
                        page = PdfReader(raster).pages[0]
                    page.merge_page(PdfReader(overlay).pages[0])
                cover.add_page(page)
            composition = 'raster' if force_raster and mode == 'standard11' else 'vector' if mode == 'standard11' else 'vector (기관 서식)'
        with (tmp / 'cover.pdf').open('wb') as stream:
            cover.write(stream)
        writer = PdfWriter()
        for page in cover.pages:
            writer.add_page(page)
        for page in PdfReader(tmp / 'annex.pdf').pages:
            writer.add_page(page)
        with (tmp / 'final.pdf').open('wb') as stream:
            writer.write(stream)
        report = validate(tmp / 'annex.docx', tmp / 'final.pdf', len(cover.pages), f,
                          tmp / 'layout.json', overlays=overlays, repeat=True, cover_pdf=tmp/'cover.pdf')
        if not report['passed']:
            failed = Path(tempfile.mkdtemp(prefix='layout_failed_', dir=temp_root))
            for filename in ['fields.json', 'annex.docx', 'annex.pdf', 'cover.pdf', 'final.pdf', 'layout.json']:
                shutil.copyfile(tmp / filename, failed / filename)
            raise ValueError('레이아웃 검증 실패: ' + '; '.join(report['errors'][:6]) + ' / 확인 파일: ' + str(failed))
        placements=[None]*len(cover.pages)
        for _,placement in overlays:
            placements[placement['page_index']]=placement|{'standard':mode=='standard11'}
        make_full_docx(tmp/'annex.docx',None if mode=='unconfirmed' else original,placements,tmp/'full.docx',f)
        editor_check=validate_full_docx(tmp/'full.docx',tmp/'annex.pdf',placements if mode!='unconfirmed' else [],tmp)
        if not editor_check['passed']:
            failed=Path(tempfile.mkdtemp(prefix='editor_failed_',dir=temp_root))
            for filename in ['fields.json','annex.docx','annex.pdf','full.docx','full_editor.pdf']:
                shutil.copyfile(tmp/filename,failed/filename)
            (failed/'editor_check.json').write_text(json.dumps(editor_check,ensure_ascii=False,indent=2),encoding='utf-8')
            raise ValueError('전체 편집본 검증 실패: '+'; '.join(editor_check['errors'])+' / 확인 파일: '+str(failed))
        qa = out / ('검증' + suffix); qa.mkdir(exist_ok=False)
        shutil.copyfile(tmp / 'final.pdf', final)
        shutil.copyfile(tmp / 'annex.docx', docx)
        shutil.copyfile(tmp/'full.docx',full_docx)
        (qa/'전체편집본_검증.json').write_text(json.dumps(editor_check,ensure_ascii=False,indent=2),encoding='utf-8')
        for src, dest in [('fields.json','입력값.json'), ('annex.pdf','별지_변환원본.pdf'), ('cover.pdf','표지_합성원본.pdf'), ('layout.json','레이아웃_검증.json')]:
            shutil.copyfile(tmp / src, qa / dest)
        overlay_records=[]
        for index, (path, placement) in enumerate(overlays):
            destination = qa / ('form_overlay_%d.pdf' % index)
            shutil.copyfile(path, destination)
            overlay_records.append({'path': str(destination), 'placement': placement})
        result = {'pdf':str(final), 'docx':str(docx), 'full_docx':str(full_docx), 'mode':composition, 'cover_pages':len(cover.pages),
                  'annex_pdf':str(qa/'별지_변환원본.pdf'), 'fields':str(qa/'입력값.json'),
                  'cover_pdf':str(qa/'표지_합성원본.pdf'),
                  'layout_report':str(qa/'레이아웃_검증.json'), 'overlays':overlay_records,
                  'layout_passed':True, 'conversion':conversion}
        (out/('레이아웃_검증대상'+suffix+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PDF:',final)
    print('별지 DOCX:',docx)
    print('표지와 별지 전체 편집 DOCX:',full_docx)
    print('서식 합성 방식:',composition,'/ 별지: DOCX 원본 변환')
    print('레이아웃 검증: 통과 / 독립 재변환·반복 변환·전체 별지 픽셀 일치')
    if not no_open:
        from document_runtime import open_document
        open_document(final)
    return result

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('fields',nargs='?');p.add_argument('--keys',action='store_true');p.add_argument('--no-open',action='store_true');p.add_argument('--raster',action='store_true');p.add_argument('--out-dir');a=p.parse_args(argv)
 if a.keys:
  print('\n'.join(FORM_KEYS+['의견제출인_명칭','처분청','건명','대상_표시','취지','소명 [{제목, 본문}, ...]','결어','소명자료_목록','별지_서명','파일명','서식 {type}']));return
 if not a.fields:p.error('fields.json 경로가 필요합니다.')
 with open(a.fields,encoding='utf-8') as stream:f=json.load(stream)
 build(f,a.out_dir,a.no_open,a.raster)
if __name__=='__main__':
 from document_runtime import bootstrap
 bootstrap()
 try:main()
 except (ValueError,RuntimeError,KeyError) as error:print('오류:',error,file=sys.stderr);sys.exit(1)
