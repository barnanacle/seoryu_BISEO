#!/usr/bin/env python3
"""수강생용 운영 꾸러미가 설명서 폴더 없이 설치되는지 확인한다."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "runtime_manifest.json").read_text(encoding="utf-8"))


def main() -> int:
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
