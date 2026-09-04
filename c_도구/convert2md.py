#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert2md — PDF·워드(DOCX)·엑셀(XLSX)·파워포인트(PPTX)·이미지 파일을
md(마크다운)로 변환합니다.

사용법:
    python convert2md.py <파일 또는 폴더>
    python convert2md.py <파일 또는 폴더> --force

동작:
  * 파일 1개를 주면 그 파일만, 폴더를 주면 폴더 속(하위 폴더 포함)의
    지원 파일 전부를 한꺼번에 변환합니다.
  * 변환 결과 .md 는 원본과 같은 위치에, 같은 이름으로 만들어집니다.
    (원본 파일은 절대 수정·삭제하지 않습니다.)
  * 이미 같은 이름의 .md 가 있으면 건너뜁니다. --force 를 붙이면 다시 변환합니다.
  * 한글 문서(.hwp / .hwpx)는 이 도구가 아니라 같은 폴더의 hwp2md.py 를 사용하세요.

필요한 것: Python 3.11 이상 + markitdown 패키지.
  준비되어 있지 않으면 AI에게 "tools의 파일 변환 환경을 준비해줘"라고 요청하세요.

자세한 설명은 같은 폴더의 도구_사용법.md 를 보세요.
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REEXEC_GUARD = "CONVERT2MD_REEXEC"  # venv 재실행 무한 반복 방지용

# 지원 형식 (확장자 → 한국어 이름)
SUPPORTED_EXTS = {
    ".pdf": "PDF 문서",
    ".docx": "워드 문서",
    ".pptx": "파워포인트",
    ".xlsx": "엑셀",
    ".xls": "엑셀(구버전)",
    ".csv": "표 데이터(CSV)",
    ".jpg": "이미지",
    ".jpeg": "이미지",
    ".png": "이미지",
    ".gif": "이미지",
    ".bmp": "이미지",
    ".webp": "이미지",
    ".tiff": "이미지",
}
HWP_EXTS = {".hwp", ".hwpx"}

# 폴더 일괄 변환 시 들어가지 않는 폴더
SKIP_DIR_NAMES = {"venv", "rhwp", "__pycache__", "node_modules"}


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


def _find_venv_python() -> Path | None:
    """스크립트 옆 venv/ 안의 파이썬을 찾는다 (Mac/Windows 모두)."""
    for base in [SCRIPT_DIR, *_packet_tool_dirs()]:
        venv = base / "venv"
        for rel in ("bin/python3", "bin/python", "Scripts/python.exe", "Scripts/python"):
            cand = venv / rel
            if cand.exists():
                return cand
    return None


def _ensure_markitdown() -> None:
    """markitdown 을 찾는다. 없으면 venv 로 다시 실행하고, 그래도 없으면 안내."""
    try:
        import markitdown  # noqa: F401
        return
    except ImportError:
        pass

    venv_py = _find_venv_python()
    if venv_py is not None and os.environ.get(REEXEC_GUARD) != "1":
        # venv 안의 파이썬으로 자기 자신을 다시 실행 (사용자는 신경 쓸 필요 없음)
        import subprocess

        env = dict(os.environ)
        env[REEXEC_GUARD] = "1"
        raise SystemExit(
            subprocess.call(
                [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]],
                env=env,
            )
        )

    print("❌ 변환 프로그램(markitdown)이 설치되어 있지 않습니다.", file=sys.stderr)
    print(
        "   AI에게 이렇게 말해 주세요: "
        "\"markitdown을 설치해줘 (pip install 'markitdown[all]')\"",
        file=sys.stderr,
    )
    print("   더 자세한 도움말: tools/안내_파일변환.md", file=sys.stderr)
    sys.exit(2)


def _iter_folder(root: Path):
    """폴더 안의 변환 후보 파일을 (숨김·시스템 폴더는 빼고) 차례로 낸다."""
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel_dirs = p.relative_to(root).parts[:-1]
        if any(
            part.startswith(".") or part in SKIP_DIR_NAMES or part.endswith("_img")
            for part in rel_dirs
        ):
            continue
        if p.name.startswith((".", "~$")):  # 숨김 파일, 오피스 임시 파일
            continue
        yield p


def _convert_one(converter, src: Path, force: bool) -> str:
    """파일 1개 변환. 결과: 'ok' | 'skip' | 'empty'"""
    out = src.with_suffix(".md")
    if out.exists() and not force:
        print(f"⏭️  건너뜀(이미 .md 있음): {src.name}")
        return "skip"

    result = converter.convert(str(src))
    text = (result.text_content or "").strip()
    if not text:
        print(f"⚠️  내용을 뽑아내지 못했습니다: {src.name}")
        print("    (스캔본 PDF나 글자 없는 이미지일 수 있습니다."
              " 이런 파일은 AI 대화창에 직접 첨부해 보여주는 편이 낫습니다.)")
        return "empty"

    frontmatter = (
        "---\n"
        "tags: [변환문서]\n"
        f"date: {date.today().isoformat()}\n"
        "source: convert2md (markitdown)\n"
        f"original_file: {src.name}\n"
        "---\n\n"
    )
    out.write_text(frontmatter + text + "\n", encoding="utf-8")
    print(f"✅ 완료: {out}")
    return "ok"


def main() -> None:
    _setup_console()

    parser = argparse.ArgumentParser(
        prog="convert2md",
        description="PDF·워드·엑셀·파워포인트·이미지 파일을 md(마크다운)로 변환합니다.",
        epilog="예시:  python convert2md.py ../1_수집자료실        (1_수집자료실 폴더 전체 일괄 변환)\n"
               "       python convert2md.py 보고서.pdf      (파일 1개 변환)\n"
               "한글 문서(.hwp/.hwpx)는 hwp2md.py 를 사용하세요.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("inputs", nargs="+", metavar="<파일 또는 폴더>",
                        help="변환할 파일 또는 폴더 (폴더면 하위 폴더까지 일괄 변환)")
    parser.add_argument("--force", action="store_true",
                        help="이미 .md 가 있어도 다시 변환합니다")
    args = parser.parse_args()

    _ensure_markitdown()
    from markitdown import MarkItDown

    converter = MarkItDown()
    counts = {"ok": 0, "skip": 0, "empty": 0, "fail": 0, "hwp": 0}

    for raw in args.inputs:
        root = Path(raw).expanduser()

        if not root.exists():
            print(f"❌ 찾을 수 없습니다: {root}")
            print("   경로(파일 위치)에 오타가 없는지 확인해 주세요.")
            counts["fail"] += 1
            continue

        if root.is_file():
            targets = [root]
            explicit = True  # 사용자가 콕 집어 준 파일 → 지원 안 하면 이유를 알려줌
        else:
            targets = list(_iter_folder(root))
            explicit = False

        for f in targets:
            ext = f.suffix.lower()

            if ext in HWP_EXTS:
                counts["hwp"] += 1
                print(f"ℹ️  한글 문서는 hwp2md.py 로 변환하세요: {f.name}")
                print(f"    실행 예:  python hwp2md.py \"{f}\"")
                continue

            if ext not in SUPPORTED_EXTS:
                if explicit and ext != ".md":
                    kinds = "·".join(sorted({e.lstrip('.') for e in SUPPORTED_EXTS}))
                    print(f"❌ 지원하지 않는 형식입니다: {f.name}")
                    print(f"   지원 형식: {kinds} (한글 문서는 hwp2md.py)")
                    counts["fail"] += 1
                continue  # 폴더 일괄 모드에서는 지원 외 파일을 조용히 지나감

            try:
                counts[_convert_one(converter, f, args.force)] += 1
            except Exception as e:  # 한 파일이 실패해도 나머지는 계속 변환
                counts["fail"] += 1
                print(f"❌ 변환 실패: {f.name}")
                print(f"   이유: {type(e).__name__}: {e}")
                print("   → 파일이 다른 프로그램에서 열려 있으면 닫고 다시 시도해 주세요."
                      " 계속 실패하면 tools/안내_파일변환.md 를 참고하세요.")

    print("\n===== 변환 결과 =====")
    line = f"성공 {counts['ok']}건 · 건너뜀 {counts['skip']}건 · 실패 {counts['fail']}건"
    if counts["empty"]:
        line += f" · 내용 없음 {counts['empty']}건"
    if counts["hwp"]:
        line += f" · 한글 문서 안내 {counts['hwp']}건"
    print(line)
    if counts["ok"]:
        print("성공한 파일은 원본 옆에 같은 이름의 .md 로 저장되었습니다."
              " 이 화면이 보이면 성공입니다.")

    sys.exit(1 if counts["fail"] else 0)


if __name__ == "__main__":
    main()
