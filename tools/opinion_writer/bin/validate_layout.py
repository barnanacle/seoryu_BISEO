"""Reject clipped forms and compare a fresh DOCX conversion with every merged annex page."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
import logging
from pathlib import Path
import re
import tempfile
import unicodedata
import zipfile
from xml.etree import ElementTree as ET

from document_runtime import HERE, bootstrap, convert_docx, render_pdf, sha256, temp_root

logging.getLogger('pdfminer').setLevel(logging.ERROR)


def compact(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', text)).replace('\u00ad','').replace('\u200b','')


def lines(page):
    groups=defaultdict(list)
    for char in page.chars:
        if char['text'].strip():groups[round(char['top'],1)].append(char)
    return [sorted(chars,key=lambda c:c['x0']) for _,chars in sorted(groups.items())]


def find_phrase(page,phrase,min_y=0,max_y=842,*,min_x=0,max_x=float("inf")):
    needle=compact(phrase)
    if not needle:return None
    chars=[c for row in lines(page) for c in row if min_y<=c['top']<=max_y and min_x<=c['x0'] and c['x1']<=max_x]
    text=''.join(c['text'] for c in chars)
    start=text.find(needle)
    if start<0:return None
    selected=chars[start:start+len(needle)]
    return {'x0':min(c['x0'] for c in selected),'top':min(c['top'] for c in selected),
            'x1':max(c['x1'] for c in selected),'bottom':max(c['bottom'] for c in selected),'chars':selected}


def compare_images(first,second):
    from PIL import Image,ImageChops
    import numpy as np
    a=Image.open(first).convert('RGB');b=Image.open(second).convert('RGB')
    if a.size!=b.size:return {'equal':False,'size_a':a.size,'size_b':b.size,'different_pixels':None}
    diff=np.asarray(ImageChops.difference(a,b))
    changed=int(np.count_nonzero(np.any(diff>0,axis=2)))
    return {'equal':changed==0,'different_pixels':changed,'total_pixels':a.width*a.height,'max_channel_difference':int(diff.max())}


def check_overlay(pdf_path,manifest):
    import pdfplumber
    errors=[];measurements=[]
    with pdfplumber.open(pdf_path) as pdf:
        page=pdf.pages[0]
        for entry in manifest['entries']:
            text=entry['text']
            if not compact(text):continue
            found=find_phrase(page,text,entry['top']-.7,entry['top']+.7,min_x=entry['left']-.7,max_x=entry['left']+entry['width']+.7)
            if found is None:
                errors.append('표지 텍스트 누락 또는 수직 위치 오류: '+entry['field']);continue
            dx=abs(found['x0']-entry['left']);dy=abs(found['top']-entry['top'])
            if dx>.7 or dy>.7:errors.append('표지 좌표 편차: '+entry['field'])
            x,y,w,h=entry['box']
            if found['x0']<x-.7 or found['x1']>x+w+.7 or found['top']<y-.7 or found['bottom']>y+h+.7:
                errors.append('표지 칸 넘침: '+entry['field'])
            if entry['field'] in {'의견','기타'} and entry.get('valign')=='middle':
                cx=(found['x0']+found['x1'])/2;cy=(found['top']+found['bottom'])/2
                if abs(cx-(x+w/2))>.7 or abs(cy-(y+h/2))>.7:errors.append('별지로 작성 중앙 배치 오류: '+entry['field'])
            measurements.append({'field':entry['field'],'left':round(found['x0'],3),'top':round(found['top'],3),'width':round(found['x1']-found['x0'],3),'height':round(found['bottom']-found['top'],3)})
    return errors,measurements


def expected_paragraphs(fields):
    values=[fields.get(k,'') for k in ['별지_제목','의견제출인_명칭','별지_주소','처분청','건명','대상_표시','취지','결어','소명자료_목록','별지_서명']]
    for s in fields.get('소명',[]):values += [s['제목'],s['본문']]
    return [compact(p) for value in values for p in re.split(r'\n\s*\n',str(value)) if compact(p)]


def check_docx_contract(docx_path, fields, spec):
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    attr=lambda name:'{'+ns['w']+'}'+name
    errors=[]
    with zipfile.ZipFile(docx_path) as source:
        root=ET.fromstring(source.read('word/document.xml'))
        font_table=ET.fromstring(source.read('word/fontTable.xml'))
    embedded={n.get(attr('name')) for n in font_table if n.find('w:embedRegular',ns) is not None}
    families=set(json.loads((HERE/'서식/layout_profile.json').read_text())['fonts'].values())
    if not families<=embedded:errors.append('DOCX에 기준 글꼴 임베딩이 없습니다.')
    table=root.find('.//w:tbl/w:tblGrid',ns)
    widths=[int(n.get(attr('w'))) for n in table] if table is not None else []
    if widths[:2]!=[round(spec['label_width_pt']*20),round(spec['label_gap_pt']*20)]:errors.append('DOCX 메타정보의 라벨 폭·간격이 기준과 다릅니다.')
    table_width=root.find('.//w:tbl/w:tblPr/w:tblW',ns)
    if table_width is None or table_width.get(attr('type'))!='dxa' or table_width.get(attr('w'))!=str(sum(widths)):
        errors.append('DOCX 메타정보 표의 전체 폭이 명시되지 않았습니다.')
    for cell in root.findall('.//w:tbl/w:tr/w:tc',ns):
        for edge in ['top','left','bottom','right']:
            margin=cell.find('w:tcPr/w:tcMar/w:'+edge,ns)
            if margin is None or margin.get(attr('w'))!='0':errors.append('DOCX 메타정보 셀 여백이 명시되지 않았습니다.');break
    body=[]
    for value in [fields.get('취지',''),fields.get('결어','')]+[s['본문'] for s in fields.get('소명',[])]:
        body += [compact(x) for x in re.split(r'\n\s*\n',value) if compact(x)]
    paragraphs=root.findall('./w:body/w:p',ns)
    used=set()
    for expected in body:
        matches=[(i,p) for i,p in enumerate(paragraphs) if i not in used and compact(''.join(p.itertext()))==expected]
        preferred=[(i,p) for i,p in matches if p.find('w:pPr/w:ind',ns) is not None and p.find('w:pPr/w:ind',ns).get(attr('firstLine'))==str(round(spec['first_indent_pt']*20))]
        match=(preferred or matches or [(None,None)])[0]
        index,p=match
        if p is None:errors.append('DOCX 본문 문단 누락: '+expected[:35]);continue
        used.add(index)
        indent=p.find('w:pPr/w:ind',ns);spacing=p.find('w:pPr/w:spacing',ns)
        if indent is None or indent.get(attr('firstLine'))!=str(round(spec['first_indent_pt']*20)):
            errors.append('DOCX 본문 첫 줄 들여쓰기 오류');break
        if spacing is None or spacing.get(attr('lineRule'))!='exact' or spacing.get(attr('line'))!=str(round(spec['line_pt']*20)):
            errors.append('DOCX 본문 고정 행간 오류');break
        for run in p.findall('w:r',ns):
            track=run.find('w:rPr/w:spacing',ns);size=run.find('w:rPr/w:sz',ns)
            if track is None or track.get(attr('val'))!=str(round(spec['body_tracking_pt']*20)) or size is None or size.get(attr('val'))!=str(round(spec['body_size_pt']*2)):
                errors.append('DOCX 본문 자간·크기 오류');break
    return errors


def validate(docx_path,merged_pdf,cover_pages,fields,output_report,overlays=(),repeat=True,cover_pdf=None):
    import pdfplumber
    from pypdf import PdfReader
    profile=json.loads((HERE/'서식/layout_profile.json').read_text())
    spec=profile['annex'];tolerance=spec['coordinate_tolerance_pt']
    result={'profile':profile['version'],'reference_sha256':profile['reference_sha256'],'docx_sha256':sha256(docx_path),'pdf_sha256':sha256(merged_pdf),
            'cover_pages':cover_pages,'errors':[],'warnings':[],'form':[],'meta':{},'page_comparison':[]}
    errors=result['errors']
    errors.extend(check_docx_contract(docx_path,fields,spec))
    for overlay,manifest in overlays:
        problems,positions=check_overlay(overlay,manifest);errors.extend(problems);result['form'].extend(positions)
    with tempfile.TemporaryDirectory(prefix='layout_check_',dir=temp_root()) as directory:
        tmp=Path(directory);fresh=tmp/'fresh.pdf'
        result['conversion']=convert_docx(Path(docx_path),fresh)
        with pdfplumber.open(fresh) as pdf:
            # Paragraphs can cross a page boundary; page numbers are not body content.
            text='\n'.join(p.crop((0,0,p.width,780)).extract_text() or '' for p in pdf.pages)
            normalized=compact(text)
            for paragraph,count in Counter(expected_paragraphs(fields)).items():
                if normalized.count(paragraph)<count:errors.append('별지 내용 누락: '+paragraph[:55])
            if '�' in text or '(cid:' in text:errors.append('별지에 해석되지 않는 글자가 있습니다.')
            if '{{' in text:errors.append('별지에 치환되지 않은 템플릿 키가 있습니다.')
            page=pdf.pages[0]
            label=find_phrase(page,'의견제출인',max_y=600)
            authority_label=find_phrase(page,'처분청',max_y=650)
            company=find_phrase(page,compact(fields.get('의견제출인_명칭',''))[:12],min_y=label['top']-.5 if label else 0,max_y=600)
            address=find_phrase(page,compact(fields.get('별지_주소',''))[:12],min_y=company['bottom'] if company else 0,max_y=650)
            authority=find_phrase(page,compact(fields.get('처분청',''))[:12],min_y=authority_label['top']-.5 if authority_label else 0,max_y=650)
            tag=find_phrase(page,'[별지]',max_y=160)
            title=find_phrase(page,fields.get('별지_제목',''),max_y=210)
            title_lines=len(set(round(c['top'],1) for c in title['chars'])) if title else 1
            for name,found,expected_y in [('별지 표지',tag,spec['tag_visible_top_pt']),('별지 제목',title,spec['title_visible_top_pt']),('메타정보 시작',label,spec['meta_visible_top_pt']+(title_lines-1)*spec['title_line_pt'])]:
                if found is None or abs(found['top']-expected_y)>tolerance:errors.append('별지 기준 수직 위치 오류: '+name)
            for name,found,expected_x in [('의견제출인_라벨',label,spec['label_x_pt']),('처분청_라벨',authority_label,spec['label_x_pt']),('회사명',company,spec['value_x_pt']),('주소',address,spec['value_x_pt']),('처분청명',authority,spec['value_x_pt'])]:
                if found is None:
                    errors.append('별지 메타정보 탐색 실패: '+name);continue
                result['meta'][name]={k:round(found[k],3) for k in ['x0','top','x1','bottom']}
                if abs(found['x0']-expected_x)>tolerance:errors.append('별지 메타정보 세로 정렬 오류: '+name)
            if label and company and abs(label['top']-company['top'])>.7:errors.append('의견제출인 라벨과 회사명의 기준선 불일치')
            if authority_label and authority:
                if abs(authority_label['top']-authority['top'])>.7:errors.append('처분청 라벨과 명칭의 기준선 불일치')
                xs=[round(c['x0'],2) for c in authority_label['chars']]
                if len(xs)!=3 or any(abs(x-(spec['label_x_pt']+24*i))>tolerance for i,x in enumerate(xs)):
                    errors.append('처분청 글자 간격 오류')
            heading_names=['의 견 제 출 의  취 지','사실관계 및 의견의 근거','결    어']+[s['제목'] for s in fields.get('소명',[])]
            for page_number,p in enumerate(pdf.pages,1):
                body_chars=[c for c in p.chars if c['text'].strip() and c['top']<780]
                if len(body_chars)<8:errors.append(f'별지 {page_number}쪽이 비어 있거나 꼬리말만 있습니다.')
                for c in body_chars:
                    if c['x0']<spec['left_pt']-tolerance or c['x1']>595-spec['right_pt']+tolerance or c['top']<spec['top_pt']-tolerance or c['bottom']>842-spec['bottom_pt']+tolerance:
                        errors.append(f'별지 {page_number}쪽 본문 여백 침범');break
                for name in heading_names:
                    found=find_phrase(p,name,max_y=770)
                    if found and not any(c['top']>found['bottom']+.5 for c in body_chars):
                        errors.append(f'별지 {page_number}쪽 제목만 남음: {name}')
            result['annex_pages']=len(pdf.pages)
            last=compact(pdf.pages[-1].crop((0,0,pdf.pages[-1].width,780)).extract_text() or '')
            signature=compact('위 의견제출인'+fields.get('별지_서명',''))
            leftover=last.replace(compact(fields.get('별지_작성일','')),'').replace(signature,'')
            if len(pdf.pages)>1 and not leftover:errors.append('별지 마지막 쪽에 날짜·서명만 남았습니다.')
        merged_reader=PdfReader(merged_pdf)
        if len(merged_reader.pages)!=cover_pages+result['annex_pages']:
            errors.append('합본의 별지 쪽수와 DOCX 재변환 쪽수 불일치')
        else:
            if cover_pdf:
                actual_cover=render_pdf(Path(merged_pdf),tmp/'merged_cover',dpi=120,first=1,last=cover_pages)
                expected_cover=render_pdf(Path(cover_pdf),tmp/'expected_cover',dpi=120)
                result['cover_comparison']=[compare_images(a,b) for a,b in zip(actual_cover,expected_cover)]
                if len(actual_cover)!=len(expected_cover) or any(not x['equal'] for x in result['cover_comparison']):
                    errors.append('합본 표지가 검증한 입력값 레이어 합성본과 다릅니다.')
            actual=render_pdf(Path(merged_pdf),tmp/'merged',dpi=120,first=cover_pages+1)
            expected=render_pdf(fresh,tmp/'fresh_images',dpi=120)
            for i,(a,b) in enumerate(zip(actual,expected),1):
                comparison=compare_images(a,b);comparison['annex_page']=i
                result['page_comparison'].append(comparison)
                if not comparison['equal']:errors.append(f'DOCX 재변환과 합본 별지 {i}쪽의 픽셀 불일치')
            if repeat:
                second=tmp/'repeat.pdf';convert_docx(Path(docx_path),second)
                again=render_pdf(second,tmp/'repeat_images',dpi=120)
                result['repeat_comparison']=[compare_images(a,b) for a,b in zip(expected,again)]
                if len(again)!=len(expected) or any(not x['equal'] for x in result['repeat_comparison']):
                    errors.append('같은 DOCX를 반복 변환했을 때 배치가 달라졌습니다.')
    result['passed']=not errors
    output_report=Path(output_report)
    output_report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest');p.add_argument('--no-repeat',action='store_true');a=p.parse_args()
    path=Path(a.manifest).resolve();manifest=json.loads(path.read_text())
    fields=json.loads(Path(manifest['fields']).read_text())
    from build_pdf import normalize_fields
    overlays=[(Path(x['path']),x['placement']) for x in manifest.get('overlays',[])]
    report=validate(manifest['docx'],manifest['pdf'],manifest['cover_pages'],normalize_fields(fields),path.parent/'레이아웃_재검증.json',overlays=overlays,repeat=not a.no_repeat,cover_pdf=manifest.get('cover_pdf'))
    print(json.dumps({'passed':report['passed'],'annex_pages':report.get('annex_pages'),'errors':report['errors']},ensure_ascii=False,indent=2))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':
    bootstrap();main()
