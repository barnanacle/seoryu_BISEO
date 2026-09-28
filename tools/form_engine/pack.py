"""Load a form pack without following paths outside its own directory."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PACKS_ROOT = Path(__file__).resolve().parents[1] / "form_packs"


def resolve_asset(pack: dict, name: str) -> Path:
    root = Path(pack["_root"]).resolve()
    path = (root / name).resolve()
    if path != root and root not in path.parents:
        raise ValueError("꾸러미 밖의 파일을 참조할 수 없습니다: " + name)
    return path


def load_pack(reference: str | Path) -> dict:
    path = Path(reference)
    if not path.is_absolute() and not path.exists():
        path = PACKS_ROOT / path
    if path.is_dir():
        path = path / "pack.json"
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError("서식 꾸러미를 찾을 수 없습니다: " + str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("지원하지 않는 서식 꾸러미 형식입니다.")
    if data.get("id") != path.parent.name:
        raise ValueError("꾸러미 id와 폴더 이름이 다릅니다.")
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("공식 서식의 쪽별 칸 정의가 없습니다.")
    numbers = [p.get("page") for p in pages]
    if numbers != list(range(len(numbers))) or any(not isinstance(p.get("fields"), dict) for p in pages):
        raise ValueError("꾸러미 pages에는 0부터 연속된 쪽과 칸 정의가 필요합니다.")
    data["_root"] = path.parent
    files = data.get("files", {})
    names = [files.get("form_pdf"), files.get("annex_docx"), files.get("font_docx")]
    backgrounds = files.get("form_png", [])
    names.extend(backgrounds if isinstance(backgrounds, list) else [backgrounds])
    for name in names:
        if name and not resolve_asset(data, name).is_file():
            raise FileNotFoundError("꾸러미 자산을 찾을 수 없습니다: " + name)
    original = resolve_asset(data, files["form_pdf"])
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    if digest != data.get("form_sha256"):
        raise ValueError("공식 서식 원본이 꾸러미 기준과 다릅니다. 좌표를 다시 확인해야 합니다.")
    return data
