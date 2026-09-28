#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility entry point for the opinion notice form pack.

Keep the established CLI and Python function signatures while the renderer
reads official form assets, field rules, and output names from pack.json.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
TOOLS = HERE.parent
sys.path.insert(0, str(HERE / "bin/_vendor"))
sys.path.insert(0, str(TOOLS))

from form_engine.annex import build_annex_docx as _build_annex_docx
from form_engine.engine import build as _build, checked_output as _checked_output
from form_engine.pack import load_pack
from form_engine.transforms import UNKNOWN, normalize_fields as _normalize_fields

PACK = load_pack("opinion_notice_11")
OUTDIR = HERE / "산출"
# Legacy names remain patchable for callers that verify an altered official PDF.
FORM_PDF = HERE / "서식/별지11호_의견제출서_공식서식.pdf"
FORM_PNG = HERE / "서식/별지11호_의견제출서_공식서식_배경.png"
ANNEX_DOCX = HERE / "서식/별지_상세의견서_템플릿.docx"
FORM_KEYS = list(PACK["pages"][0]["fields"])


def normalize_fields(fields):
    return _normalize_fields(fields, PACK)


def build_annex_docx(fields, out_path):
    return _build_annex_docx(fields, out_path, PACK)


def checked_output(path):
    return _checked_output(path, OUTDIR)


def build(fields, output_dir=None, no_open=False, force_raster=False):
    return _build(fields, PACK, OUTDIR, output_dir, no_open, force_raster,
                  asset_overrides={"form_pdf": FORM_PDF, "form_png": FORM_PNG,
                                   "annex_docx": ANNEX_DOCX})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fields", nargs="?")
    parser.add_argument("--keys", action="store_true")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--raster", action="store_true")
    parser.add_argument("--out-dir")
    args = parser.parse_args(argv)
    if args.keys:
        print("\n".join(FORM_KEYS + ["의견제출인_명칭", "처분청", "건명", "대상_표시",
                                     "취지", "소명 [{제목, 본문}, ...]", "결어",
                                     "소명자료_목록", "별지_서명", "파일명", "서식 {type}"]))
        return
    if not args.fields:
        parser.error("fields.json 경로가 필요합니다.")
    with open(args.fields, encoding="utf-8") as stream:
        fields = json.load(stream)
    build(fields, args.out_dir, args.no_open, args.raster)


if __name__ == "__main__":
    from document_runtime import bootstrap
    bootstrap()
    try:
        main()
    except (ValueError, RuntimeError, KeyError) as error:
        print("오류:", error, file=sys.stderr)
        sys.exit(1)
