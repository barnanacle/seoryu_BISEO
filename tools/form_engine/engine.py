#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render reviewed form packs without pack-specific field names or paths."""
import json,logging,re,shutil,tempfile
from pathlib import Path
from .annex import build_annex_docx
from .layout import create_overlay
from .pack import resolve_asset
from .transforms import normalize_fields
logging.getLogger('pypdf').setLevel(logging.ERROR)

def checked_output(path, output_root):
    path = Path(path).resolve()
    root = Path(output_root).resolve()
    if path != root and root not in path.parents:
        raise ValueError("산출 경로는 도구/산출 안이어야 합니다.")
    path.mkdir(parents=True, exist_ok=True)
    return path

def build(fields, pack, output_root, output_dir=None, no_open=False, force_raster=False,
          asset_overrides=None):
    from pypdf import PdfReader, PdfWriter
    from document_runtime import convert_docx, sha256
    from validate_layout import validate
    from editable_document import make_full_docx,validate_full_docx

    f = normalize_fields(fields, pack)
    out = checked_output(output_dir or output_root, output_root)
    temp_root = checked_output(Path(output_root) / '_tmp', output_root)
    output = pack["output"]
    name = re.sub(r'[\\/:*?"<>|]', '', str(f.get('파일명') or f.get(output["fallback_name_field"], "초안"))).strip() or '초안'
    suffix = ''; n = 1
    names = [(output["pdf_prefix"], ".pdf"), (output["annex_docx_prefix"], ".docx"),
             (output["full_docx_prefix"], ".docx")]
    while any((out / (prefix + name + suffix + extension)).exists() for prefix, extension in names) or (out / (output["verification_prefix"] + suffix)).exists():
        n += 1; suffix = '_v%03d' % n
    final = out / (output["pdf_prefix"] + name + suffix + ".pdf")
    docx = out / (output["annex_docx_prefix"] + name + suffix + ".docx")
    full_docx = out / (output["full_docx_prefix"] + name + suffix + ".docx")
    form = f.get('서식', {'type': pack["form_mode"]})
    mode = form.get('type', 'unconfirmed')
    if mode not in (pack["form_mode"], 'custom', 'unconfirmed'):
        raise ValueError('서식.type 오류')
    overrides = asset_overrides or {}
    form_pdf = Path(overrides.get("form_pdf") or resolve_asset(pack, pack["files"]["form_pdf"]))
    form_png = Path(overrides.get("form_png") or resolve_asset(pack, pack["files"]["form_png"]))
    annex_docx = Path(overrides.get("annex_docx") or resolve_asset(pack, pack["files"]["annex_docx"]))
    if mode == pack["form_mode"] and sha256(form_pdf) != pack["form_sha256"]:
        raise ValueError('공식 서식 원본이 기준 파일과 다릅니다. 좌표를 다시 확인해야 합니다.')
    with tempfile.TemporaryDirectory(prefix='form_pack_', dir=temp_root) as directory:
        tmp = Path(directory)
        (tmp / 'fields.json').write_text(json.dumps(f, ensure_ascii=False, indent=2), encoding='utf-8')
        # One authoring source: write the delivered DOCX, then convert those exact bytes.
        build_annex_docx(f, tmp / 'annex.docx', pack)
        conversion = convert_docx(tmp / 'annex.docx', tmp / 'annex.pdf')
        cover = PdfWriter(); overlays = []
        if mode == 'unconfirmed':
            make_full_docx(tmp/'annex.docx',None,[],tmp/'generic_full.docx',f,
                           profile=pack["profile"],masks=pack.get("masks",[]),
                           title=output["full_docx_title"],
                           field_names=list(pack["pages"][0]["fields"]),
                           unconfirmed_title=output["unconfirmed_title"])
            convert_docx(tmp/'generic_full.docx',tmp/'generic_full.pdf')
            generic_pages=PdfReader(tmp/'generic_full.pdf').pages
            annex_count=len(PdfReader(tmp/'annex.pdf').pages)
            if len(generic_pages)<=annex_count:raise ValueError('일반 초안 표지가 생성되지 않았습니다.')
            for page in generic_pages[:-annex_count]:cover.add_page(page)
            composition = 'generic (제출 서식 확인 필요)'
        else:
            original = form_pdf if mode == pack["form_mode"] else Path(form['pdf'])
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
                boxes = None if mode == pack["form_mode"] else {k: v[1:] for k, v in form['boxes'].items() if v[0] == index}
                if boxes is None or boxes:
                    overlay = tmp / ('form_overlay_%d.pdf' % index)
                    placement = create_overlay(f, overlay, annex_docx, tmp, pack,
                                               boxes, (float(page.mediabox.width), float(page.mediabox.height)),
                                               page_index=index)
                    placement['page_index']=index
                    overlays.append((overlay, placement))
                    if mode == pack["form_mode"] and force_raster:
                        from reportlab.pdfgen import canvas
                        raster = tmp / 'raster_form.pdf'
                        page_width, page_height = float(page.mediabox.width), float(page.mediabox.height)
                        c = canvas.Canvas(str(raster), pagesize=(page_width, page_height))
                        c.drawImage(str(form_png), 0, 0, width=page_width, height=page_height); c.save()
                        page = PdfReader(raster).pages[0]
                    page.merge_page(PdfReader(overlay).pages[0])
                cover.add_page(page)
            composition = 'raster' if force_raster and mode == pack["form_mode"] else 'vector' if mode == pack["form_mode"] else 'vector (기관 서식)'
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
                          tmp / 'layout.json', overlays=overlays, repeat=True,
                          cover_pdf=tmp/'cover.pdf',profile=pack["profile"])
        if not report['passed']:
            failed = Path(tempfile.mkdtemp(prefix='layout_failed_', dir=temp_root))
            for filename in ['fields.json', 'annex.docx', 'annex.pdf', 'cover.pdf', 'final.pdf', 'layout.json']:
                shutil.copyfile(tmp / filename, failed / filename)
            raise ValueError('레이아웃 검증 실패: ' + '; '.join(report['errors'][:6]) + ' / 확인 파일: ' + str(failed))
        placements=[None]*len(cover.pages)
        for _,placement in overlays:
            placements[placement['page_index']]=placement|{'standard':mode==pack["form_mode"]}
        make_full_docx(tmp/'annex.docx',None if mode=='unconfirmed' else original,placements,
                       tmp/'full.docx',f,profile=pack["profile"],masks=pack.get("masks",[]),
                       title=output["full_docx_title"],field_names=list(pack["pages"][0]["fields"]),
                       unconfirmed_title=output["unconfirmed_title"])
        editor_check=validate_full_docx(tmp/'full.docx',tmp/'annex.pdf',placements if mode!='unconfirmed' else [],tmp)
        if not editor_check['passed']:
            failed=Path(tempfile.mkdtemp(prefix='editor_failed_',dir=temp_root))
            for filename in ['fields.json','annex.docx','annex.pdf','full.docx','full_editor.pdf']:
                shutil.copyfile(tmp/filename,failed/filename)
            (failed/'editor_check.json').write_text(json.dumps(editor_check,ensure_ascii=False,indent=2),encoding='utf-8')
            raise ValueError('전체 편집본 검증 실패: '+'; '.join(editor_check['errors'])+' / 확인 파일: '+str(failed))
        qa = out / (output["verification_prefix"] + suffix); qa.mkdir(exist_ok=False)
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
