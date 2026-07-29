#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""내 지식창고 대시보드 만들기 (make_dashboard.py)

지식창고 안의 목차·처리 대장·일지·기억 파일을 훑어 숫자를 세고,
그 숫자를 `dashboard.html` 한 파일에 박아 넣습니다. 브라우저로 더블클릭해 봅니다.

사용법
    python3 tools/make_dashboard.py            # 이 파일이 있는 폴더의 상위 폴더 = 지식창고
    python3 tools/make_dashboard.py ~/JARVIS   # 지식창고 위치를 직접 지정
    python3 tools/make_dashboard.py --no-name-guess   # 사람 이름 추정 가리기를 끔

안전 규칙 (이 스크립트가 스스로 지키는 것)
    1. 인터넷에 접속하지 않습니다. 파이썬 기본 기능만 씁니다(추가 설치 0).
    2. 읽는 곳은 아래 목록뿐입니다.
         wiki/index.md · wiki/.ingest-ledger.tsv · wiki/log.md
         wiki/*.md (파일 이름과 [[링크]]만)
         memory/오늘메모.md · memory/나에대해.md · memory/업무규칙.md (줄 수·글자 수만)
         DATA/** (파일 이름 목록만 — 파일 내용은 열지 않습니다)
    3. 절대 열지 않는 곳: `서류함/`(의뢰인 실명 자료) · `문서작업/` · DATA 파일의 본문.
       — graphify 안전 규칙과 같습니다: 인덱싱은 wiki 폴더만, 서류함과 DATA 본문은 제외.
    4. 쓰는 파일은 `dashboard.html` 하나뿐입니다. 그 밖의 어떤 파일도 만들거나 고치지 않습니다.
    5. 사람 이름·상호명·전화번호·사업자등록번호·접수번호·금액·주소·이메일·여권번호처럼
       보이는 표기는 화면에 가려서(마스킹) 표시합니다.
       원래 파일은 손대지 않습니다 — 화면 표시만 가립니다.
       ⚠️ 가림은 완전하지 않습니다. 규칙에 없는 형태는 그대로 지나갑니다 —
          "가려지지 않았으니 안전하다"는 뜻이 아닙니다. 이 파일은 어떤 경우에도 공개하지 않습니다.

파이썬 3.9 이상 · 표준 라이브러리만 사용.
"""

import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime

# ─────────────────────────────────────────────────────────────
# 설정값
# ─────────────────────────────────────────────────────────────

TEMPLATE_NAME = "dashboard_template.html"   # tools/ 안에 두는 원본 서식
OUTPUT_NAME = "dashboard.html"              # 지식창고 루트에 만드는 결과물
# 데이터 자리: <script>const DATA = /*__DATA__*/ null;</script>
# 앞뒤(<script> 태그)는 그대로 두고 가운데 값만 갈아 끼운다.
# 그룹1 = 마커까지, 그룹2 = 줄의 마지막 세미콜론 뒤(</script> 등).
MARKER_RE = re.compile(r"^(.*const DATA = /\*__DATA__\*/)\s*.*;(.*)$", re.MULTILINE)

MAX_RECENT = 10          # 최근 정리 표시 건수
MAX_LIST = 40            # 목록형 항목 최대 표시 건수 (미처리 등)
MIN_LINKS = 2            # 이 미만이면 '연결 부족'

MEMORY_FILES = [         # (파일명, 줄 상한, 글자 상한)
    ("오늘메모.md", 200, None),
    ("나에대해.md", 30, 1500),
    ("업무규칙.md", 60, 3000),
]

SKIP_DIR_NAMES = {"__pycache__", "node_modules", ".git", ".obsidian"}
SKIP_FILE_NAMES = {"안내.md", ".DS_Store", "Thumbs.db", "desktop.ini"}

# ─────────────────────────────────────────────────────────────
# 민감정보 가리기(마스킹)
# ─────────────────────────────────────────────────────────────

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
#  (4) 파일 이름 안에서 구분기호로 끊긴 토막 : "홍길동_계약서.pdf", "서류함/김철수/"
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


def days_since(text):
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            d = datetime.strptime(text.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
        return max(0, (date.today() - d).days)
    return None


# ─────────────────────────────────────────────────────────────
# 읽기 — 목차(wiki/index.md)
# ─────────────────────────────────────────────────────────────

_PAGE_LINE = re.compile(r"^\s*[-*]\s*\[\[([^\]|#]+)")
_GIST = re.compile(r"\]\]\s*[—–-]\s*(.+)$")


def parse_index(text):
    """카테고리 목록을 뽑는다. 서식: '## 이름' / '> 여기엔 무엇이 있나: …' / '- [[페이지]] — 요지'"""
    cats = []
    cur = None
    for line in (text or "").splitlines():
        st = line.strip()
        if st.startswith("## ") and not st.startswith("### "):
            cur = {"이름": nfc(st[3:].strip()), "설명": "", "페이지": []}
            cats.append(cur)
            continue
        if cur is None:
            continue
        if st.startswith(">"):
            body = st.lstrip("> ").strip()
            if body.startswith("여기엔 무엇이 있나"):
                cur["설명"] = body.split(":", 1)[-1].strip() if ":" in body else body
            elif not cur["설명"]:
                cur["설명"] = body
            continue
        m = _PAGE_LINE.match(line)
        if m:
            gist = _GIST.search(st)
            cur["페이지"].append({
                "이름": nfc(m.group(1).strip()),
                "요지": nfc(gist.group(1).strip()) if gist else "",
            })
    return cats


# ─────────────────────────────────────────────────────────────
# 읽기 — 처리 대장(wiki/.ingest-ledger.tsv)
# ─────────────────────────────────────────────────────────────

def parse_ledger(text):
    """(등재 경로 집합, 등재 파일이름 집합, 보류 목록)"""
    paths, stems, holds = set(), set(), []
    for line in (text or "").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = [c.strip() for c in line.split("\t")]
        while len(cells) < 4:
            cells.append("")
        src, verdict, landed, when = cells[0], cells[1], cells[2], cells[3]
        if src in ("자료경로", "자료 경로") or verdict == "판정":
            continue  # 머리글 줄
        norm = nfc(src).replace("\\", "/").lstrip("./")
        paths.add(norm)
        if norm.startswith("DATA/"):
            paths.add(norm[5:])
        stems.add(os.path.splitext(os.path.basename(norm))[0])
        if verdict.startswith("보류") or landed.startswith("보류"):
            reason, cond, started = "", "", when
            body = landed[3:].strip(" :") if landed.startswith("보류") else landed
            parts = [p.strip() for p in body.split("/")]
            if parts:
                reason = parts[0]
            if len(parts) > 1:
                cond = parts[1]
            if len(parts) > 2 and parts[2]:
                started = parts[2]
            holds.append({
                "자료": norm, "사유": reason, "해소조건": cond,
                "시작일": started, "경과일": days_since(started),
            })
    return paths, stems, holds


# ─────────────────────────────────────────────────────────────
# 읽기 — 일지(wiki/log.md)
# ─────────────────────────────────────────────────────────────

_DATE_HEAD = re.compile(r"^##\s+(.+?)\s*$")


def parse_log(text, limit=MAX_RECENT):
    out = []
    cur_date = ""
    for line in (text or "").splitlines():
        m = _DATE_HEAD.match(line)
        if m:
            head = m.group(1).strip()
            cur_date = "" if head.upper().startswith("YYYY") else head
            continue
        st = line.strip()
        if not cur_date or not st.startswith(("- ", "* ")):
            continue
        body = st[2:].strip()
        if len(body) > 140:
            body = body[:140] + "…"
        out.append({"날짜": cur_date, "내용": nfc(body)})
        if len(out) >= limit:
            break
    return out


# ─────────────────────────────────────────────────────────────
# 읽기 — 위키 페이지(파일 이름 + [[링크]]만)
# ─────────────────────────────────────────────────────────────

_LINK = re.compile(r"\[\[([^\]|#]+)")


def scan_wiki_pages(wiki_dir):
    pages = {}
    try:
        names = sorted(os.listdir(wiki_dir))
    except OSError:
        return pages
    for name in names:
        if not name.endswith(".md") or name in ("index.md", "log.md"):
            continue
        body = read_text(os.path.join(wiki_dir, name))
        if body is None:
            continue
        stem = nfc(os.path.splitext(name)[0])
        pages[stem] = {nfc(t.strip()) for t in _LINK.findall(body)}
    return pages


# ─────────────────────────────────────────────────────────────
# 읽기 — DATA 폴더 (파일 이름 목록만, 내용은 열지 않음)
# ─────────────────────────────────────────────────────────────

def scan_data_files(data_dir):
    found = []
    for cur, dirs, files in os.walk(data_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIR_NAMES]
        for fn in sorted(files):
            if fn.startswith(".") or fn in SKIP_FILE_NAMES:
                continue
            rel = os.path.relpath(os.path.join(cur, fn), os.path.dirname(data_dir))
            found.append(nfc(rel).replace("\\", "/"))
    return sorted(found)


# ─────────────────────────────────────────────────────────────
# 읽기 — 기억 파일 (줄 수·글자 수만)
# ─────────────────────────────────────────────────────────────

def scan_memory(memory_dir):
    rows = []
    for fname, max_lines, max_chars in MEMORY_FILES:
        body = read_text(os.path.join(memory_dir, fname))
        if body is None:
            continue
        lines = [ln for ln in body.splitlines() if ln.strip()]
        n_lines, n_chars = len(lines), len(body)
        over = (n_lines > max_lines) or (max_chars is not None and n_chars > max_chars)
        near = (n_lines >= max_lines * 0.8) or (max_chars is not None and n_chars >= max_chars * 0.8)
        rows.append({
            "파일": fname, "줄수": n_lines, "글자수": n_chars,
            "상한줄": max_lines, "상한자": max_chars,
            "상태": "상한 초과 — 정리 필요" if over else ("상한에 가까움" if near else "여유"),
        })
    return rows


# ─────────────────────────────────────────────────────────────
# 계산 — 지표 모으기
# ─────────────────────────────────────────────────────────────

def build_data(root, mask):
    wiki_dir = os.path.join(root, "wiki")
    data_dir = os.path.join(root, "DATA")
    memory_dir = os.path.join(root, "memory")
    missing = []

    # 목차
    index_text = read_text(os.path.join(wiki_dir, "index.md"))
    if index_text is None:
        missing.append("카테고리")
    cats = parse_index(index_text)

    # 위키 페이지 + 연결
    pages = scan_wiki_pages(wiki_dir)
    inbound = {}
    for src, targets in pages.items():
        for t in targets:
            if t in pages and t != src:
                inbound.setdefault(t, set()).add(src)
    link_count = {}
    for stem, targets in pages.items():
        nb = {t for t in targets if t in pages and t != stem} | inbound.get(stem, set())
        link_count[stem] = len(nb)

    # 페이지 → 카테고리
    page_cat = {}
    for c in cats:
        for p in c["페이지"]:
            page_cat.setdefault(p["이름"], c["이름"])

    # 분야 횡단 링크 비율 (같은 쌍은 한 번만 센다)
    pairs = set()
    for src, targets in pages.items():
        for t in targets:
            if t in pages and t != src:
                pairs.add(tuple(sorted((src, t))))
    total_pair = cross_pair = 0
    for a, b in pairs:
        ca, cb = page_cat.get(a), page_cat.get(b)
        if ca and cb:
            total_pair += 1
            if ca != cb:
                cross_pair += 1
    cross_ratio = round(cross_pair / total_pair * 100) if total_pair else None

    # 카테고리별 페이지 (링크 수 붙이기)
    listed = set()
    cat_out = []
    for c in cats:
        rows = []
        for p in c["페이지"]:
            listed.add(p["이름"])
            rows.append({
                "이름": mask(p["이름"]),
                "요지": mask(p["요지"]),
                "링크수": link_count.get(p["이름"]),
            })
        cat_out.append({
            "이름": mask(c["이름"]), "설명": mask(c["설명"]),
            "페이지수": len(rows), "페이지": rows,
        })
    unlisted = [mask(s) for s in sorted(pages) if s not in listed]

    # 연결 부족
    weak = sorted(
        ({"이름": mask(s), "링크수": n} for s, n in link_count.items() if n < MIN_LINKS),
        key=lambda r: (r["링크수"], r["이름"]),
    )[:MAX_LIST]

    # 처리 대장
    ledger_text = read_text(os.path.join(wiki_dir, ".ingest-ledger.tsv"))
    done_paths, done_stems, holds = parse_ledger(ledger_text)

    # DATA 미처리
    if not os.path.isdir(data_dir) or ledger_text is None:
        missing.append("미처리")
        data_files, todo = [], []
    else:
        data_files = scan_data_files(data_dir)
        todo = []
        for rel in data_files:
            stem = os.path.splitext(os.path.basename(rel))[0]
            no_prefix = rel[5:] if rel.startswith("DATA/") else rel
            if rel in done_paths or no_prefix in done_paths or stem in done_stems:
                continue
            todo.append(rel)

    # 일지
    log_text = read_text(os.path.join(wiki_dir, "log.md"))
    if log_text is None:
        missing.append("최근정리")
    recent = [{"날짜": mask(r["날짜"]), "내용": mask(r["내용"])} for r in parse_log(log_text)]

    # 기억
    memory = scan_memory(memory_dir)

    holds_out = []
    for h in sorted(holds, key=lambda h: (h["경과일"] is None, -(h["경과일"] or 0))):
        holds_out.append({
            "자료": mask(h["자료"]), "사유": mask(h["사유"]),
            "해소조건": mask(h["해소조건"]), "경과일": h["경과일"],
        })

    payload = {
        "생성시각": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "지식창고이름": mask(nfc(os.path.basename(os.path.abspath(root)))),
        "요약": {
            "위키페이지수": len(pages),
            "미처리": len(todo),
            "보류": len(holds_out),
            "횡단비율": cross_ratio,
        },
        "카테고리": cat_out,
        "미분류페이지": unlisted[:MAX_LIST],
        "최근정리": recent,
        "미처리목록": [mask(f) for f in todo[:MAX_LIST]],
        "보류목록": holds_out[:MAX_LIST],
        "링크부족": weak,
        "기억": memory,
        "지표없음": missing,
        "경고": {},   # 마스킹 집계는 모든 문자열 처리 후 채운다
    }
    return payload


# ─────────────────────────────────────────────────────────────
# 쓰기 — HTML 한 파일에 숫자 박아 넣기
# ─────────────────────────────────────────────────────────────

def find_template(root):
    """tools/dashboard_template.html 를 우선 쓰고, 없으면 기존 dashboard.html 을 서식으로 재사용."""
    candidates = [
        os.path.join(root, "tools", TEMPLATE_NAME),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), TEMPLATE_NAME),
        os.path.join(root, OUTPUT_NAME),
    ]
    for path in candidates:
        text = read_text(path)
        if text and MARKER_RE.search(text):
            return path, text
    return None, None


def inject(template_text, payload):
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # 화면 표시용 글자가 HTML 구조를 깨뜨리지 못하게 감싼다 (< > & 를 유니코드 표기로)
    blob = blob.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return MARKER_RE.sub(lambda m: m.group(1) + " " + blob + ";" + m.group(2), template_text, count=1)


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    args = [a for a in argv[1:] if not a.startswith("--")]
    guess_names = "--no-name-guess" not in argv

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.expanduser(args[0])) if args else os.path.dirname(here)

    if not os.path.isdir(root):
        say("❌ 지식창고 폴더를 찾지 못했습니다: " + root)
        say("   python3 tools/make_dashboard.py <지식창고 경로> 처럼 위치를 알려 주세요.")
        return 1
    if not os.path.isdir(os.path.join(root, "wiki")):
        say("❌ 여기가 지식창고가 맞는지 확인해 주세요 — wiki 폴더가 없습니다: " + root)
        say("   python3 tools/make_dashboard.py <지식창고 경로> 처럼 위치를 알려 주세요.")
        return 1

    tpl_path, tpl_text = find_template(root)
    if tpl_text is None:
        say("❌ 대시보드 서식 파일을 찾지 못했습니다.")
        say("   찾은 곳: tools/" + TEMPLATE_NAME + " · " + OUTPUT_NAME)
        say("   AI에게 「5_챗지피티/templates/dashboard.html 을 tools/" + TEMPLATE_NAME + " 로 복사해줘」라고 말씀하세요.")
        return 1

    mask = Masker(guess_names=guess_names)
    payload = build_data(root, mask)
    payload["경고"] = {"마스킹건수": mask.total, "유형": mask.kinds}

    out_path = os.path.join(root, OUTPUT_NAME)
    try:
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(inject(tpl_text, payload))
    except OSError as e:
        say("❌ 파일을 저장하지 못했습니다: " + str(e))
        return 1

    s = payload["요약"]
    ratio = "—" if s["횡단비율"] is None else str(s["횡단비율"]) + "%"
    say("✅ 대시보드를 새로 그렸습니다.")
    say("   파일: " + out_path)
    say("   서식: " + tpl_path)
    say("   위키 " + str(s["위키페이지수"]) + "쪽 · 아직 정리 안 된 자료 " + str(s["미처리"]) +
        "건 · 보류 " + str(s["보류"]) + "건 · 분야 횡단 연결 " + ratio)
    if payload["지표없음"]:
        say("   ℹ️ 다음 항목은 '자료 없음'으로 표시됩니다(파일을 찾지 못함): " + ", ".join(payload["지표없음"]))
    if mask.total:
        say("   ⚠️ 민감정보로 보이는 표기 " + str(mask.total) + "건을 가려서 표시했습니다 (" +
            ", ".join(mask.kinds) + ")")
    say("")
    say("👉 이제 지식창고 폴더의 " + OUTPUT_NAME + " 파일을 더블클릭해서 열어 보세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
