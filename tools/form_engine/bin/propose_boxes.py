#!/usr/bin/env python3
"""Propose reviewable form-cell boxes from a blank official PDF.

Candidates are never written into pack.json automatically. Inspect the numbered
PNG against the official PDF, then enter only approved boxes into the pack.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def unique(values, tolerance=1.5):
    result = []
    for value in sorted(values):
        if not result or abs(value - result[-1]) > tolerance:
            result.append(value)
    return result


def candidates(page, page_index, min_width=65, max_top=None):
    horizontal = [line for line in page.lines
                  if abs(line["y1"] - line["y0"]) < 1
                  and line["x1"] - line["x0"] > page.width * .14]
    vertical = [line for line in page.lines
                if abs(line["x1"] - line["x0"]) < 1
                and line["y1"] - line["y0"] > 15]
    ys = unique([line["top"] for line in horizontal])
    if not horizontal or len(ys) < 2:
        return []
    xs = unique([line["x0"] for line in vertical] +
                [min(line["x0"] for line in horizontal),
                 max(line["x1"] for line in horizontal)])
    result = []
    for top, bottom in zip(ys, ys[1:]):
        if bottom - top < 18:
            continue
        if max_top is not None and top >= max_top:
            continue
        for left, right in zip(xs, xs[1:]):
            if right - left < min_width:
                continue
            center_x, center_y = (left + right) / 2, (top + bottom) / 2
            if not any(line["x0"] - 2 <= center_x <= line["x1"] + 2 and
                       abs(line["top"] - top) <= 2 for line in horizontal):
                continue
            inset_top = min(27, max(12, (bottom - top) * .55))
            box = [round(left + 4, 2), round(top + inset_top, 2),
                   round(right - left - 8, 2), round(bottom - top - inset_top - 3, 2)]
            if box[2] < 25 or box[3] < 8:
                continue
            x, y, w, h = box
            if any(char["text"].strip() and x <= (char["x0"]+char["x1"])/2 <= x+w
                   and y <= (char["top"]+char["bottom"])/2 <= y+h for char in page.chars):
                continue
            label = (page.crop((left, top, right, min(bottom, top + 22)))
                     .extract_text() or "").replace("\n", " ").strip()[:65]
            result.append({"id": "P%d-%02d" % (page_index + 1, len(result) + 1),
                           "page": page_index, "box": box, "nearby_label": label})
    return result


def render_overlay(pdf, page_index, proposals, destination):
    from PIL import Image, ImageDraw, ImageFont
    from tempfile import TemporaryDirectory

    binary = shutil.which("pdftoppm")
    if not binary:
        raise RuntimeError("확인용 PNG에는 pdftoppm이 필요합니다.")
    with TemporaryDirectory(prefix="form_boxes_") as folder:
        prefix = Path(folder) / "page"
        subprocess.run([binary, "-f", str(page_index + 1), "-l", str(page_index + 1),
                        "-r", "120", "-png", "-singlefile", str(pdf), str(prefix)],
                       check=True, stdout=subprocess.DEVNULL)
        image = Image.open(str(prefix) + ".png").convert("RGB")
        draw = ImageDraw.Draw(image)
        scale = 120 / 72
        for item in proposals:
            x, y, w, h = item["box"]
            rect = [round(x * scale), round(y * scale),
                    round((x + w) * scale), round((y + h) * scale)]
            draw.rectangle(rect, outline="#D42C21", width=2)
            draw.text((rect[0] + 2, rect[1] + 1), item["id"], fill="#A20C08",
                      font=ImageFont.load_default())
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--min-width", type=float, default=65)
    parser.add_argument("--max-top", type=float)
    args = parser.parse_args(argv)
    import pdfplumber

    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    all_candidates = []
    with pdfplumber.open(args.pdf) as pdf:
        for index, page in enumerate(pdf.pages):
            proposals = candidates(page, index, args.min_width, args.max_top)
            all_candidates.extend(proposals)
            render_overlay(args.pdf, index, proposals, output / ("page-%d-candidates.png" % (index + 1)))
    (output / "candidates.json").write_text(json.dumps(all_candidates, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    print("후보", len(all_candidates), "개 · 자동 확정하지 않았습니다:", output)


if __name__ == "__main__":
    main()
