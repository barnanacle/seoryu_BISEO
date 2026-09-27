#!/usr/bin/env python3
"""매니페스트에 적힌 서류비서 운영 꾸러미만 안전하게 설치하고 검증한다."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = SOURCE_ROOT / "runtime_manifest.json"
OS_METADATA_NAMES = {".ds_store", "thumbs.db", "desktop.ini", ".localized"}


def is_os_metadata(path: Path) -> bool:
    """Finder/Explorer가 만든 파일만 예외로 둔다. 다른 숨김 파일은 예외가 아니다."""
    name = path.name.casefold()
    return name in OS_METADATA_NAMES or name.startswith("._")


def source_is_excluded(source: Path, source_root: Path, exclusions=()) -> bool:
    relative = source.relative_to(source_root)
    rel_text = relative.as_posix()
    return (
        any(part in {"__pycache__", ".venv"} or is_os_metadata(Path(part)) for part in relative.parts)
        or source.suffix == ".pyc"
        or source.is_symlink()
        or any(rel_text == item or rel_text.startswith(item.rstrip("/") + "/") for item in exclusions)
    )


def copy_without_overwrite(
    source: Path,
    target: Path,
    created: list[str],
    skipped: list[str],
    *,
    source_root: Path = SOURCE_ROOT,
    exclusions=(),
) -> None:
    if source_is_excluded(source, source_root, exclusions):
        return
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for child in sorted(source.iterdir(), key=lambda path: path.name):
            copy_without_overwrite(
                child, target / child.name, created, skipped,
                source_root=source_root, exclusions=exclusions,
            )
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        skipped.append(str(target))
        return
    shutil.copy2(source, target)
    created.append(str(target))


def manifest_entries(manifest: dict) -> tuple[dict[str, Path], set[str]]:
    """실제 source 파일에서 기대 파일/빈 폴더까지 계산한다."""
    files: dict[str, Path] = {}
    directories: set[str] = set()
    exclusions = manifest["never_copy_from_source"]
    for item in manifest["copy"]:
        source_rel = Path(item["source"])
        target_rel = Path(item["target"])
        for rel in (source_rel, target_rel):
            if rel.is_absolute() or ".." in rel.parts or not rel.parts:
                raise ValueError(f"잘못된 매니페스트 경로: {rel}")
        source = SOURCE_ROOT / source_rel
        if not source.exists() or source_is_excluded(source, SOURCE_ROOT, exclusions):
            raise FileNotFoundError(f"설치 원본 누락: {source_rel}")
        members = [source, *source.rglob("*")] if source.is_dir() else [source]
        for member in members:
            if source_is_excluded(member, SOURCE_ROOT, exclusions):
                continue
            destination = target_rel / member.relative_to(source) if source.is_dir() else target_rel
            rel_text = destination.as_posix()
            directories.update(parent.as_posix() for parent in destination.parents if parent != Path("."))
            if member.is_dir():
                directories.add(rel_text)
            elif member.is_file():
                if rel_text in files and files[rel_text] != member:
                    raise ValueError(f"매니페스트 대상 경로 중복: {rel_text}")
                files[rel_text] = member
    return files, directories


def verify_runtime(target_root: Path, manifest: dict) -> dict:
    """대상은 읽기만 한다. OS 메타데이터는 보존하고 오류 수에서 뺀다."""
    expected_files, expected_dirs = manifest_entries(manifest)
    missing_files = sorted(rel for rel in expected_files if not (target_root / rel).is_file() or (target_root / rel).is_symlink())
    missing_dirs = sorted(rel for rel in expected_dirs if not (target_root / rel).is_dir() or (target_root / rel).is_symlink())
    changed_files = sorted(
        rel for rel, source in expected_files.items()
        if rel not in missing_files and (target_root / rel).read_bytes() != source.read_bytes()
    )
    extras: list[str] = []
    ignored_metadata: list[str] = []
    for path in target_root.rglob("*"):
        rel = path.relative_to(target_root).as_posix()
        if path.is_file() and not path.is_symlink() and is_os_metadata(path):
            ignored_metadata.append(rel)
        elif rel not in expected_files and rel not in expected_dirs:
            extras.append(rel)
    missing_required = sorted(
        [f"폴더: {rel}" for rel in manifest["required_directories"] if not (target_root / rel).is_dir()]
        + [f"파일: {rel}" for rel in manifest["required_files"] if not (target_root / rel).is_file()]
    )
    forbidden = sorted(rel for rel in manifest["must_not_install"] if (target_root / rel).exists())
    return {
        "expected_files": len(expected_files),
        "expected_directories": len(expected_dirs),
        "missing_files": missing_files,
        "missing_directories": missing_dirs,
        "changed_files": changed_files,
        "unexpected": sorted(extras),
        "ignored_metadata": sorted(ignored_metadata),
        "missing_required": missing_required,
        "forbidden": forbidden,
    }


def report(target_root: Path, result: dict, *, already_installed: bool = False) -> bool:
    problem_keys = ("missing_files", "missing_directories", "changed_files", "unexpected", "missing_required", "forbidden")
    failed = any(result[key] for key in problem_keys)
    if failed:
        print("❌ 서류비서 운영 꾸러미 검증 실패", file=sys.stderr)
        for key in problem_keys:
            values = result[key]
            if values:
                print(f"   {key}: {len(values)}개 — {', '.join(values[:8])}", file=sys.stderr)
    else:
        prefix = "기존 설치 검증 완료" if already_installed else "설치·검증 완료"
        print(f"✅ 서류비서 운영 꾸러미 {prefix}")
        print(f"   위치: {target_root}")
        print(f"   원본과 일치: 파일 {result['expected_files']}개 · 폴더 {result['expected_directories']}개")
        print("   누락 0개 · 내용 불일치 0개 · 예상 밖 운영 항목 0개")
        print("   사용자가 넣는 곳: 1_자료실 · 2_서류철 · 3_작업실")
        print("   AI가 관리하는 곳: memory · wiki · tools")
    if result["ignored_metadata"]:
        print(f"   OS 메타데이터 {len(result['ignored_metadata'])}개는 보존하고 검증 대상에서 제외했습니다.")
    return not failed


def main() -> int:
    parser = argparse.ArgumentParser(description="서류비서 꾸러미를 빈 폴더에 설치하고 원본과 대조합니다.")
    parser.add_argument("target", help="Codex 프로젝트로 연 설치 대상 폴더")
    parser.add_argument("--verify-only", action="store_true", help="복사 없이 설치 결과만 읽기 전용으로 재검증")
    args = parser.parse_args()
    target_root = Path(args.target).expanduser().resolve()
    if target_root == SOURCE_ROOT or SOURCE_ROOT in target_root.parents:
        print("❌ 설치 대상은 저장소 원본 폴더 바깥에 두어야 합니다.", file=sys.stderr)
        return 2
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest_entries(manifest)  # 복사 전 모든 원본 경로를 검사한다.
    except (OSError, ValueError, KeyError) as error:
        print(f"❌ 설치 목록 또는 원본 오류: {error}", file=sys.stderr)
        return 3

    if args.verify_only:
        if not target_root.is_dir():
            print("❌ 검증할 설치 폴더가 없습니다.", file=sys.stderr)
            return 2
        return 0 if report(target_root, verify_runtime(target_root, manifest), already_installed=True) else 4

    if target_root.exists():
        if not target_root.is_dir():
            print("❌ 설치 대상이 폴더가 아닙니다.", file=sys.stderr)
            return 2
        substantive = [path for path in target_root.iterdir() if not (path.is_file() and not path.is_symlink() and is_os_metadata(path))]
        if substantive:
            result = verify_runtime(target_root, manifest)
            if report(target_root, result, already_installed=True):
                return 0
            print("❌ 기존 파일을 덮어쓰거나 삭제하지 않았습니다. 빈 폴더를 사용하거나 --verify-only로 차이를 확인하세요.", file=sys.stderr)
            return 2
    else:
        target_root.mkdir(parents=True)

    created: list[str] = []
    skipped: list[str] = []
    try:
        for item in manifest["copy"]:
            copy_without_overwrite(
                SOURCE_ROOT / item["source"], target_root / item["target"], created, skipped,
                exclusions=manifest["never_copy_from_source"],
            )
    except OSError as error:
        print(f"❌ 설치 중 파일 복사 실패: {error}", file=sys.stderr)
        print("   복사된 파일은 삭제하지 않았습니다. 대상 상태를 확인하세요.", file=sys.stderr)
        return 3
    result = verify_runtime(target_root, manifest)
    if skipped:
        print(f"   기존 파일 보존(덮어쓰지 않음): {len(skipped)}개")
    return 0 if report(target_root, result) else 4


if __name__ == "__main__":
    raise SystemExit(main())
