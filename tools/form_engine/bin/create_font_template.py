#!/usr/bin/env python3
"""Create a blank DOCX with embedded form fonts for packs without an annex."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS / "opinion_writer/bin"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--form-font", required=True, type=Path)
    parser.add_argument("--body-font", required=True, type=Path)
    args = parser.parse_args(argv)
    from docx import Document
    from docx.shared import Mm
    from document_runtime import embed_fonts

    doc = Document()
    doc.sections[0].page_width = Mm(210)
    doc.sections[0].page_height = Mm(297)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(args.out)
    embed_fonts(args.out, {"NanumGothic": args.form_font,
                           "NanumMyeongjo": args.body_font})
    print(args.out)


if __name__ == "__main__":
    main()
