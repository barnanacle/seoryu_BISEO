#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""개인정보 자동 점검 (pii_check.py)

`wiki/` 와 `memory/` 에 의뢰인 이름·번호·금액이 남아 있지 않은지 **기계로** 훑어봅니다.
AI의 자기점검(헌법 「안전 1」)이 조용히 건너뛰어질 때를 대비한 **마지막 그물**입니다.

사용법
    python3 tools/pii_check.py              # 이 파일이 있는 폴더의 상위 폴더 = 지식창고
    python3 tools/pii_check.py ~/JARVIS     # 지식창고 위치를 직접 지정
    python3 tools/pii_check.py --no-name-guess   # 사람 이름 추정만 끄기

이 프로그램이 스스로 지키는 것
    1. **어떤 파일도 만들거나 고치지 않습니다.** 화면에 목록만 보여줍니다.
    2. 읽는 곳은 `wiki/` 와 `memory/` 의 텍스트 파일뿐입니다.
    3. 절대 열지 않는 곳: `2_서류철/`(의뢰인 실명 자료) · `3_작업실/` · `1_자료실/`.
       — 2_서류철은 실명을 적어도 되는 유일한 곳이라 점검 대상이 아닙니다.
    4. 인터넷에 접속하지 않습니다. 판정 규칙은 `make_dashboard.py` 의 것을 그대로 씁니다
       (규칙이 한 곳에만 있어야 두 프로그램의 결과가 어긋나지 않습니다).

⚠️ 걸리는 것이 없다고 해서 "안전하다"는 뜻은 아닙니다. 규칙에 없는 형태는 지나갑니다.
   마지막 방어선은 언제나 사람이 한 번 눈으로 보는 것입니다.

파이썬 3.9 이상 · 표준 라이브러리만 사용.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from make_dashboard import Masker, nfc, read_text, say
except ImportError:  # 같은 폴더에 make_dashboard.py 가 없을 때
    print("❌ 같은 tools 폴더 안의 make_dashboard.py 를 찾지 못했습니다.")
    print("   두 파일은 함께 있어야 합니다(판정 규칙을 나눠 쓰기 때문입니다).")
    print("   AI에게 「JARVIS 운영 꾸러미의 tools를 점검하고 빠진 파일을 복구해줘」라고 말씀하세요.")
    sys.exit(1)

SCAN_DIRS = ["wiki", "memory"]          # 여기만 훑습니다
NEVER = {"2_서류철", "3_작업실", "1_자료실"}   # 이름만 봐도 열지 않습니다
TEXT_EXT = {".md", ".txt", ".tsv", ".csv"}
MAX_SHOW = 200                           # 화면에 보여줄 최대 줄 수


def iter_files(root):
    for top in SCAN_DIRS:
        base = os.path.join(root, top)
        if not os.path.isdir(base):
            continue
        for cur, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in NEVER and not d.startswith(".")]
            for fn in sorted(files):
                if os.path.splitext(fn)[1].lower() not in TEXT_EXT:
                    continue
                yield os.path.join(cur, fn)


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    args = [a for a in argv[1:] if not a.startswith("--")]
    guess_names = "--no-name-guess" not in argv

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.expanduser(args[0])) if args else os.path.dirname(here)

    if not os.path.isdir(os.path.join(root, "wiki")):
        say("❌ 여기가 지식창고가 맞는지 확인해 주세요 — wiki 폴더가 없습니다: " + root)
        say("   python3 tools/pii_check.py <지식창고 경로> 처럼 위치를 알려 주세요.")
        return 1

    hits = []
    scanned = 0
    for path in iter_files(root):
        body = read_text(path)
        if body is None:
            continue
        scanned += 1
        rel = nfc(os.path.relpath(path, root)).replace("\\", "/")
        for n, line in enumerate(body.splitlines(), start=1):
            if not line.strip():
                continue
            probe = Masker(guess_names=guess_names)
            masked = probe(line)
            if probe.total:
                text = line.strip()
                if len(text) > 90:
                    text = text[:90] + "…"
                hits.append((rel, n, ", ".join(probe.kinds), masked.strip()[:90]))

    say("🔎 개인정보 자동 점검 — wiki/ · memory/ 의 텍스트 파일 " + str(scanned) + "개를 훑었습니다.")
    say("   (2_서류철/ · 3_작업실/ · 1_자료실/ 는 열지 않습니다)")
    say("")

    if not hits:
        say("✅ 규칙에 걸리는 줄이 없습니다.")
        say("   ⚠️ 다만 규칙에 없는 형태는 지나갑니다 — 새로 만든 페이지는 눈으로도 한 번 봐 주세요.")
        return 0

    say("⚠️ 확인이 필요한 줄 " + str(len(hits)) + "건입니다. (아래는 가린 상태로 보여 드립니다)")
    say("")
    for rel, n, kinds, masked in hits[:MAX_SHOW]:
        say("  " + rel + ":" + str(n) + ": " + kinds)
        say("      " + masked)
    if len(hits) > MAX_SHOW:
        say("  … 그 밖에 " + str(len(hits) - MAX_SHOW) + "건 더 있습니다.")
    say("")
    say("👉 할 일: 위 줄을 열어 이름·번호·금액을 지우거나, 그 내용이 사건 사실이라면 2_서류철/로 옮기세요.")
    say("   AI에게 「pii_check 결과를 보고 wiki에 남은 개인정보를 익명화해줘」라고 말씀하셔도 됩니다.")
    say("   이름이 아닌 낱말이 걸렸다면 그냥 두셔도 됩니다(추정 규칙이라 넉넉하게 잡습니다).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
