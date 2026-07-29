#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
style_pick.py — 전자명함 디자인 자동 결정 (정본)

무엇을 하나
    인터뷰 답으로 만든 "씨앗 문자열" 하나를 계산해서,
    6개 축(색·배치·글자·장식·모서리·강조)에서 각각 하나씩 고릅니다.
    조합은 8 x 4 x 3 x 6 x 3 x 3 = 5,184가지입니다.

결과물
    1) 화면에 한국어 요약 (사람이 읽는 용도)
    2) style.json  (재현용 기록 + CSS 값)
    3) index.html 에 붙여 넣을 <body ...> 한 줄

안전 규칙 (이 파일은 아래를 지킵니다)
    - 파이썬 표준 라이브러리만 씁니다. 추가 설치가 필요 없습니다.
    - 인터넷에 아무것도 보내지 않고, 아무것도 내려받지 않습니다.
    - 파일은 style.json 하나만 만듭니다. 다른 파일은 읽지도 고치지도 않습니다.
    - 의뢰인 정보를 다루지 않습니다. 씨앗에는 본인 명함 정보만 들어갑니다.

파이썬이 없어도 됩니다
    이 계산은 손으로도 할 수 있습니다 -> 5_챗지피티/명함_디자인표.md 3절 "방법 2 폴백".
    다만 두 방법은 계산법이 달라 서로 다른 조합이 나옵니다.
    한 번 정한 방법을 계속 쓰시면 결과는 언제나 같습니다(재현됩니다).

쓰는 법
    python3 style_pick.py
        -> 다섯 조각을 하나씩 물어봅니다.

    python3 style_pick.py "홍길동" "행정사사무소청효" "행정사" "이메일" "든든한"
        -> 물어보지 않고 바로 계산합니다.

    python3 style_pick.py --variant 2
        -> 같은 답으로 다른 조합을 뽑습니다(씨앗 끝에 #2를 붙입니다).

    python3 style_pick.py --out /어디에/style.json
        -> style.json 저장 위치를 지정합니다. (기본: 이 파일과 같은 폴더)
"""

import hashlib
import json
import os
import sys
import unicodedata

# ---------------------------------------------------------------------------
# 축 정의 — 5_챗지피티/명함_디자인표.md 및 card_index.html 과 값이 1:1로 같아야 합니다.
#          이 표를 고치면 세 곳을 함께 고치세요.
# ---------------------------------------------------------------------------

PALETTES = [
    # (키, 이름, 라이트 7색, 다크 7색)
    # 7색 순서: bg, surface, fg, muted, accent, accent-soft, line
    ("mukji", "먹지",
     ["#F6F5F2", "#FFFFFF", "#1C1C1A", "#6B6A66", "#2E2C28", "#E7E5DF", "#DCD9D2"],
     ["#141412", "#1D1D1A", "#F2F1ED", "#A3A199", "#D9D5CB", "#2A2A26", "#33322D"]),
    ("jjokbit", "쪽빛",
     ["#F4F6FA", "#FFFFFF", "#16203A", "#5E6A85", "#23407A", "#DCE4F3", "#D2DAE8"],
     ["#0F1420", "#171E2E", "#E8ECF6", "#98A3BC", "#7CA0E8", "#1D2740", "#2A3348"]),
    ("solip", "솔잎",
     ["#F4F7F3", "#FFFFFF", "#17251C", "#5C6B5F", "#2A5B3C", "#DDEADF", "#D2DFD4"],
     ["#0F1511", "#171F19", "#E9F0EA", "#96A79A", "#6FBF8B", "#1B2A20", "#29372C"]),
    ("hwangto", "황토",
     ["#FAF6EF", "#FFFFFF", "#2A2118", "#7A6A55", "#8A5A22", "#F1E3CE", "#E6DAC5"],
     ["#17130E", "#201A13", "#F5EEE2", "#B0A18B", "#D79A4E", "#2C2115", "#3A2E20"]),
    ("jasu", "자수정",
     ["#F8F5FA", "#FFFFFF", "#221A2C", "#6E6280", "#5B3E86", "#E9E0F3", "#DED4EA"],
     ["#14101A", "#1C1724", "#F0EAF6", "#A79BB8", "#A98CE0", "#241C30", "#322843"]),
    ("cheolhoe", "철회",
     ["#F3F4F5", "#FFFFFF", "#1A1D1F", "#656B70", "#3A4A55", "#E1E5E8", "#D6DADD"],
     ["#111315", "#191C1F", "#ECEEF0", "#9AA1A7", "#90A6B4", "#1F2429", "#2C3237"]),
    ("cheongrok", "청록",
     ["#F1F7F7", "#FFFFFF", "#12262A", "#566E72", "#146B72", "#D6EBEC", "#CBE0E1"],
     ["#0D1516", "#141E20", "#E6F1F2", "#93A9AC", "#56BEC4", "#16292B", "#24373A"]),
    ("jeokdong", "적동",
     ["#FAF4F2", "#FFFFFF", "#2B1A16", "#7A6058", "#99402C", "#F3DFD8", "#E8D3CB"],
     ["#17110F", "#201815", "#F6EBE7", "#B39A92", "#E08163", "#2C1C17", "#3B2823"]),
]

COLOR_VARS = ["--bg", "--surface", "--fg", "--muted", "--accent", "--accent-soft", "--line"]

LAYOUTS = [
    ("a", "세로 카드", "이름이 위, 소개·업무·연락이 아래로 차례로"),
    ("b", "좌측 색띠 사이드바", "넓은 화면에서 왼쪽 색 패널 + 오른쪽 내용"),
    ("c", "상단 밴드", "위쪽 전체가 색 띠, 그 안에 이름·직함"),
    ("d", "중앙 미니멀", "여백을 넉넉히 두고 전부 가운데 정렬"),
]

GOTHIC = ('-apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", '
          '"Malgun Gothic", "맑은 고딕", sans-serif')
MYEONGJO = '"AppleMyungjo", Batang, "바탕", Georgia, serif'

TYPES = [
    ("gothic", "고딕 단일", GOTHIC, GOTHIC),
    ("myeongjo", "명조 제목 + 고딕 본문", MYEONGJO, GOTHIC),
    ("bold", "굵은 제목 + 좁은 본문", GOTHIC, GOTHIC),
]

MOTIFS = [
    ("none", "없음", "장식 없음 (여백으로만 정리)"),
    ("rule", "얇은 이중선", "이름 아래 3px 이중선"),
    ("seal", "도장 자리 사각", "오른쪽 위 정사각 테두리 문양"),
    ("grid", "옅은 격자", "배경에 24px 격자"),
    ("slant", "사선 그라데이션", "카드 위쪽 사선 그라데이션"),
    ("band", "좌측 굵은 색띠", "카드 왼쪽 6px 색띠"),
]

SHAPES = [
    ("sharp", "직각 타이트", "0", "20px"),
    ("round", "라운드 넉넉", "18px", "32px"),
    ("soft", "라운드 타이트", "10px", "22px"),
]

STRENGTHS = [
    ("calm", "차분", "강조색을 선과 작은 글씨에만 씁니다"),
    ("mid", "보통", "직함과 연락 버튼에 강조색을 씁니다"),
    ("vivid", "선명", "이름 글자와 색띠에 강조색을 씁니다"),
]

QUESTIONS = [
    ("이름", "성함을 적어 주세요 (예: 홍길동)"),
    ("사무소명", "사무소명을 적어 주세요 (예: 행정사사무소청효)"),
    ("직함", "직함을 적어 주세요 (예: 행정사)"),
    ("연락수단", "명함에 넣을 연락 수단을 적어 주세요 (전화/이메일/링크/카카오 중 고른 것)"),
    ("느낌단어", "명함에서 주고 싶은 느낌 한 단어 (예: 단정한/든든한/밝은/전통적인/젊은)"),
]


# ---------------------------------------------------------------------------
# 계산
# ---------------------------------------------------------------------------

def make_seed(parts, variant=1):
    """다섯 조각을 이어 붙이고 정규화해서 씨앗 문자열을 만듭니다."""
    joined = "".join(parts)
    joined = unicodedata.normalize("NFC", joined)
    for ch in (" ", "\t", "　", "-", "‐", "‑", "‒", "–", "—"):
        joined = joined.replace(ch, "")
    if variant and int(variant) > 1:
        joined = "%s#%d" % (joined, int(variant))
    return joined


def pick(seed):
    """씨앗 -> 6개 축 번호. SHA-256 앞 6조각(2자리씩)의 나머지."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    chunks = [int(digest[i * 2:i * 2 + 2], 16) for i in range(6)]
    sizes = [len(PALETTES), len(LAYOUTS), len(TYPES), len(MOTIFS), len(SHAPES), len(STRENGTHS)]
    idx = [chunks[i] % sizes[i] for i in range(6)]
    return digest, chunks, idx


def build_result(parts, variant=1):
    seed = make_seed(parts, variant)
    digest, chunks, idx = pick(seed)

    pal = PALETTES[idx[0]]
    lay = LAYOUTS[idx[1]]
    typ = TYPES[idx[2]]
    mot = MOTIFS[idx[3]]
    shp = SHAPES[idx[4]]
    stg = STRENGTHS[idx[5]]

    body_attrs = (
        'data-palette="%s" data-layout="%s" data-type="%s" '
        'data-motif="%s" data-shape="%s" data-strength="%s"'
        % (pal[0], lay[0], typ[0], mot[0], shp[0], stg[0])
    )

    css_light = dict(zip(COLOR_VARS, pal[2]))
    css_dark = dict(zip(COLOR_VARS, pal[3]))
    css_common = {
        "--font-head": typ[2],
        "--font-body": typ[3],
        "--radius": shp[2],
        "--pad": shp[3],
    }

    return {
        "만든방법": "style_pick.py (SHA-256 정본 방식)",
        "씨앗": seed,
        "변형": int(variant),
        "해시앞12자리": digest[:12],
        "계산조각": chunks,
        "축": {
            "색조합": {"번호": idx[0], "키": pal[0], "이름": pal[1]},
            "배치": {"번호": idx[1], "키": lay[0], "이름": lay[1]},
            "글자조합": {"번호": idx[2], "키": typ[0], "이름": typ[1]},
            "장식모티프": {"번호": idx[3], "키": mot[0], "이름": mot[1]},
            "모서리여백": {"번호": idx[4], "키": shp[0], "이름": shp[1]},
            "강조강도": {"번호": idx[5], "키": stg[0], "이름": stg[1]},
        },
        "body속성": body_attrs,
        "css": {"라이트": css_light, "다크": css_dark, "공통": css_common},
    }


# ---------------------------------------------------------------------------
# 화면 출력
# ---------------------------------------------------------------------------

def print_summary(r):
    a = r["축"]
    print("")
    print("=" * 58)
    print(" 명함 디자인이 정해졌습니다")
    print("=" * 58)
    print(" 씨앗      : %s" % r["씨앗"])
    print(" 1 색 조합 : %s (%s)" % (a["색조합"]["이름"], a["색조합"]["키"]))
    print(" 2 배치    : %s (%s)" % (a["배치"]["이름"], a["배치"]["키"]))
    print(" 3 글자    : %s (%s)" % (a["글자조합"]["이름"], a["글자조합"]["키"]))
    print(" 4 장식    : %s (%s)" % (a["장식모티프"]["이름"], a["장식모티프"]["키"]))
    print(" 5 모서리  : %s (%s)" % (a["모서리여백"]["이름"], a["모서리여백"]["키"]))
    print(" 6 강조    : %s (%s)" % (a["강조강도"]["이름"], a["강조강도"]["키"]))
    print("-" * 58)
    print(" index.html 의 <body ...> 줄을 아래로 바꾸세요.")
    print("")
    print(" <body %s>" % r["body속성"])
    print("")


def main(argv):
    variant = 1
    out_path = None
    parts = []

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            print(__doc__)
            return 0
        if arg == "--variant":
            if i + 1 >= len(argv):
                print("오류: --variant 뒤에 숫자를 적어 주세요. 예) --variant 2")
                return 1
            try:
                variant = int(argv[i + 1])
            except ValueError:
                print("오류: --variant 값은 숫자여야 합니다. 예) --variant 2")
                return 1
            i += 2
            continue
        if arg == "--out":
            if i + 1 >= len(argv):
                print("오류: --out 뒤에 저장할 파일 경로를 적어 주세요.")
                return 1
            out_path = argv[i + 1]
            i += 2
            continue
        parts.append(arg)
        i += 1

    if len(parts) not in (0, 5):
        print("오류: 씨앗 조각은 5개여야 합니다 (이름 사무소명 직함 연락수단 느낌단어).")
        print("      %d개가 들어왔습니다. 값에 공백이 있으면 따옴표로 묶어 주세요." % len(parts))
        return 1

    if not parts:
        print("명함 디자인을 정하겠습니다. 다섯 가지만 알려주세요.")
        print("(그냥 Enter를 누르면 다음 질문으로 넘어갑니다)")
        for _, prompt in QUESTIONS:
            try:
                answer = input("  %s\n  > " % prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("\n중단했습니다.")
                return 1
            parts.append(answer)

    if not "".join(parts).strip():
        print("오류: 답이 모두 비어 있습니다. 최소한 성함은 적어 주세요.")
        return 1

    result = build_result(parts, variant)
    print_summary(result)

    if out_path is None:
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.json")

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        print(" ⚠️ style.json 을 저장하지 못했습니다: %s" % e)
        print("    위 <body ...> 줄만 복사해 쓰셔도 명함은 정상적으로 만들어집니다.")
        return 0

    print(" 기록을 저장했습니다: %s" % out_path)
    print(" (이 파일이 있으면 다음에 다시 계산하지 않아도 같은 디자인을 되살릴 수 있습니다)")
    print("")
    print(" 다른 조합을 보고 싶으시면:  python3 style_pick.py --variant 2")
    print(" 파이썬 없이 손으로 계산하려면: 5_챗지피티/명함_디자인표.md 3절 방법 2")
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
