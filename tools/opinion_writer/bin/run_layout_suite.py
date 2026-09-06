"""Render representative input shapes and exercise the layout validator's failure gates."""
from document_runtime import bootstrap
if __name__=='__main__':
    bootstrap()
    import argparse,copy,json,tempfile
    from pathlib import Path
    from pypdf import PdfReader,PdfWriter
    from build_pdf import HERE,build,normalize_fields,checked_output
    from document_runtime import temp_root
    from validate_layout import validate

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source')
    parser.add_argument('--cases',nargs='+')
    args=parser.parse_args()
    root=Path(tempfile.mkdtemp(prefix='layout_suite_',dir=temp_root()))
    original=json.loads(Path(args.source).read_text()) if args.source else None
    base={'의견제출인_성명':'가상 신청인','의견제출인_명칭':'가상 신청인','의견제출인_주소':'서울특별시 가상구 가상로 10',
          '의견제출인_전화번호':'02-0000-0000','당사자_명칭':'가상 신청인','당사자_주소':'서울특별시 가상구 가상로 10',
          '당사자_전화번호':'02-0000-0000','의견제출인_서명':'가상 신청인','처분청':'가상처분청','수신':'가상처분청',
          '작성일':'【확인 필요】','처분의_제목':'가상 처분사전통지 레이아웃 검증','건명':'범용 출력기 레이아웃 검증용 가상 사건',
          '대상_표시':'대상은 확인 필요','의견':'별지로 작성','기타':'별지로 작성',
          '취지':'이 문서는 출력 기능을 확인하기 위한 가상 사례입니다. 실제 행정처분의 법률 판단을 포함하지 않습니다.',
          '결어':'사실과 법적 근거는 확인 필요입니다. 레이아웃 검증용 문서입니다.',
          '소명자료_목록':'소명자료 1. 증빙 원본 【확인 필요】',
          '소명':[{'제목':'확인할 사항','본문':'이 문단은 날짜와 문서 형식의 안정성을 확인하기 위한 가상 문장입니다.'}]}
    if original is None:original=copy.deepcopy(base)
    long=copy.deepcopy(base)
    long['의견제출인_성명']=long['의견제출인_명칭']=long['당사자_명칭']='사단법인 전국 공공행정 및 지역사회 발전을 위한 공동협력 지원센터'
    address='서울특별시 영등포구 국제금융로 100, 미래공공행정센터 제2관 15층 1501호'
    long['의견제출인_주소']=long['당사자_주소']=address
    long['의견제출인_서명']='가상 대표자'
    six=copy.deepcopy(base)
    six['소명']=[{'제목':f'{i}번째 검토 항목','본문':('문단이 여러 쪽에 이어져도 원문이 누락되지 않고 줄바꿈과 자간이 유지되어야 합니다. '*7)+'\n\n다음 문단 역시 같은 DOCX에서 변환합니다.'} for i in range(1,7)]
    empty=copy.deepcopy(base);empty['소명']=[]
    custom=copy.deepcopy(base)
    fixture=root/'custom_form.pdf';w=PdfWriter();w.add_blank_page(width=612,height=792);w.add_blank_page(width=595,height=842)
    with fixture.open('wb') as stream:w.write(stream)
    custom['서식']={'type':'custom','pdf':str(fixture),'boxes':{'의견제출인_성명':[0,100,150,350,30,12,'left'],'작성일':[1,100,150,350,30,12,'left']}}
    unconfirmed=copy.deepcopy(base);unconfirmed['서식']={'type':'unconfirmed'}
    raster=copy.deepcopy(base);raster['_test_raster']=True
    cases=[('original',original),('individual_unknown_date',base),('long_name_address',long),('six_sections',six),('zero_sections',empty),('custom_two_pages',custom),('unconfirmed_form',unconfirmed),('raster_form',raster)]
    if args.cases:
        unknown=set(args.cases)-{name for name,_ in cases}
        if unknown:parser.error('알 수 없는 검사: '+', '.join(unknown))
        cases=[item for item in cases if item[0] in args.cases]
    results=[]
    for label,fields in cases:
        try:
            fields['파일명']='검증_'+label
            result=build(fields,checked_output(root/label),no_open=True,force_raster=fields.pop('_test_raster',False))
            results.append({'case':label,'passed':True,'result':result})
        except Exception as error:
            results.append({'case':label,'passed':False,'error':str(error)})
        print(label,results[-1]['passed'],flush=True)
    good=next((x['result'] for x in results if x['case']=='individual_unknown_date' and x['passed']),None)
    if good:
        fields=normalize_fields(json.loads(Path(good['fields']).read_text()))
        reader=PdfReader(good['pdf']);writer=PdfWriter()
        for page in reader.pages:writer.add_page(page)
        writer.add_blank_page(width=595,height=842)
        bad=root/'extra_page.pdf'
        with bad.open('wb') as stream:writer.write(stream)
        report=validate(good['docx'],bad,good['cover_pages'],fields,root/'negative_page_count.json',repeat=False)
        results.append({'case':'negative_extra_page','passed':not report['passed'] and any('쪽수' in x for x in report['errors'])})
    (root/'suite_result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SUITE_REPORT',root/'suite_result.json',flush=True)
    raise SystemExit(0 if all(x['passed'] for x in results) else 1)
