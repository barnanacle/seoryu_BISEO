import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bin'))
import case_workflow as cw
import dialogue_flow as flow
from document_runtime import temp_root


def prepare(case,root):
    notice=root/'notice.txt';notice.write_text('가상 사전통지: 영업정지 예정. 실제 사건이 아닌 단위 검사 자료.')
    cw.add_source(case,root,notice,'notice')
    case['notice']['sanctions']=[{'type':'영업정지 예정','scope':'가상 범위'}]
    case['workflow']['criteria']=[{'id':cid,'category':category,'title':'검토 필요','requirement':'【확인 필요】','analysis':'해당 규정을 확인하고 사실을 질문해야 합니다.','assessment':'unknown','law_ids':[]} for cid,category in [('C1','non_imposition'),('C2','mitigation')]]
    case['workflow']['questions']=[{'id':'Q1','question':'통지된 사실과 다른 점이 있습니까?','why':'성립 요건과 감경 사정을 확인합니다.','criterion_ids':['C1','C2']}]
    return notice


def make_ready(case,root):
    prepare(case,root);path=root/'case.json'
    flow.issue_checklist(case,path,render=False)
    answer=root/'answer.txt';answer.write_text('기억나지 않아 확인이 필요합니다.')
    sid=flow.receive_response(case,path,answer)
    case['workflow']['answers']=[{'question_id':'Q1','state':'unknown','answer':'【확인 필요】','source_refs':[{'source_id':sid,'locator':'1행'}]}]
    return path


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=temp_root(),prefix='flow_test_');self.root=Path(self.tmp.name)
        self.case=cw.new_case('FLOW_TEST','demo');self.path=self.root/'case.json'
    def tearDown(self):self.tmp.cleanup()
    def test_notice_only_cannot_make_opinion(self):
        prepare(self.case,self.root)
        with self.assertRaisesRegex(ValueError,'질문지'):cw.make_draft(self.case,self.path,render=False)
    def test_incomplete_verified_law_is_rejected(self):
        prepare(self.case,self.root)
        self.case['legal_review']=[{'id':'L1','status':'verified'}]
        self.assertTrue(any('원문·출처' in e for e in flow.validate_questionnaire(self.case)))
    def test_failed_render_directory_is_preserved_on_retry(self):
        prepare(self.case,self.root)
        old=self.root/'상담준비/QSET-001';old.mkdir(parents=True);(old/'partial.txt').write_text('previous attempt')
        issued=flow.issue_checklist(self.case,self.path,False)
        self.assertEqual(issued.name,'QSET-002');self.assertTrue((old/'partial.txt').exists())
    def test_response_requires_issued_checklist(self):
        source=prepare(self.case,self.root)
        with self.assertRaisesRegex(ValueError,'질문지'):flow.receive_response(self.case,self.path,source)
    def test_checklist_requires_legal_criteria_and_questions(self):
        prepare(self.case,self.root);self.case['workflow']['criteria']=[]
        self.assertTrue(flow.validate_questionnaire(self.case))
    def test_checklist_only_does_not_authorize_draft(self):
        prepare(self.case,self.root);flow.issue_checklist(self.case,self.path,False)
        with self.assertRaisesRegex(ValueError,'답변 또는 상담'):flow.assert_draft_ready(self.case,self.path)
    def test_answers_must_be_mapped(self):
        make_ready(self.case,self.root);self.case['workflow']['answers']=[]
        with self.assertRaisesRegex(ValueError,'질문별 답변'):flow.assert_draft_ready(self.case,self.path)
    def test_unknown_answer_is_not_invented(self):
        make_ready(self.case,self.root);self.assertEqual(flow.assert_draft_ready(self.case,self.path)['id'],'QSET-001')
    def test_changed_question_requires_new_checklist(self):
        make_ready(self.case,self.root);self.case['workflow']['questions'][0]['question']='변경된 질문'
        with self.assertRaisesRegex(ValueError,'바뀌었습니다'):flow.assert_draft_ready(self.case,self.path)
    def test_new_checklist_needs_response_reconciliation(self):
        make_ready(self.case,self.root);flow.issue_checklist(self.case,self.path,False)
        with self.assertRaisesRegex(ValueError,'답변 또는 상담'):flow.assert_draft_ready(self.case,self.path)
    def test_self_service_questionnaire_has_usable_guidance(self):
        prepare(self.case,self.root);self.case['workflow']['audience']='self'
        text=flow.questionnaire_markdown(self.case,'QSET-001')
        for term in ['본인이 직접','같은 대화','감경','불처분','답변','왜 확인하나요']:self.assertIn(term,text)
    def test_answer_citations_must_use_the_received_source(self):
        make_ready(self.case,self.root)
        self.case['workflow']['answers'][0]={'question_id':'Q1','state':'answered','answer':'아니오','source_refs':[{'source_id':'S001','locator':'1행'}]}
        with self.assertRaisesRegex(ValueError,'상담 원문'):flow.assert_draft_ready(self.case,self.path)
    def test_questionnaire_split_across_pages_is_rejected(self):
        from unittest.mock import patch,MagicMock
        pdf=MagicMock();pdf.__enter__.return_value=pdf
        first=MagicMock();first.extract_text.return_value='Q1 확인할 질문\n- 왜 확인하나요: 사유'
        second=MagicMock();second.extract_text.return_value='- 자료가 있나요 / 파일명 또는 발급처: _____'
        pdf.pages=[first,second]
        with patch('pdfplumber.open',return_value=pdf):
            result=flow.validate_questionnaire_layout('synthetic.pdf',[{'id':'Q1'}])
        self.assertFalse(result['passed']);self.assertIn('다른 쪽',result['errors'][0])
    def test_questionnaire_missing_question_is_rejected(self):
        from unittest.mock import patch,MagicMock
        pdf=MagicMock();pdf.__enter__.return_value=pdf;pdf.pages=[]
        with patch('pdfplumber.open',return_value=pdf):
            result=flow.validate_questionnaire_layout('synthetic.pdf',[{'id':'Q1'}])
        self.assertFalse(result['passed']);self.assertIn('누락',result['errors'][0])
    def test_different_conversations_have_different_bindings(self):
        self.assertNotEqual(flow.session_path('conv-A'),flow.session_path('conv-B'))
        with self.assertRaises(ValueError):flow.session_path('')

if __name__=='__main__':unittest.main()
