"""Reference-aligned text placement on the untouched official form PDF."""
from __future__ import annotations
import copy
import json
import re
from pathlib import Path
from document_runtime import HERE, extract_fonts

UNKNOWN='【확인 필요】'
PROFILE=HERE/'서식/layout_profile.json'


def font_registry(template: Path, directory: Path):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    paths=extract_fonts(template,directory)
    families=json.loads(PROFILE.read_text())['fonts']
    for alias,family in [('OpinionForm',families['form']),('OpinionBody',families['body'])]:
        pdfmetrics.registerFont(TTFont(alias,str(paths[family])))
    return paths


def wrap_text(text, font, size, width):
    """Preserve explicit newlines and fit every character; never clip a field."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    lines=[]
    for paragraph in str(text).replace('\r','').split('\n'):
        if not paragraph:
            lines.append('');continue
        current=''
        for char in paragraph:
            if stringWidth(current+char,font,size)>width and current:
                # Prefer a word boundary when it does not create a very short line.
                boundary=current.rfind(' ')
                if boundary>=len(current)*.6:
                    lines.append(current[:boundary].rstrip())
                    current=current[boundary+1:]+char
                else:
                    lines.append(current.rstrip());current=char.lstrip()
            else:current+=char
        lines.append(current.rstrip())
    return lines


def fit_text(text,spec,font='OpinionForm'):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    x,y,width,height=spec['box'];size=float(spec['size']);minimum=float(spec.get('min_size',size))
    while size>=minimum-.001:
        lines=wrap_text(text,font,size,width)
        line_height=max(size,spec.get('line',size*1.35)*size/spec['size'])
        required=size+(len(lines)-1)*line_height
        if required<=height+.01 and all(stringWidth(s,font,size)<=width+.01 for s in lines):
            return lines,round(size,3),line_height
        size=round(size-.1,4)
        if minimum<size<minimum+.1:size=minimum
    raise ValueError('표지 칸에 내용이 들어가지 않습니다. 내용을 임의로 자르지 않았습니다: '+str(text)[:70])


def normalized_address(text):
    return re.sub(r'\s*\n\s*(?=\()', '', str(text).strip()).replace('\n',' ')


def form_values(fields):
    vals={k:str(fields.get(k) or UNKNOWN) for k in json.loads(PROFILE.read_text())['form']}
    vals['당사자_주소']=normalized_address(vals['당사자_주소'])
    signature=fields.get('대표자','').strip()
    company=str(fields.get('의견제출인_명칭','')).strip()
    full=vals['의견제출인_서명'].strip()
    if not signature and company and full.startswith(company+' 대표 '):
        signature=full[len(company+' 대표 '):].strip()
    if signature and len(signature)<=5 and re.fullmatch(r'[가-힣]+',signature):
        vals['의견제출인_서명']='대표   '+'   '.join(signature)
    else:signature=''
    m=re.fullmatch(r'\s*(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D*',vals['작성일'])
    if m:
        import datetime
        year,month,day=map(int,m.groups());datetime.date(year,month,day)
        vals['작성일']=f'{year}년    {month}월    {day}일'
    else:vals['작성일']=UNKNOWN
    return vals,bool(signature)


def create_overlay(fields,pdf_path,template,work_dir,custom_boxes=None,page_size=(595,842)):
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    font_registry(template,Path(work_dir)/'form_fonts')
    values,representative=form_values(fields)
    specs=copy.deepcopy(json.loads(PROFILE.read_text())['form'])
    if custom_boxes is not None:
        specs={k:{'box':list(v[:4]),'size':v[4],'min_size':v[4],'line':v[4]*1.3,'align':v[5]} for k,v in custom_boxes.items()}
        values={k:str(v) for k,v in fields.items() if isinstance(v,str)}
    elif representative:
        specs['의견제출인_서명']={'box':[373.8,629.64,85.8,12],'size':9,'min_size':9,'line':12}
    width,height=page_size
    c=canvas.Canvas(str(pdf_path),pagesize=page_size,invariant=1)
    c.setTitle('의견제출서 입력값 레이어')
    if custom_boxes is None:
        # Relocate only date placeholders and the isolated recipient suffix in the copy.
        # No official labels, legal text or ruling lines are removed from the source file.
        c.setFillColorRGB(1,1,1)
        for x,y,w,h in [(398,604,137,19),(201,659,25,19)]:c.rect(x,height-y-h,w,h,fill=1,stroke=0)
    c.setFillColorRGB(0,0,0)
    entries=[]
    for key,spec in specs.items():
        value=values.get(key,UNKNOWN)
        if key=='수신' and custom_boxes is None:value=value+'   귀하'
        x,y,w,h=spec['box']
        if x<0 or y<0 or x+w>width+.1 or y+h>height+.1:raise ValueError('서식 좌표 범위 오류: '+key)
        if spec.get('align','left') not in {'left','center','right'}:raise ValueError('서식 정렬 오류: '+key)
        lines,size,leading=fit_text(value,spec)
        block_height=size+(len(lines)-1)*leading
        top=y+(h-block_height)/2 if spec.get('valign')=='middle' else y
        for line_index,text in enumerate(lines):
            text_width=pdfmetrics.stringWidth(text,'OpinionForm',size)
            left=x+(w-text_width)/2 if spec.get('align')=='center' else x+w-text_width if spec.get('align')=='right' else x
            desired_top=top+line_index*leading
            descent=pdfmetrics.getDescent('OpinionForm')/1000*size
            baseline=height-desired_top-size-descent
            c.setFont('OpinionForm',size);c.drawString(left,baseline,text)
            entries.append({'field':key,'text':text,'left':left,'top':desired_top,'width':text_width,'height':size,'box':spec['box'],'align':spec.get('align','left'),'valign':spec.get('valign','top')})
    c.save()
    return {'page_size':list(page_size),'entries':entries,'representative_signature':representative,'profile':json.loads((HERE/'서식/layout_profile.json').read_text())['version']}
