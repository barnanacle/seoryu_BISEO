import copy,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bin'))
import case_workflow as cw
import build_pdf as pdf

class WorkflowTests(unittest.TestCase):
 def setUp(self):
  (cw.OUTDIR/'_tmp').mkdir(exist_ok=True)
  self.tmp=tempfile.TemporaryDirectory(dir=cw.OUTDIR/'_tmp',prefix='test_')
  self.root=Path(self.tmp.name)
  original=self.root/'consultation.md';original.write_text('상담자는 개선 조치를 했다고 진술했다.')
  self.c=cw.new_case('TEST','demo');cw.add_source(self.c,self.root,original,'consultation')
  self.c['facts']=[{'id':'F1','text':'개선 조치 진술','status':'reported','source_refs':[{'source_id':'S001','locator':'1행'}]}]
  self.c['evidence']=[{'id':'E1','title':'개선 사진','purpose':'개선 확인','status':'planned','source_ids':[],'include_in_attachment':False}]
  self.c['arguments']=[{'id':'A1','title':'개선 조치','body':'개선 조치를 하였다는 진술을 확인하였습니다. 증빙은 【확인 필요】입니다.','status':'active','fact_ids':['F1'],'law_ids':[],'evidence_ids':['E1']}]
 def tearDown(self):self.tmp.cleanup()
 def reviewed(self):cw.review(self.c,self.root,'AI 시험','본문과 관련 자료의 상태를 대조한 시험')
 def test_no_sector_or_date_defaults(self):
  self.assertEqual(self.c['draft']['fields']['작성일'],cw.UNKNOWN)
  self.assertEqual(self.c['procedure']['form']['type'],'unconfirmed')
  serialized=json.dumps(self.c,ensure_ascii=False)
  self.assertNotIn('화장품',serialized);self.assertNotIn('반성',serialized)
 def test_unreviewed_claims_stop_build(self):
  e,w=cw.validate(self.c,self.root);self.assertTrue(any('재검토' in x for x in e))
 def test_evidence_change_invalidates_claim_and_document(self):
  self.reviewed();self.assertEqual(cw.validate(self.c,self.root)[0],[])
  self.c['evidence'][0]['status']='unavailable'
  e,w=cw.validate(self.c,self.root)
  self.assertTrue(any('A1' in x for x in e));self.assertTrue(any('취지·결어' in x for x in e))
 def test_narrative_edit_requires_review(self):
  self.reviewed();self.c['arguments'][0]['body']+=' 추가 문장.'
  self.assertTrue(cw.validate(self.c,self.root)[0])
 def test_raw_tampering_cannot_be_acknowledged(self):
  self.reviewed();(self.root/self.c['sources'][0]['path']).write_text('변조')
  with self.assertRaisesRegex(ValueError,'원문'):cw.review(self.c,self.root,'AI','재검토')
 def test_received_is_not_verified(self):
  self.c['evidence'][0]['status']='received'
  self.assertTrue(any('실제 수령' in x for x in cw.validate(self.c,self.root,False)[0]))
 def test_unverified_not_attachment(self):
  self.c['evidence'][0]['include_in_attachment']=True
  self.assertTrue(any('첨부' in x for x in cw.validate(self.c,self.root,False)[0]))
 def test_verified_cannot_have_unreviewed_finding(self):
  self.c['evidence'][0].update({'status':'verified','source_ids':['S001'],'finding':'unreviewed','review_note':'확인 예정'})
  self.assertTrue(any('검토 결과' in x for x in cw.validate(self.c,self.root,False)[0]))
 def test_unverified_law_not_cited(self):
  self.c['legal_review']=[{'id':'L1','status':'unverified'}];self.c['arguments'][0]['law_ids']=['L1']
  self.assertTrue(any('미확인 법령' in x for x in cw.validate(self.c,self.root,False)[0]))
 def test_form_requires_applicability(self):
  self.c['procedure']['form']['type']='standard11'
  self.assertTrue(any('서식' in x for x in cw.validate(self.c,self.root,False)[0]))
 def test_unknown_fact_needs_marker(self):
  self.c['facts'][0]['status']='unknown';self.c['arguments'][0]['body']='확정적으로 개선했습니다.'
  self.assertTrue(any('표시' in x for x in cw.validate(self.c,self.root,False)[0]))
 def test_withdrawn_claim_drops_unused_requests(self):
  self.c['arguments'][0]['status']='withdrawn'
  self.assertEqual(cw.used_evidence(self.c),[])
  self.assertNotIn('개선 사진',cw.reports(self.c,self.root,[])['소명자료_요청목록.md'])
 def test_public_evidence_labels_do_not_change_internal_ids(self):
  before=copy.deepcopy(self.c)
  fields=cw.compiled_fields(self.c,self.root)
  self.assertIn('소명자료 1. 개선 사진',fields['소명자료_목록'])
  self.assertIn('관련 자료: 소명자료 1',fields['소명'][0]['본문'])
  self.assertNotIn('E1',fields['소명자료_목록'])
  self.assertEqual(before,self.c)
  reports=cw.reports(self.c,self.root,[])
  self.assertIn('## 소명자료 1. 개선 사진',reports['소명자료_요청목록.md'])
  self.assertIn('E1',reports['소명자료_번호대조표.json'])
 def test_attachment_first_numbering_keeps_references_consistent(self):
  self.c['evidence'].append({'id':'E007','title':'확인서','status':'verified','include_in_attachment':True})
  self.c['arguments'][0]['evidence_ids']=['E1','E007']
  labels=cw.evidence_display_labels(self.c)
  self.assertEqual(labels,{'E007':'소명자료 1','E1':'소명자료 2'})
  f=cw.compiled_fields(self.c,self.root)
  self.assertIn('관련 자료: 소명자료 2 · 소명자료 1',f['소명'][0]['본문'])
  self.assertIn('소명자료 1. 확인서',f['소명자료_목록'])
 def test_product_codes_are_not_rewritten_as_evidence_numbers(self):
  self.assertEqual(cw.public_evidence_references('모델 E001의 자료 [E001]',{'E001':'소명자료 1'}),'모델 E001의 자료 소명자료 1')
 def test_dynamic_six_sections_escape_xml(self):
  f={'의견제출인_명칭':'개인 신청인','별지_서명':'개인 신청인','소명':[{'제목':f'항목 {i}','본문':'첫 문단 <script> & 확인\n\n두 번째 문단'} for i in range(6)]}
  output=self.root/'annex.docx';pdf.build_annex_docx(f,output)
  with zipfile.ZipFile(output) as z:
   x=z.read('word/document.xml').decode()
   from xml.etree import ElementTree as ET
   ET.fromstring(x)
   self.assertIn('5. 항목 4',x);self.assertIn('6. 항목 5',x);self.assertNotIn('소명_',x);self.assertNotIn('대표 개인',x);self.assertNotIn('<script>',x)
 def test_legacy_fields_keep_four_sections(self):
  f={f'소명{i}_{k}':f'{i} {k}' for i in range(1,5) for k in ['제목','본문']}
  self.assertEqual(len(pdf.normalize_fields(f)['소명']),4)
 def test_no_automatic_unknown_date(self):
  from form_layout import form_values
  v,_=form_values({});self.assertEqual(v['작성일'],cw.UNKNOWN);self.assertNotIn('작성일_년',v)
 def test_version_history_preserves_previous(self):
  from test_dialogue_flow import make_ready
  make_ready(self.c,self.root)
  self.reviewed();p=self.root/'case.json';cw.save_case(p,self.c)
  first=cw.make_draft(self.c,p,render=False)
  before=(first/'사건_스냅샷.json').read_bytes()
  self.c['evidence'][0]['status']='unavailable';self.c['arguments'][0]['body']='사진 확보가 어려워 진술만 있습니다. 【확인 필요】';self.reviewed()
  second=cw.make_draft(self.c,p,render=False)
  self.assertNotEqual(first,second);self.assertEqual((first/'사건_스냅샷.json').read_bytes(),before)
  self.assertIn('evidence E1',(second/'수정내역.md').read_text())
 def test_final_disposition_route_rejected(self):
  self.c['notice']['stage']='final'
  self.assertTrue(any('사전 의견제출 단계' in x for x in cw.validate(self.c,self.root,False)[0]))
 def test_external_write_rejected(self):
  with self.assertRaisesRegex(ValueError,'산출 경로'):pdf.checked_output('/private/tmp/outside-opinion-tests')
if __name__=='__main__':unittest.main()
