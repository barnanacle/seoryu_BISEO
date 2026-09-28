#!/usr/bin/env python3
"""Build reviewed form-pack outputs from one fields.json file."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "opinion_writer/bin"))

from document_runtime import bootstrap
from form_engine.engine import build
from form_engine.pack import PACKS_ROOT, load_pack


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fields", nargs="?", type=Path)
    parser.add_argument("--pack", help="꾸러미 id 또는 pack.json 경로")
    parser.add_argument("--list-packs", action="store_true")
    parser.add_argument("--keys", action="store_true")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--raster", action="store_true")
    parser.add_argument("--output-root", type=Path,
                        help="산출물 루트. 기본값은 입력 fields.json 옆의 산출 폴더")
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)
    if args.list_packs:
        for item in sorted(PACKS_ROOT.glob("*/pack.json")):
            print(item.parent.name)
        return
    if not args.pack:
        parser.error("--pack을 지정하세요.")
    pack = load_pack(args.pack)
    if args.keys:
        for name, spec in pack["fields"].items():
            print(name, spec["type"], "필수" if spec.get("required") else "선택")
        return
    if args.fields is None:
        parser.error("fields.json 경로가 필요합니다.")
    bootstrap()
    fields = json.loads(args.fields.read_text(encoding="utf-8"))
    input_parent = args.fields.resolve().parent
    in_public_pack = input_parent == PACKS_ROOT.resolve() or PACKS_ROOT.resolve() in input_parent.parents
    output_root = args.output_root or (
        TOOLS / "form_engine/산출" if in_public_pack else input_parent / "산출"
    )
    build(fields, pack, output_root, args.out_dir, args.no_open, args.raster)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print("오류:", error, file=sys.stderr)
        raise SystemExit(1)
