#!/usr/bin/env python3
"""수강생용 운영 꾸러미가 설명서 폴더 없이 설치되는지 확인한다."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "runtime_manifest.json").read_text(encoding="utf-8"))

INSTALL_FACING_DOCS = [
    ROOT / "README.md",
    ROOT / "설치프롬프트.md",
    ROOT / "0_설치/MAC_설치.md",
    ROOT / "0_설치/WINDOWS_설치.md",
    ROOT / "0_설치/설치_점검표.md",
    ROOT / "1_시작/BOOTSTRAP.md",
    ROOT / "5_챗지피티/README.md",
    ROOT / "5_챗지피티/앱설치_설정.md",
    ROOT / "5_챗지피티/Codex_설치_상세.md",
    ROOT / "5_챗지피티/붙여넣기_프롬프트.md",
    ROOT / "5_챗지피티/BOOTSTRAP_CHATGPT.md",
    ROOT / "5_챗지피티/실측_점검표.md",
    ROOT / "5_챗지피티/문제해결_보충.md",
]

BANNED_INSTALL_PHRASES = (
    "Download ZIP",
    "꾸러미 ZIP",
    "패킷 ZIP",
    "GitHub Desktop으로 클론",
    "GitHub Desktop으로 복제",
    "1_시작/BOOTSTRAP.md를 읽고",
)


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
        assert not (target / ".git").exists()

        assert (target / "AGENTS.md").read_bytes() == (target / "CLAUDE.md").read_bytes()
        assert not list(target.rglob("__pycache__"))
        assert not list(target.rglob("*.pyc"))

        readme = (target / "README.md").read_text(encoding="utf-8")
        for folder in ("DATA", "서류함", "문서작업", "wiki", "memory", "tools"):
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
        for source in ("DATA/", "서류함/", "문서작업/"):
            assert source in constitution
        assert "이미 반영된 자료이므로 건너뛴다" in constitution
        assert "서류함/#sha256:" in constitution

    print("✅ clean runtime install test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
