#!/usr/bin/env python3
"""수강생용 운영 꾸러미가 설명서 폴더 없이 설치되는지 확인한다."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "runtime_manifest.json").read_text(encoding="utf-8"))
sys.path.insert(0,str(ROOT))
from install_runtime import source_is_excluded,copy_without_overwrite

SOURCE_DIRS = ("1_자료실", "2_서류철", "3_작업실")
LEGACY_DIRS = ("DATA", "서류함", "문서작업", "0_설치", "1_시작", "2_도구", "3_사용법", "4_확장", "5_챗지피티")

INSTALL_FACING_DOCS = [
    ROOT / "README.md",
    ROOT / "설치프롬프트.md",
    ROOT / "a_설치/MAC_설치.md",
    ROOT / "a_설치/WINDOWS_설치.md",
    ROOT / "a_설치/설치_점검표.md",
    ROOT / "b_시작/BOOTSTRAP.md",
    ROOT / "f_챗지피티/README.md",
    ROOT / "f_챗지피티/앱설치_설정.md",
    ROOT / "f_챗지피티/Codex_설치_상세.md",
    ROOT / "f_챗지피티/붙여넣기_프롬프트.md",
    ROOT / "f_챗지피티/BOOTSTRAP_CHATGPT.md",
    ROOT / "f_챗지피티/실측_점검표.md",
    ROOT / "f_챗지피티/문제해결_보충.md",
]

BANNED_INSTALL_PHRASES = (
    "Download ZIP",
    "꾸러미 ZIP",
    "패킷 ZIP",
    "GitHub Desktop으로 클론",
    "GitHub Desktop으로 복제",
    "b_시작/BOOTSTRAP.md를 읽고",
)


def check_source_tools(target: Path) -> None:
    """새 경로의 미처리 집계·처리 대장 대조·개인 자료 제외를 확인한다."""
    for rel in (
        "1_자료실/행정절차·공통/guide.pdf",
        "1_자료실/행정절차·공통/pending.pdf",
        "2_서류철/case/private.md",
        "3_작업실/draft.md",
    ):
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic fixture", encoding="utf-8")

    ledger = "1_자료실/행정절차·공통/guide.pdf\t새페이지\tguide\t2026-09-04\n"
    (target / "wiki/.ingest-ledger.tsv").write_text(ledger, encoding="utf-8")
    for path in (target / "tools/make_dashboard.py", ROOT / "f_챗지피티/templates/tools_make_dashboard.py"):
        spec = importlib.util.spec_from_file_location("dashboard_path_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        paths, _, _ = module.parse_ledger(ledger.replace("/", "\\"))
        assert "1_자료실/행정절차·공통/guide.pdf" in paths
        assert "행정절차·공통/guide.pdf" in paths

        original_read = module.read_text

        def guarded_read(filename):
            relative = Path(filename).relative_to(target)
            assert relative.parts[0] not in SOURCE_DIRS, relative
            return original_read(filename)

        module.read_text = guarded_read
        payload = module.build_data(str(target), lambda text: text)
        assert payload["요약"]["미처리"] == 1, payload["요약"]
        assert "미처리" not in payload["지표없음"]
        template = (target / "tools/dashboard_template.html").read_text(encoding="utf-8")
        rendered = module.inject(template, payload)
        assert "const DATA = /*__DATA__*/ {" in rendered
        assert "private.md" not in rendered and "draft.md" not in rendered

    # 입력 폴더 이름이 wiki 하위에 생겨도 개인정보 점검은 건너뛴다.
    for folder in SOURCE_DIRS:
        nested = target / "wiki" / folder
        nested.mkdir()
        (nested / "private.md").write_text("synthetic fixture", encoding="utf-8")
    for path in (target / "tools/pii_check.py", ROOT / "f_챗지피티/templates/tools_pii_check.py"):
        spec = importlib.util.spec_from_file_location("pii_path_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for filename in module.iter_files(str(target)):
            relative = Path(filename).relative_to(target)
            assert not set(relative.parts) & set(SOURCE_DIRS), relative


def main() -> int:
    for doc in INSTALL_FACING_DOCS:
        text = doc.read_text(encoding="utf-8")
        if doc.name != "설치프롬프트.md":
            assert "설치프롬프트.md" in text, doc
        for phrase in BANNED_INSTALL_PHRASES:
            assert phrase.casefold() not in text.casefold(), (doc, phrase)

    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "설치 방법은 하나입니다" in root_readme
    assert "비어 있는 `JARVIS` 폴더" in root_readme
    assert "Codex" in root_readme

    with tempfile.TemporaryDirectory(prefix="test_JAARVIS_runtime_") as temp:
        target = Path(temp) / "JARVIS"
        subprocess.run(
            [sys.executable, str(ROOT / "install_runtime.py"), str(target)],
            check=True,
        )

        for rel in MANIFEST["required_directories"]:
            assert (target / rel).is_dir(), rel
        for rel in MANIFEST["required_files"]:
            assert (target / rel).is_file(), rel
        for rel in MANIFEST["must_not_install"]:
            assert not (target / rel).exists(), rel
        for rel in LEGACY_DIRS:
            assert not (ROOT / rel).exists(), rel
            assert not (target / rel).exists(), rel
        assert {p.name for p in target.iterdir() if p.is_dir() and p.name[0].isdigit()} == set(SOURCE_DIRS)
        assert not (target / ".git").exists()

        for item in MANIFEST["copy"]:
            source, destination = ROOT / item["source"], target / item["target"]
            files = source.rglob("*") if source.is_dir() else [source]
            for original in files:
                if original.is_file() and not source_is_excluded(original,ROOT,MANIFEST["never_copy_from_source"]):
                    copied = destination / original.relative_to(source) if source.is_dir() else destination
                    assert copied.read_bytes() == original.read_bytes(), copied

        assert (target / "AGENTS.md").read_bytes() == (target / "CLAUDE.md").read_bytes()
        assert (target / "AGENTS.md").stat().st_size <= 30_000
        assert not list(target.rglob("__pycache__"))
        assert not list(target.rglob("*.pyc"))

        readme = (target / "README.md").read_text(encoding="utf-8")
        for folder in ("1_자료실", "2_서류철", "3_작업실", "wiki", "memory", "tools"):
            assert folder in readme

        skill_root = target / ".agents/skills/form-template-filler"
        skill_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(skill_root.rglob("*"))
            if path.is_file() and path.suffix in {".md", ".yaml", ".yml"}
        )
        for phrase in ("fields.json", "공식 서식", "산출/_tmp", "【확인 필요】", "법령명·조문·별표"):
            assert phrase in skill_text, phrase
        assert "/Users/" not in skill_text
        assert not re.search(r"\b01[016789][ -]?\d{3,4}[ -]?\d{4}\b", skill_text)
        assert not list(skill_root.rglob("*.pdf"))
        assert not list(skill_root.rglob("*.docx"))
        assert (target / "tools/안내_반복서식.md").read_text(encoding="utf-8") == (
            skill_root / "references/implementation-guide.md"
        ).read_text(encoding="utf-8")

        constitution = (target / "AGENTS.md").read_text(encoding="utf-8")
        for trigger in ("wiki에 반영해", "환류해", "인젝션해"):
            assert trigger in constitution
        for source in ("1_자료실/", "2_서류철/", "3_작업실/"):
            assert source in constitution
        assert "이미 반영된 자료이므로 건너뛴다" in constitution
        assert "2_서류철/#sha256:" in constitution

        ignored = subprocess.run(
            ["git", "-C", str(ROOT), "-c", "core.quotePath=false", "check-ignore", "--no-index", "--stdin"],
            input="2_서류철/case/private.pdf\n3_작업실/draft.docx\n2_서류철/안내.md\n3_작업실/안내.md\n",
            text=True, capture_output=True, check=True,
        )
        assert ignored.stdout.splitlines() == ["2_서류철/case/private.pdf", "3_작업실/draft.docx"]
        for excluded in MANIFEST['never_copy_from_source']:
            assert not (target/excluded).exists(),excluded
        assert '질문지' in (target/'tools/opinion_writer/AGENTS.md').read_text(encoding='utf-8')
        assert 'tools/opinion_writer/AGENTS.md' in constitution
        # Synthetic private output in the source must never enter a new install.
        fixture=Path(temp)/'copy_source';fixture.mkdir()
        for name in ['tools/opinion_writer/산출/private.txt','tools/opinion_writer/.venv/private.txt','tools/opinion_writer/bin/safe.py']:
            f=fixture/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('synthetic')
        output=Path(temp)/'copy_target'
        copy_without_overwrite(fixture/'tools',output/'tools',[],[],source_root=fixture,exclusions=MANIFEST['never_copy_from_source'])
        assert (output/'tools/opinion_writer/bin/safe.py').is_file()
        assert not (output/'tools/opinion_writer/산출').exists()
        assert not (output/'tools/opinion_writer/.venv').exists()
        # Reinstallation preserves the user's modified existing files.
        (target/'README.md').write_text('user content',encoding='utf-8')
        subprocess.run([sys.executable,str(ROOT/'install_runtime.py'),str(target)],check=True)
        assert (target/'README.md').read_text(encoding='utf-8')=='user content'
        check_source_tools(target)

    print("✅ clean runtime install test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
