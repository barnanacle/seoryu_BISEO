#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hwp2md — 한글 문서(.hwp / .hwpx)를 md(마크다운)로 변환합니다.

사용법:
    python hwp2md.py <파일 또는 폴더>
    python hwp2md.py <파일 또는 폴더> --force

동작:
  * rhwp 라는 한글 문서 해석 프로그램을 이용해 본문·표를 뽑아냅니다.
    - rhwp 위치: 이 스크립트 옆의 rhwp/ 폴더 (Mac은 rhwp, Windows는 rhwp.exe —
      자동으로 알맞은 쪽을 찾습니다)
  * 문서에 들어 있는 그림은 "<문서명>_img" 폴더에 꺼내 놓고 본문에 링크합니다.
  * 결과 .md 는 원본과 같은 위치에 같은 이름으로 만들어집니다.
    (원본 한글 파일은 절대 수정·삭제하지 않습니다.)
  * 이미 같은 이름의 .md 가 있으면 건너뜁니다. --force 를 붙이면 다시 변환합니다.

지원 형식:
  * .hwp  — 한글 5.0 형식 (그림 추출에 olefile 패키지 필요)
  * .hwpx — 개방형 한글 형식

PDF·워드·엑셀 등 다른 파일은 같은 폴더의 convert2md.py 를 사용하세요.
자세한 설명은 같은 폴더의 도구_사용법.md 를 보세요.
"""

import argparse
import os
import re
import subprocess
import sys
import zipfile
import zlib
from datetime import date
from pathlib import Path
from typing import Optional

try:
    import olefile  # .hwp(OLE2) 그림 추출에만 필요 — 없어도 본문 변환은 됩니다
except ImportError:
    olefile = None

SCRIPT_DIR = Path(__file__).resolve().parent
RHWP_DIR = SCRIPT_DIR / "rhwp"
REEXEC_GUARD = "HWP2MD_REEXEC"  # venv 재실행 무한 반복 방지용


# ============================================================
# 0. 실행 환경 준비 (한글 출력·venv·rhwp 찾기)
# ============================================================

def _setup_console() -> None:
    """Windows 명령 프롬프트에서도 한글이 깨지지 않도록 출력 인코딩을 맞춘다."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _packet_tool_dirs() -> list:
    """스크립트 옆 도구_경로.md에 기록된 추가 도구 위치를 읽는다.
    운영 폴더 밖에 별도 변환 환경을 둔 경우에만 쓰는 선택 기능이다."""
    dirs = []
    memo = SCRIPT_DIR / "도구_경로.md"
    if memo.exists():
        try:
            for line in memo.read_text(encoding="utf-8").splitlines():
                line = line.strip().strip("`").rstrip("/\\")
                if line.startswith("/") or (len(line) > 2 and line[1] == ":"):
                    dirs.append(Path(line))
                    break
        except OSError:
            pass
    return dirs


def _find_venv_python() -> Optional[Path]:
    """스크립트 옆 venv/ 안의 파이썬을 찾는다 (Mac/Windows 모두)."""
    for base in [SCRIPT_DIR, *_packet_tool_dirs()]:
        venv = base / "venv"
        for rel in ("bin/python3", "bin/python", "Scripts/python.exe", "Scripts/python"):
            cand = venv / rel
            if cand.exists():
                return cand
    return None


def _maybe_reexec_into_venv() -> None:
    """olefile 이 없고 옆에 venv/ 가 있으면, venv 파이썬으로 자신을 다시 실행한다."""
    if olefile is not None:
        return
    venv_py = _find_venv_python()
    if venv_py is None or os.environ.get(REEXEC_GUARD) == "1":
        return
    env = dict(os.environ)
    env[REEXEC_GUARD] = "1"
    raise SystemExit(
        subprocess.call(
            [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]],
            env=env,
        )
    )


def find_rhwp(explicit: Optional[Path] = None) -> Optional[Path]:
    """rhwp 실행 파일을 찾는다. Mac=rhwp, Windows=rhwp.exe 자동 판별."""
    if explicit is not None:
        return explicit if explicit.exists() else None
    names = ["rhwp.exe", "rhwp"] if os.name == "nt" else ["rhwp", "rhwp.exe"]
    search_dirs = [RHWP_DIR, RHWP_DIR / "target" / "release"]  # 직접 빌드한 경우 대비
    for base in _packet_tool_dirs():
        search_dirs.append(base / "rhwp")
    # 압축이 한 겹 폴더째 풀린 경우(rhwp/rhwp-v0.7.17-.../rhwp.exe) 1단계 하위도 탐색
    for d in list(search_dirs):
        if d.is_dir():
            search_dirs.extend(sub for sub in sorted(d.iterdir()) if sub.is_dir())
    for d in search_dirs:
        for n in names:
            cand = d / n
            if cand.is_file():
                # 실행 권한이 빠져 있으면 스스로 복구 시도 (압축 해제 과정에서 흔히 빠짐)
                if os.name != "nt" and not os.access(cand, os.X_OK):
                    try:
                        cand.chmod(cand.stat().st_mode | 0o755)
                    except OSError:
                        pass
                return cand
    return None


def _rhwp_missing_exit() -> None:
    print("❌ 한글 해석 프로그램(rhwp)을 찾을 수 없습니다.", file=sys.stderr)
    print(f"   찾아본 위치: {RHWP_DIR} (Mac은 rhwp, Windows는 rhwp.exe)", file=sys.stderr)
    print("   AI에게 \"tools의 HWP·HWPX 변환 환경을 준비해줘\"라고 요청하세요.", file=sys.stderr)
    print("   또는 https://github.com/edwardkim/rhwp/releases 에서 v0.7.17 을"
          " 내려받아 압축을 풀고, 실행 파일을 위 rhwp/ 폴더에 넣어 주세요.", file=sys.stderr)
    print("   더 자세한 도움말: tools/안내_파일변환.md", file=sys.stderr)
    sys.exit(2)


def _run_rhwp(rhwp: Path, cmd: str, target: Path) -> str:
    """rhwp 를 실행하고 UTF-8 텍스트로 결과를 받는다 (Windows 한글 깨짐 방지)."""
    try:
        return subprocess.check_output(
            [str(rhwp), cmd, str(target)],
            encoding="utf-8",
            errors="replace",
        )
    except PermissionError:
        print(f"❌ rhwp 를 실행할 권한이 없습니다: {rhwp}", file=sys.stderr)
        print("   Mac이라면 AI에게 이렇게 말해 주세요:"
              " \"tools/rhwp 실행 파일에 실행 권한을 줘\"", file=sys.stderr)
        sys.exit(2)


# ============================================================
# 1. rhwp info -> 문서 정보(frontmatter)
# ============================================================

INFO_FIELD_RE = re.compile(
    r"^(파일|크기|버전|압축|암호화|배포용|구역 수|페이지 수|총 문단 수): (.+)$"
)
TABLE_LINE_RE = re.compile(r"^표\d+ \[")
SHAPE_LINE_RE = re.compile(r"^그림\d+ \[")
BINDATA_LINE_RE = re.compile(
    r"^\s*\[(\d+)\] Embedding \(ID: (\d+), ext: (\w+), loaded: (\d+) bytes\)"
)
FONT_LINE_RE = re.compile(r"^폰트\(([^)]+)\): (.+)$")


def run_info(rhwp: Path, hwp: Path) -> dict:
    out = _run_rhwp(rhwp, "info", hwp)
    info: dict = {"raw": out, "fonts": {}, "bindata": []}
    for line in out.splitlines():
        if m := INFO_FIELD_RE.match(line.strip()):
            info[m.group(1)] = m.group(2).strip()
        elif m := FONT_LINE_RE.match(line.strip()):
            info["fonts"][m.group(1)] = [s.strip() for s in m.group(2).split(",")]
        elif m := BINDATA_LINE_RE.match(line):
            info["bindata"].append(
                {
                    "id": int(m.group(2)),
                    "ext": m.group(3).lower(),
                    "size": int(m.group(4)),
                }
            )
    info["tables"] = sum(1 for ln in out.splitlines() if TABLE_LINE_RE.match(ln))
    info["images"] = sum(1 for ln in out.splitlines() if SHAPE_LINE_RE.match(ln))
    return info


def make_frontmatter(hwp: Path, info: dict, image_count: int) -> str:
    title = hwp.stem
    pages = info.get("페이지 수", "?")
    paragraphs = info.get("총 문단 수", "?")
    version = info.get("버전", "?")
    return (
        "---\n"
        "tags: [HWP, 변환문서]\n"
        f"date: {date.today().isoformat()}\n"
        "source: HWP 변환 (rhwp + hwp2md)\n"
        f"original_file: {hwp.name}\n"
        f"title: {title}\n"
        f"hwp_version: {version}\n"
        f"pages: {pages}\n"
        f"paragraphs: {paragraphs}\n"
        f"tables: {info.get('tables', 0)}\n"
        f"images: {image_count}\n"
        "---\n\n"
    )


# ============================================================
# 2. rhwp dump -> 문단 구조 해석
# ============================================================

# 문단 머리줄 예시:
#   --- 문단 0.5 --- cc=12, text_len=10, controls=0 [쪽나누기]
PARA_HEADER_RE = re.compile(
    r"^--- 문단 (\d+)\.(\d+) --- cc=\d+, text_len=(\d+), controls=\d+\s*(.*)$"
)
TEXT_RE = re.compile(r'^  텍스트: "((?:[^"\\]|\\.)*)"')
TABLE_HEADER_RE = re.compile(r"^\s*\[(\d+)\] 표: (\d+)행×(\d+)열")
CELL_RE = re.compile(
    r'^\s*\[\d+\]\s+셀\[(\d+)\]\s+r=(\d+),c=(\d+)\s+rs=(\d+),cs=(\d+).*?\s+text="((?:[^"\\]|\\.)*)"'
)
SHAPE_RE = re.compile(
    r"^\s*\[(\d+)\] 그림: bin_id=(\d+),\s*common=(\d+)×(\d+)"
)
PAGEBREAK_TAG = "[쪽나누기]"
SECTION_RE = re.compile(r"^=== 구역 (\d+) ===")


def run_dump(rhwp: Path, hwp: Path) -> str:
    return _run_rhwp(rhwp, "dump", hwp)


def parse_paragraphs(dump: str) -> list[dict]:
    """dump 출력을 문단 단위 dict 목록으로 나눈다.

    각 문단: section, idx, text, has_pagebreak, tables, images.
    """
    paragraphs: list[dict] = []
    cur: Optional[dict] = None
    cur_section = 0

    for raw in dump.splitlines():
        if m := SECTION_RE.match(raw):
            cur_section = int(m.group(1))
            continue

        if m := PARA_HEADER_RE.match(raw):
            if cur is not None:
                paragraphs.append(cur)
            cur = {
                "section": cur_section,
                "idx": int(m.group(2)),
                "text_len": int(m.group(3)),
                "has_pagebreak": PAGEBREAK_TAG in (m.group(4) or ""),
                "text": "",
                "tables": [],
                "images": [],
            }
            continue

        if cur is None:
            continue

        if m := TEXT_RE.match(raw):
            txt = m.group(1)
            if txt.strip() and txt != "(빈 문단)":
                cur["text"] = txt
        elif m := TABLE_HEADER_RE.match(raw):
            cur["tables"].append(
                {
                    "rows": int(m.group(2)),
                    "cols": int(m.group(3)),
                    "cells": [],
                }
            )
        elif m := CELL_RE.match(raw):
            if cur["tables"]:
                cur["tables"][-1]["cells"].append(
                    {
                        "r": int(m.group(2)),
                        "c": int(m.group(3)),
                        "rs": int(m.group(4)),
                        "cs": int(m.group(5)),
                        "text": m.group(6).strip(),
                    }
                )
        elif m := SHAPE_RE.match(raw):
            cur["images"].append(
                {"bin_id": int(m.group(2)), "w": int(m.group(3)), "h": int(m.group(4))}
            )

    if cur is not None:
        paragraphs.append(cur)
    return paragraphs


# ============================================================
# 3. 마크다운 만들기
# ============================================================

def render_table(tbl: dict) -> str:
    """해석된 표를 마크다운 표로 그린다. (칸 합치기는 마크다운이 지원하지 않아
    합쳐진 칸은 첫 칸에만 내용이 들어가고 나머지는 빈 칸이 됩니다.)"""
    rows = tbl["rows"]
    cols = tbl["cols"]
    cells = tbl["cells"]

    if not cells:
        return ""

    grid: dict[tuple[int, int], str] = {}
    for cell in cells:
        grid[(cell["r"], cell["c"])] = cell["text"]

    lines: list[str] = []

    # 1×1 표는 표 대신 인용 블록으로
    if rows == 1 and cols == 1:
        text = cells[0]["text"]
        if not text:
            return ""
        if re.match(r"^[QⅠⅡⅢⅣIVX0-9.]", text):
            return f"\n### {text}\n"
        return f"\n> {text}\n"

    header = [grid.get((0, c), "").replace("\n", "<br>") or " " for c in range(cols)]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * cols) + "|")
    for r in range(1, rows):
        row = [grid.get((r, c), "").replace("\n", "<br>") or " " for c in range(cols)]
        lines.append("| " + " | ".join(row) + " |")

    return "\n" + "\n".join(lines) + "\n"


def render_image(img: dict, image_links: dict[int, str]) -> str:
    bin_id = img["bin_id"]
    link = image_links.get(bin_id)
    # 7200 HWPUNIT == 1인치 == 25.4mm
    mm_w = round(img["w"] * 25.4 / 7200, 1)
    mm_h = round(img["h"] * 25.4 / 7200, 1)
    alt = f"그림 (bin_id={bin_id}, {mm_w}×{mm_h}mm)"
    if link:
        return f"\n![{alt}]({link})\n"
    return f"\n*[{alt} — 이미지 추출 실패 또는 미지원]*\n"


def render_markdown(paragraphs: list[dict], image_links: dict[int, str]) -> str:
    blocks: list[str] = []
    for p in paragraphs:
        for img in p["images"]:
            blocks.append(render_image(img, image_links))
        for tbl in p["tables"]:
            blocks.append(render_table(tbl))
        if p["text"]:
            blocks.append(p["text"].rstrip())
        if p["has_pagebreak"]:
            blocks.append("\n---\n")
    return "\n\n".join(b for b in blocks if b.strip())


# ============================================================
# 4. 그림(BinData) 추출 — HWP(OLE2)·HWPX(ZIP) 모두 지원
# ============================================================

BIN_NAME_RE = re.compile(r"^BIN([0-9A-Fa-f]+)\.(\w+)$")
HWPX_BIN_NAME_RE = re.compile(
    r"BinData/(?:image|bin)?(\d+)\.([A-Za-z0-9]+)$", re.IGNORECASE
)


def extract_bindata(hwp: Path, out_dir: Path) -> dict[int, Path]:
    """HWP 5.0(OLE2) 또는 HWPX(ZIP)에서 그림을 꺼낸다. {bin_id: 저장 경로} 반환."""
    if zipfile.is_zipfile(str(hwp)):
        return _extract_bindata_hwpx(hwp, out_dir)
    if olefile is not None and olefile.isOleFile(str(hwp)):
        return _extract_bindata_ole(hwp, out_dir)
    if olefile is None and hwp.suffix.lower() == ".hwp":
        print("⚠️  olefile 패키지가 없어 .hwp 문서의 그림 추출을 건너뜁니다."
              " (본문·표 변환은 정상 진행)")
        print("    그림까지 필요하면 AI에게 \"olefile을 설치해줘"
              " (pip install olefile)\"라고 말해 주세요.")
    return {}


def _extract_bindata_hwpx(hwp: Path, out_dir: Path) -> dict[int, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[int, Path] = {}
    with zipfile.ZipFile(str(hwp)) as zf:
        members = [n for n in zf.namelist() if n.startswith("BinData/")]
        # 파일 이름에 번호가 없으면 나열 순서를 번호로 사용
        for fallback_id, name in enumerate(sorted(members), start=1):
            if name.endswith("/"):
                continue
            m = HWPX_BIN_NAME_RE.search(name)
            if m:
                bin_id = int(m.group(1))
                ext = m.group(2).lower()
            else:
                bin_id = fallback_id
                ext = Path(name).suffix.lstrip(".").lower() or "bin"
            data = zf.read(name)
            out_path = out_dir / f"bin{bin_id:04d}.{ext}"
            out_path.write_bytes(data)
            result[bin_id] = out_path
    return result


def _extract_bindata_ole(hwp: Path, out_dir: Path) -> dict[int, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[int, Path] = {}

    ole = olefile.OleFileIO(str(hwp))
    try:
        for stream_path in ole.listdir():
            if len(stream_path) < 2 or stream_path[0] != "BinData":
                continue
            name = stream_path[-1]
            m = BIN_NAME_RE.match(name)
            if not m:
                continue
            bin_id = int(m.group(1), 16)
            ext = m.group(2).lower()
            raw = ole.openstream(stream_path).read()

            data = raw
            # HWP 5.0 BinData 는 보통 raw deflate 로 압축되어 있음
            try:
                data = zlib.decompress(raw, -15)
            except zlib.error:
                try:
                    data = zlib.decompress(raw)
                except zlib.error:
                    data = raw  # 압축 안 된 경우

            # 그림 파일 서명 확인 (JPG/PNG)
            if ext in ("jpg", "jpeg") and not data.startswith(b"\xff\xd8"):
                if raw.startswith(b"\xff\xd8"):
                    data = raw
            elif ext == "png" and not data.startswith(b"\x89PNG"):
                if raw.startswith(b"\x89PNG"):
                    data = raw

            out_path = out_dir / f"bin{bin_id:04d}.{ext}"
            out_path.write_bytes(data)
            result[bin_id] = out_path
    finally:
        ole.close()

    return result


# ============================================================
# 5. 이미지 폴더·링크
# ============================================================

def image_dirname(out_path: Path) -> str:
    """결과 md 이름을 따서 그림 폴더 이름을 만든다: <문서명>_img"""
    stem = re.sub(r'[<>:"/\\|?*]', "_", out_path.stem).strip().rstrip(".")
    return (stem or "문서")[:80] + "_img"


def build_image_links(dir_name: str, local_paths: dict[int, Path]) -> dict[int, str]:
    """같은 폴더 기준 상대 경로 링크를 만든다 (공백은 %20 으로)."""
    links: dict[int, str] = {}
    for bin_id, p in local_paths.items():
        links[bin_id] = f"./{dir_name}/{p.name}".replace(" ", "%20")
    return links


# ============================================================
# 6. 변환 실행
# ============================================================

def convert(rhwp: Path, src: Path, output: Optional[Path], force: bool) -> str:
    """파일 1개 변환. 결과: 'ok' | 'skip'  (실패 시 예외)"""
    out_path = output if output is not None else src.with_suffix(".md")
    if out_path.exists() and not force:
        print(f"⏭️  건너뜀(이미 .md 있음): {src.name}")
        return "skip"

    print(f"\n📄 변환 시작: {src.name}")

    print("  [1/4] 문서 정보 확인...")
    try:
        info = run_info(rhwp, src)
    except subprocess.CalledProcessError:
        # info 가 실패해도 본문 변환은 시도한다
        info = {"fonts": {}, "bindata": [], "tables": 0, "images": 0}
        print("      (문서 정보를 읽지 못했습니다 — 본문 변환은 계속 시도합니다)")

    print("  [2/4] 본문·표 추출...")
    try:
        dump = run_dump(rhwp, src)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            "한글 문서를 해석하지 못했습니다."
            " 암호가 걸려 있거나 배포용(편집 제한) 문서일 수 있습니다."
            f" (rhwp 오류 코드 {e.returncode})"
        ) from e
    paragraphs = parse_paragraphs(dump)

    print("  [3/4] 그림 추출...")
    img_dir = out_path.parent / image_dirname(out_path)
    try:
        local_imgs = extract_bindata(src, img_dir)
    except Exception as e:
        local_imgs = {}
        print(f"      ⚠️ 그림 추출 실패({type(e).__name__}) — 본문만 변환합니다.")
    if not local_imgs and img_dir.exists():
        try:
            img_dir.rmdir()  # 빈 폴더면 정리
        except OSError:
            pass
    image_links = build_image_links(img_dir.name, local_imgs)

    print("  [4/4] 마크다운 저장...")
    body = render_markdown(paragraphs, image_links)
    md = make_frontmatter(src, info, len(local_imgs)) + body + "\n"
    out_path.write_text(md, encoding="utf-8")

    table_count = sum(len(p["tables"]) for p in paragraphs)
    print(f"✅ 완료: {out_path}")
    tail = f"   문단 {len(paragraphs)}개 · 표 {table_count}개 · 그림 {len(local_imgs)}개"
    if local_imgs:
        tail += f"  (그림 폴더: {img_dir.name}/)"
    print(tail)
    return "ok"


def iter_targets(root: Path):
    """폴더면 하위 폴더까지 뒤져 .hwp/.hwpx 파일을 차례로 낸다."""
    if root.is_file():
        yield root
        return
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".hwp", ".hwpx"):
            continue
        if p.name.startswith((".", "~$")):
            continue
        if any(part.startswith(".") for part in p.relative_to(root).parts[:-1]):
            continue
        yield p


def main() -> None:
    _setup_console()
    _maybe_reexec_into_venv()

    parser = argparse.ArgumentParser(
        prog="hwp2md",
        description="한글 문서(.hwp/.hwpx)를 md(마크다운)로 변환합니다.",
        epilog="예시:  python hwp2md.py ../DATA          (DATA 폴더의 한글 문서 일괄 변환)\n"
               "       python hwp2md.py 의견서.hwp        (파일 1개 변환)\n"
               "PDF·워드·엑셀 등은 convert2md.py 를 사용하세요.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("inputs", nargs="+", metavar="<파일 또는 폴더>",
                        help="변환할 한글 문서 또는 폴더")
    parser.add_argument("-o", "--output", type=Path,
                        help="결과 md 저장 경로 (파일 1개 변환 시에만)")
    parser.add_argument("--force", action="store_true",
                        help="이미 .md 가 있어도 다시 변환합니다")
    parser.add_argument("--rhwp", type=Path,
                        help="rhwp 실행 파일 위치를 직접 지정 (보통 필요 없음)")
    args = parser.parse_args()

    rhwp = find_rhwp(args.rhwp)
    if rhwp is None:
        _rhwp_missing_exit()

    if args.output and (len(args.inputs) > 1 or not Path(args.inputs[0]).is_file()):
        print("❌ -o/--output 은 파일 1개를 변환할 때만 쓸 수 있습니다.", file=sys.stderr)
        sys.exit(2)

    counts = {"ok": 0, "skip": 0, "fail": 0, "other": 0}

    for raw in args.inputs:
        root = Path(raw).expanduser()

        if not root.exists():
            print(f"❌ 찾을 수 없습니다: {root}")
            print("   경로(파일 위치)에 오타가 없는지 확인해 주세요.")
            counts["fail"] += 1
            continue

        if root.is_file() and root.suffix.lower() not in (".hwp", ".hwpx"):
            print(f"❌ 이 도구는 한글 문서(.hwp/.hwpx) 전용입니다: {root.name}")
            print("   PDF·워드·엑셀·이미지는 convert2md.py 를 사용하세요.")
            counts["other"] += 1
            continue

        found_any = False
        for f in iter_targets(root):
            found_any = True
            try:
                counts[convert(rhwp, f, args.output, args.force)] += 1
            except Exception as e:  # 한 파일이 실패해도 나머지는 계속 변환
                counts["fail"] += 1
                print(f"❌ 변환 실패: {f.name}")
                print(f"   이유: {e}")
                print("   → 파일이 한글 프로그램에서 열려 있으면 닫고 다시 시도해 주세요."
                      " 계속 실패하면 tools/안내_파일변환.md 를 참고하세요.")

        if root.is_dir() and not found_any:
            print(f"ℹ️  이 폴더에는 한글 문서(.hwp/.hwpx)가 없습니다: {root}")

    print("\n===== 변환 결과 =====")
    line = f"성공 {counts['ok']}건 · 건너뜀 {counts['skip']}건 · 실패 {counts['fail']}건"
    if counts["other"]:
        line += f" · 다른 형식 안내 {counts['other']}건"
    print(line)
    if counts["ok"]:
        print("성공한 파일은 원본 옆에 같은 이름의 .md 로 저장되었습니다."
              " 이 화면이 보이면 성공입니다.")

    sys.exit(1 if counts["fail"] else 0)


if __name__ == "__main__":
    main()
