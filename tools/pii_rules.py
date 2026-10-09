"""개인정보 판정 규칙과 읽기 보조 함수. 자동 스캔·쓰기·네트워크 호출 없음."""
import re
import unicodedata

# 판정 규칙 원형
# 상위 50성 (성씨가 적으면 그만큼 못 가리고 지나갑니다 — 놓치는 쪽이 더 위험합니다)
SURNAMES = ("김이박최정강조윤장임한오서신권황안송전홍"
            "유고문양손배백허남심노하곽성차주우구나민진지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모")

# 이름처럼 보이지만 이름이 아닌 흔한 세 글자 낱말 (가리지 않음)
NOT_NAMES = {
    "이의서", "이력서", "이용료", "이사회", "이해도", "이자율", "이전건", "이관건", "이하생",
    "박물관", "박람회",
    "최종본", "최종안", "최신판", "최소한", "최초안", "최대치",
    "정보화", "정산서", "정정본", "정기간", "정부안", "정책안", "정관집", "정보망", "정리본", "정본화",
    "강의록", "강제성", "강남구", "강습소", "강사료",
    "조사서", "조례집", "조정안", "조치안", "조직도", "조합원", "조회수",
    "장부철", "장소별", "장애인", "장기간",
    "임대차", "임차인", "임대인", "임시본", "임원진", "임의로",
    "한글판", "한국어", "한도액", "한눈에",
    "오탈자", "오류표", "오전중",
    "서류함", "서식집", "서명란", "서울시", "서비스", "서면화", "서류철", "서류상",
    "신청서", "신고서", "신규건", "신용장", "신분증", "신설안", "신청인", "신청일", "신청건",
    "권리금", "권한별",
    "안내문", "안내서", "안전성", "안건지", "안내판",
    "송달서", "송부문", "송장철",
    "전자책", "전문가", "전체본", "전년도", "전자세", "전화번", "전송본", "전달함",
    "홍보물", "홍보안", "홍보용",
    "윤리성", "황사철", "이용자", "이용권", "최적화", "전자화", "정상화",
    # 성씨 목록을 50성으로 넓히면서 함께 걸리게 된 흔한 낱말들
    "고객사", "고시문", "문의처", "양수인", "양도인", "손해액", "배송료", "백지식",
    "허가건", "남부청", "심판례", "노무사", "하도급", "성분표", "차액분", "주소지",
    "구비류", "민원실", "진행중", "지자체", "채권자", "채무자", "소유자", "신청자",
    "원본철", "천재지", "공고문", "현황판", "함께쓰", "변경건", "여신용", "추가건",
    "도면집", "석면조", "선정안", "설명서", "마감일", "길안내", "연장건", "위임장",
    "표준안", "명의자", "기한내", "반려건", "왕복권", "금액란", "옥외용", "육하원",
    "인계서", "맹지형", "제출본", "모범안",
    # 이 지식창고에서 자주 쓰는 낱말 (카테고리·폴더 이름으로 그대로 화면에 나옵니다)
    "인허가", "인터뷰", "인수인", "인용문", "도로명", "민원인", "방문객", "성수기",
    "차상위", "금지어", "원문본", "고시안", "주요건", "지침안", "제출처", "소재지",
}
# 이런 글자로 끝나면 사람 이름이 아니라고 본다
#  · 앞쪽: 문서·서류를 가리키는 말 (신청서·허가증·조례집…)
#  · 가운데: 절차·수량을 가리키는 말 (제출일·처리중·수수료…)
#  · 뒤쪽: 행정구역 이름 (김포시·임실군·한림읍·조안면) — 사람 이름은 이 글자로 끝나지 않는다
NOT_NAME_TAIL = set("서증집철록함란표료액율판회청처물량값법령건"
                    + "일장점세비례사중체실급"
                    + "시군읍면")
# 글월 한가운데(조사가 뒤에 붙은 자리)에서만 추가로 걸러 내는 끝글자.
#  "제목에는"·"구분자는"·"문제되는"·"이어지는" 처럼 낱말 토막이 이름으로 오인되는 것을 막는다.
#  파일 이름 토막(홍길동_계약서.pdf)에는 적용하지 않는다 — 거기서는 넓게 잡는 편이 안전하다.
JOSA_STOP_TAIL = set("에의을를은는이가과와도만로며고나지되하자보후전내외중간초말들져어여게면니")

# 「의뢰인 …」·「담당자 …」 뒤에 붙어도 사람 이름이 아닌 낱말 (가리지 않음)
LABEL_STOP = {
    "제공", "반응", "정보", "성명", "이름", "확인", "요청", "목록", "관련", "본인",
    "대리", "동의", "연락", "주소", "상담", "사건", "자료", "서류", "응대", "특정",
    "측", "분", "님", "쪽", "께", "별", "용",
}

# 「주식회사 …」 뒤에 붙어도 상호가 아닌 일반 낱말 (가리지 않음)
_CORP_STOP = {
    "설립", "등기", "정관", "명의", "형태", "전환", "해산", "청산", "합병", "분할",
    "제도", "요건", "절차", "개요", "일반", "변경", "말소", "임원", "주주", "지분",
}


def _mask_corp(m):
    """법인 표기 + 상호 → 「(주)○○」. 일반 낱말이 붙은 경우는 그대로 둔다."""
    head, body = m.group(1), m.group(2)
    if body in _CORP_STOP:
        return m.group(0)
    return ("(주)" if head in ("(주)", "㈜", "(유)", "㈜") else head + " ") + "○" * min(len(body), 2)


_STRONG_RULES = [
    ("주민등록번호", re.compile(r"(?<!\d)\d{6}[-–]\d{7}(?!\d)"), lambda m: "******-*******"),
    # 법인 표기 — 앞에 붙는 형태: (주)예시상사 · ㈜가나물산 · 주식회사 한빛상사
    ("상호명", re.compile(r"(\(주\)|㈜|\(유\)|주식회사|유한회사|합자회사|합명회사|유한책임회사)"
                       r"\s*([가-힣A-Za-z0-9]{1,12})"), _mask_corp),
    # 법인 표기 — 뒤에 붙는 형태: 한빛물산(주)
    ("상호명", re.compile(r"(?<![가-힣A-Za-z0-9])([가-힣A-Za-z0-9]{1,12})\s*(\(주\)|㈜|\(유\))"),
     lambda m: "○" * min(len(m.group(1)), 2) + m.group(2)),
    # 여권번호 — 영문 1~2자 + 숫자 8자리 (외국인·출입국 업무에서 자주 나옵니다)
    ("여권번호", re.compile(r"(?<![A-Za-z0-9])[A-Z]{1,2}\d{8}(?![0-9A-Za-z])"),
     lambda m: m.group(0)[0] + "*" * (len(m.group(0)) - 1)),
    ("사업자등록번호", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{5}(?!\d)"), lambda m: "***-**-*****"),
    ("전화번호", re.compile(r"(?<!\d)(01\d|0\d{1,2})[-. ]?\d{3,4}[-. ]?\d{4}(?!\d)"),
     lambda m: m.group(1) + "-****-****"),
    # 민원 접수번호: 20으로 시작하는 10~12자리 (기관마다 자릿수가 다릅니다)
    ("접수번호", re.compile(r"(?<!\d)20\d{8,10}(?!\d)"), lambda m: m.group(0)[:4] + "*" * (len(m.group(0)) - 4)),
    ("이메일", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), lambda m: "***@***"),
    ("금액", re.compile(r"(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d{4,})\s*원"), lambda m: "***원"),
    # 주소 — 시·도 + 시/군/구 + 도로명·동 (예: 서울시 강남구 테헤란로 123)
    ("주소", re.compile(r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|"
                      r"전북|전남|경북|경남|제주)[가-힣]*\s*[가-힣]+(?:시|군|구)"
                      r"\s*[가-힣0-9]+(?:로|길|동|읍|면)[0-9\-가-힣\s]{0,12}"), lambda m: "○○ 지역"),
]

# 이름 추정 규칙 3가지.
#  (1) 직함·호칭이 뒤에 붙는 경우      : "김철수 대표", "김철수님"
#  (2) 「의뢰인:」 같은 이름표가 앞에   : "담당자 김철수"
#  (3) 조사가 뒤에 붙는 경우           : "김철수에게", "김철수가"
#  (4) 파일 이름 안에서 구분기호로 끊긴 토막 : "홍길동_계약서.pdf", "2_서류철/김철수/"
# (3)(4)를 '띄어쓰기로 끊긴 세 글자 전부'로 넓히면 "서류를"·"조항별" 같은 보통 낱말까지
# 가려 버립니다(실측 확인). 그래서 조사·구분기호가 붙은 자리로만 좁힙니다.
_NAME_SUFFIX = ("님", "씨", "대표", "사장", "과장", "부장", "팀장", "주무관", "변호사", "행정사", "의뢰인", "고객")
_JOSA = ("님", "씨", "께서", "께", "에게", "한테", "은", "는", "이", "가", "을", "를", "와", "과", "의", "도")
_DELIM = r"_\-/\\().,\[\]"

_RULE_NAME_SUFFIX = re.compile(
    "(?<![가-힣])([" + SURNAMES + "][가-힣]{1,2})(\\s*)(" + "|".join(_NAME_SUFFIX) + ")(?![가-힣])")
_RULE_NAME_LABEL = re.compile(
    "(의뢰인|상담자|신청인|대표자|담당자|성명|이름)(\\s*[:：\\-_]?\\s*)([" + SURNAMES + "][가-힣]{1,2})(?![가-힣])")
_RULE_NAME_JOSA = re.compile(
    "(?<![가-힣])([" + SURNAMES + "][가-힣]{2})(?=(?:" + "|".join(_JOSA) + ")(?![가-힣]))")
_RULE_NAME_TOKEN = re.compile(
    "(?:^|(?<=[" + _DELIM + "]))([" + SURNAMES + "][가-힣]{2})(?=$|[" + _DELIM + "])")
# (5) 외국인 성명 — 로마자 대문자 두 덩이 이상 (예: NGUYEN VAN A)
#     출입국·비자 업무에서는 오히려 이쪽이 다수입니다.
_RULE_NAME_ROMAN = re.compile(r"(?<![A-Za-z])[A-Z]{2,}(?:\s+[A-Z]+){1,3}(?![A-Za-z])")
# (6) 외국인 성명 — 한자 이름이 구분기호로 끊긴 토막 (예: 王小明_비자연장.pdf)
_RULE_NAME_HANJA = re.compile(
    "(?:^|(?<=[" + _DELIM + "\\s]))([\u4e00-\u9fff]{2,4})(?=$|[" + _DELIM + "\\s])")


def _hide_name(name):
    return name[0] + "○" * (len(name) - 1)


class Masker:
    """민감정보로 보이는 표기를 가리고, 무엇을 몇 건 가렸는지 세어 둔다."""

    def __init__(self, guess_names=True):
        self.guess_names = guess_names
        self.counts = {}

    def _hit(self, kind):
        self.counts[kind] = self.counts.get(kind, 0) + 1

    def __call__(self, text):
        if not text:
            return text
        s = str(text)

        for kind, pattern, repl in _STRONG_RULES:
            def _sub(m, kind=kind, repl=repl):
                self._hit(kind)
                return repl(m)
            s = pattern.sub(_sub, s)

        if not self.guess_names:
            return s

        def _sub_suffix(m):
            self._hit("이름(추정)")
            return _hide_name(m.group(1)) + m.group(2) + m.group(3)
        s = _RULE_NAME_SUFFIX.sub(_sub_suffix, s)

        def _sub_label(m):
            tok = m.group(3)
            if tok in NOT_NAMES or tok in LABEL_STOP or tok[-1] in JOSA_STOP_TAIL:
                return m.group(0)
            self._hit("이름(추정)")
            return m.group(1) + m.group(2) + _hide_name(tok)
        s = _RULE_NAME_LABEL.sub(_sub_label, s)

        def _sub_guess(m, extra_stop=frozenset()):
            tok = m.group(1)
            if tok in NOT_NAMES or tok[-1] in NOT_NAME_TAIL or tok[-1] in extra_stop:
                return tok
            self._hit("이름(추정)")
            return _hide_name(tok)
        s = _RULE_NAME_JOSA.sub(lambda m: _sub_guess(m, JOSA_STOP_TAIL), s)
        s = _RULE_NAME_TOKEN.sub(_sub_guess, s)

        def _sub_foreign(m):
            self._hit("이름(추정)")
            tok = m.group(0)
            return tok[0] + "○" * (len(tok.replace(" ", "")) - 1)
        s = _RULE_NAME_ROMAN.sub(_sub_foreign, s)
        s = _RULE_NAME_HANJA.sub(_sub_foreign, s)

        return s

    @property
    def total(self):
        return sum(self.counts.values())

    @property
    def kinds(self):
        return [k for k, _ in sorted(self.counts.items(), key=lambda kv: -kv[1])]


# ─────────────────────────────────────────────────────────────
# 작은 도구들
# ─────────────────────────────────────────────────────────────

def nfc(s):
    return unicodedata.normalize("NFC", str(s or ""))


def read_text(path):
    """파일을 읽는다. 없거나 못 읽으면 None (프로그램은 멈추지 않는다)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def say(msg):
    """윈도우 옛 콘솔에서 이모지가 깨져도 프로그램이 멈추지 않도록."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))

