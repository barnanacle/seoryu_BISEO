#!/usr/bin/env python3
"""INFERRED 교차참조 후보 리포트 — JARVIS 정본 (헌법 모드 3 Step 2.5 폐루프).

graph.json의 INFERRED 엣지 중 '이미 [[상호 링크]]된 페이지쌍'을 제외한
진짜 미연결 후보만 confidence 순으로 출력한다 (실측: 미필터 시 48%가 헛후보).

사용: python3 report_inferred.py [graph.json 경로] [--top N]
출력: graphify-out/INFERRED_CANDIDATES.md (검진 Step 2 「연결 기회 탐지」 입력)
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

def _wiki_root(graph_path: Path) -> Path:
    """graph.json 옆의 .graphify_root(빌드 대상 폴더 기록)에서 위키 경로를 읽는다."""
    marker = graph_path.parent / ".graphify_root"
    if marker.exists():
        return Path(marker.read_text(encoding="utf-8").strip())
    return Path.cwd() / "wiki"


WIKI = None  # main()에서 graph 경로 기준으로 결정


def nfc(s):
    return unicodedata.normalize("NFC", str(s or ""))


def page_stem(source_file):
    if not source_file:
        return None
    return nfc(Path(source_file).stem)


def main():
    global WIKI
    gp = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("graphify-out/graph.json")
    WIKI = _wiki_root(gp)
    top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 20
    g = json.loads(gp.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in g.get("nodes", [])}

    # 위키 원문 링크 셋 (페이지 → outbound [[링크]] 스템들)
    links = {}
    for p in WIKI.glob("*.md"):
        body = p.read_text(encoding="utf-8", errors="ignore")
        links[nfc(p.stem)] = {nfc(m) for m in re.findall(r"\[\[([^\]|#]+)", body)}

    cands, dropped = [], 0
    for e in g.get("links", []):
        if e.get("confidence") != "INFERRED":
            continue
        s, t = nodes.get(e.get("source"), {}), nodes.get(e.get("target"), {})
        ps, pt = page_stem(s.get("source_file")), page_stem(t.get("source_file"))
        if not ps or not pt or ps == pt:
            continue
        # 페이지 레벨 상호링크 존재 → 헛후보 제외
        if pt in links.get(ps, set()) or ps in links.get(pt, set()):
            dropped += 1
            continue
        cands.append(
            (e.get("confidence_score", 0), ps, pt, s.get("label"), t.get("label"), e.get("relation"))
        )

    cands.sort(reverse=True)
    out = ["# INFERRED 교차참조 후보 (페이지 레벨 dedup 적용)", ""]
    out.append(f"- 원 INFERRED 중 이미 상호링크된 쌍 제외: {dropped}건")
    out.append(f"- 잔여 후보: {len(cands)}건 (상위 {min(top, len(cands))} 표시)\n")
    for sc, ps, pt, ls, lt, rel in cands[:top]:
        out.append(f"- [{sc:.2f}] [[{ps}]] ↔ [[{pt}]] — {ls} ~ {lt} ({rel})")
    rp = gp.parent / "INFERRED_CANDIDATES.md"
    rp.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"후보 {len(cands)}건 (헛후보 {dropped} 제외) → {rp}")


if __name__ == "__main__":
    main()
