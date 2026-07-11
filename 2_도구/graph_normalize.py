#!/usr/bin/env python3
"""graphify 추출본 정규화 패스 — JARVIS 정본 (헌법 모드 3 Step 2.5).

한글 라벨 음역 비결정성(시행규칙→sihaeng/siheong)·prefix 불일치(wiki_/_)·
타 페이지 내 언급 중복으로 생기는 라벨 중복 노드를 결정적으로 병합한다.

병합 키(2026-07-12 v2 보강): NFC 정규화 + lower + 공백/언더스코어/·(가운뎃점)/하이픈 제거.
대표 노드 선정: ① file_type=document ② id가 wiki_ prefix ③ 긴 id 순.
가드: source_file이 서로 다른 document 노드끼리는 병합하지 않는다(실페이지 별개 보존).

사용: rebuild·--update 공용 — build 직전 추출 JSON(.graphify_extract.json)에 적용.
  python3 normalize.py <extract.json>   # in-place 정규화
"""
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

_STRIP = re.compile(r"[\s_·\-‧ㆍ]+")


def norm_key(label: str) -> str:
    s = unicodedata.normalize("NFC", str(label or "")).lower()
    return _STRIP.sub("", s)


def normalize(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    hyper = data.get("hyperedges", [])

    # 1) 라벨 키 그룹핑
    groups = defaultdict(list)
    for n in nodes:
        groups[norm_key(n.get("label", n.get("id", "")))].append(n)

    # 2) 그룹별 대표 선정 + 리매핑 테이블
    remap = {}
    kept = []
    merged_cnt = 0
    for key, grp in groups.items():
        if len(grp) == 1:
            kept.append(grp[0])
            continue
        # self-doc = 그 페이지 '자신'의 document 노드 (source_file 스템의 키 == 그룹 키).
        # 참조 기록용 stub document(source_file이 참조하는 쪽 파일)는 자유 병합 대상.
        def is_self_doc(n):
            sf = n.get("source_file") or ""
            return (
                n.get("file_type") == "document"
                and norm_key(Path(sf).stem) == key
            )

        self_docs = [n for n in grp if is_self_doc(n)]
        # 가드: 서로 다른 실페이지의 self-doc끼리는 병합 금지 (별개 페이지 보존)
        if len({n.get("source_file") for n in self_docs}) > 1:
            kept.extend(grp)
            continue

        def rank(n):
            return (
                is_self_doc(n),
                n.get("file_type") == "document",
                str(n.get("id", "")).startswith("wiki_"),
                len(str(n.get("id", ""))),
            )

        rep = max(grp, key=rank)
        kept.append(rep)
        for n in grp:
            if n is not rep:
                remap[n["id"]] = rep["id"]
                merged_cnt += 1

    # 3) 엣지 리매핑 → self-loop 제거 → (s,t,relation) dedup (EXTRACTED·고신뢰 우선)
    def rid(x):
        return remap.get(x, x)

    best = {}
    for e in edges:
        s, t = rid(e.get("source")), rid(e.get("target"))
        if s == t:
            continue
        e = {**e, "source": s, "target": t}
        k = (s, t, e.get("relation"))
        cur = best.get(k)

        def score(x):
            return (x.get("confidence") == "EXTRACTED", x.get("confidence_score", 0))

        if cur is None or score(e) > score(cur):
            best[k] = e
    new_edges = list(best.values())

    # 4) 하이퍼엣지 노드 리매핑 (중복 제거, 2노드 미만이면 폐기)
    new_hyper = []
    for h in hyper:
        ns = list(dict.fromkeys(rid(x) for x in h.get("nodes", [])))
        if len(ns) >= 3:
            new_hyper.append({**h, "nodes": ns})

    # 5) 잔존 라벨 중복 검사 (가드 예외 제외)
    lab = defaultdict(int)
    for n in kept:
        lab[norm_key(n.get("label", ""))] += 1
    dup_after = {k: v for k, v in lab.items() if v > 1}

    data["nodes"], data["edges"], data["hyperedges"] = kept, new_edges, new_hyper
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return {
        "nodes_before": len(nodes),
        "nodes_after": len(kept),
        "merged": merged_cnt,
        "edges_before": len(edges),
        "edges_after": len(new_edges),
        "dup_after_guarded": len(dup_after),
    }


if __name__ == "__main__":
    p = Path(sys.argv[1] if len(sys.argv) > 1 else "graphify-out/.graphify_extract.json")
    r = normalize(p)
    print(
        f"정규화: 노드 {r['nodes_before']}→{r['nodes_after']} (병합 {r['merged']}) · "
        f"엣지 {r['edges_before']}→{r['edges_after']} · 잔존중복(가드예외) {r['dup_after_guarded']}"
    )
