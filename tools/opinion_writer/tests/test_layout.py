import copy,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bin'))
from document_runtime import HERE,temp_root,obfuscate,extract_fonts
from build_pdf import build_annex_docx,normalize_fields
from form_layout import font_registry,fit_text,create_overlay
from validate_layout import check_docx_contract,check_overlay,compare_images

class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=temp_root(),prefix='test_layout_')
        self.root=Path(self.tmp.name)
        self.template=HERE/'서식/별지_상세의견서_템플릿.docx'
        self.spec=json.loads((HERE/'서식/layout_profile.json').read_text())['annex']
        self.fields=normalize_fields({'의견제출인_명칭':'가상 신청인','의견제출인_주소':'가상 주소\n(추가 주소)','취지':'검토용 첫 문단','결어':'검토용 결어','소명':[{'제목':'확인 사항','본문':'사실관계는 확인 필요입니다.'}]})
    def tearDown(self):self.tmp.cleanup()
    def test_font_obfuscation_known_key(self):
        guid='001B70DC-AA60-4AD5-90EC-18A0948E1EAE'
        key=bytes.fromhex('AE1E8E94A018EC90D54A60AADC701B00')
        self.assertEqual(obfuscate(bytes(32),guid),key*2)
    def test_embedded_full_fonts_are_extractable(self):
        fonts=extract_fonts(self.template,self.root/'fonts')
        self.assertEqual(set(fonts),set(json.loads((HERE/'서식/layout_profile.json').read_text())['fonts'].values()))
        self.assertTrue(all(p.stat().st_size>100000 for p in fonts.values()))
    def test_metadata_and_body_contract(self):
        path=self.root/'annex.docx';build_annex_docx(self.fields,path)
        self.assertEqual(check_docx_contract(path,self.fields,self.spec),[])
    def test_wrong_tracking_is_rejected(self):
        path=self.root/'annex.docx';build_annex_docx(self.fields,path)
        with zipfile.ZipFile(path) as z:parts={n:z.read(n) for n in z.namelist()}
        xml=parts['word/document.xml'].decode().replace('w:spacing w:val="24"','w:spacing w:val="0"')
        parts['word/document.xml']=xml.encode()
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            for n,b in parts.items():z.writestr(n,b)
        self.assertTrue(any('자간' in x for x in check_docx_contract(path,self.fields,self.spec)))
    def test_auto_table_width_is_rejected(self):
        from lxml import etree
        path=self.root/'annex.docx';build_annex_docx(self.fields,path)
        with zipfile.ZipFile(path) as z:parts={n:z.read(n) for n in z.namelist()}
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        root=etree.fromstring(parts['word/document.xml']);width=root.find('.//w:tbl/w:tblPr/w:tblW',ns)
        width.set('{'+ns['w']+'}type','auto');width.set('{'+ns['w']+'}w','0')
        parts['word/document.xml']=etree.tostring(root)
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            for n,b in parts.items():z.writestr(n,b)
        self.assertTrue(any('전체 폭' in x for x in check_docx_contract(path,self.fields,self.spec)))
    def test_overlay_centers_and_indents_are_measured(self):
        path=self.root/'overlay.pdf'
        fields=copy.deepcopy(self.fields);fields['의견']='별지로 작성';fields['기타']='별지로 작성'
        placement=create_overlay(fields,path,self.template,self.root)
        problems,positions=check_overlay(path,placement)
        self.assertEqual(problems,[])
        name=next(x for x in positions if x['field']=='의견제출인_성명')
        self.assertAlmostEqual(name['left'],148.32,places=2)
    def test_identical_unknowns_are_matched_in_their_own_cells(self):
        path=self.root/'overlay.pdf'
        fields=normalize_fields({})
        placement=create_overlay(fields,path,self.template,self.root)
        errors,positions=check_overlay(path,placement)
        self.assertEqual(errors,[])
        address=next(x for x in positions if x['field']=='의견제출인_주소')
        phone=next(x for x in positions if x['field']=='의견제출인_전화번호')
        self.assertNotEqual(address['left'],phone['left'])
    def test_identical_text_in_another_cell_cannot_hide_missing_text(self):
        path=self.root/'only_address.pdf'
        placement=create_overlay({'의견제출인_주소':'【확인 필요】'},path,self.template,self.root,
            {'의견제출인_주소':[100,150,200,30,12,'left']})
        missing=copy.deepcopy(placement['entries'][0]);missing.update({'field':'의견제출인_전화번호','left':400,'box':[400,150,120,30]})
        placement['entries'].append(missing)
        errors,_=check_overlay(path,placement)
        self.assertTrue(any('텍스트 누락' in x and '전화번호' in x for x in errors))
    def test_form_overflow_raises_instead_of_clipping(self):
        font_registry(self.template,self.root/'fonts')
        spec={'box':[0,0,40,12],'size':10,'min_size':9,'line':14}
        with self.assertRaisesRegex(ValueError,'임의로 자르지'):
            fit_text('지나치게 긴 내용을 '*100,spec)
    def test_pixel_comparison_detects_a_one_pixel_change(self):
        from PIL import Image
        a=self.root/'a.png';b=self.root/'b.png'
        im=Image.new('RGB',(10,10),'white');im.save(a)
        im.putpixel((3,4),(0,0,0));im.save(b)
        result=compare_images(a,b);self.assertFalse(result['equal']);self.assertEqual(result['different_pixels'],1)
    def test_address_breaks_are_normalized_without_changing_words(self):
        self.assertEqual(self.fields['별지_주소'],'가상 주소(추가 주소)')
    def test_changed_official_form_is_not_silently_used(self):
        from unittest.mock import patch
        from build_pdf import build
        different=self.root/'different.pdf';different.write_bytes(b'not the approved form')
        with patch('build_pdf.FORM_PDF',different):
            with self.assertRaisesRegex(ValueError,'공식 서식 원본'):
                build(self.fields,self.root/'rejected',no_open=True)

if __name__=='__main__':unittest.main()
