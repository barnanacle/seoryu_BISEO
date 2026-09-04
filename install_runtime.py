#!/usr/bin/env python3
"""install_JAARVIS 저장소에서 수강생용 운영 꾸러미만 복사한다.

저장소의 a_~f_ 폴더는 설치·원본·참고 문서이므로 대상 폴더에 복사하지 않는다.
복사 목록은 runtime_manifest.json 한 곳에서 관리한다.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = SOURCE_ROOT / "runtime_manifest.json"


def copy_without_overwrite(source: Path, target: Path, created: list[str], skipped: list[str]) -> None:
    if source.name in {"__pycache__", ".DS_Store", "Thumbs.db"} or source.suffix == ".pyc":
        return
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for child in sorted(source.iterdir(), key=lambda p: p.name):
            copy_without_overwrite(child, target / child.name, created, skipped)
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        skipped.append(str(target))
        return
    shutil.copy2(source, target)
    created.append(str(target))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="수강생용 JARVIS 운영 꾸러미를 알파벳 접두어의 설명서 폴더 없이 설치합니다."
    )
    parser.add_argument("target", help="Codex 프로젝트로 만든 설치 대상 폴더")
    args = parser.parse_args()

    target_root = Path(args.target).expanduser().resolve()
    if target_root == SOURCE_ROOT:
        print("❌ 저장소 원본 폴더와 설치 대상 폴더는 서로 달라야 합니다.", file=sys.stderr)
        return 2
    target_root.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    created: list[str] = []
    skipped: list[str] = []

    for item in manifest["copy"]:
        source = SOURCE_ROOT / item["source"]
        target = target_root / item["target"]
        if not source.exists():
            print(f"❌ 원본 누락: {source}", file=sys.stderr)
            return 3
        copy_without_overwrite(source, target, created, skipped)

    failures: list[str] = []
    for rel in manifest["required_directories"]:
        if not (target_root / rel).is_dir():
            failures.append(f"필수 폴더 누락: {rel}")
    for rel in manifest["required_files"]:
        if not (target_root / rel).is_file():
            failures.append(f"필수 파일 누락: {rel}")
    for rel in manifest["must_not_install"]:
        if (target_root / rel).exists():
            failures.append(f"설치 제외 항목이 생김: {rel}")

    if failures:
        print("❌ 설치 검증 실패", file=sys.stderr)
        for failure in failures:
            print(f"   - {failure}", file=sys.stderr)
        return 4

    print("✅ 수강생용 JARVIS 운영 꾸러미 설치 완료")
    print(f"   위치: {target_root}")
    print("   사용자가 넣는 곳: 1_수집자료실 · 2_수임업무철 · 3_문서작업실")
    print("   AI가 관리하는 곳: memory · wiki · tools")
    print("   설치 제외 확인: a_~f_ 설명서 폴더 (저장소의 .git도 복사하지 않음)")
    print(f"   새 파일: {len(created)}개")
    if skipped:
        print(f"   기존 파일 보존(덮어쓰지 않음): {len(skipped)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
