"""Place pack-defined values on an untouched official PDF page."""
from __future__ import annotations

import copy
from pathlib import Path

from .transforms import UNKNOWN, form_values


def font_registry(template: Path, directory: Path, pack: dict):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from document_runtime import extract_fonts

    paths = extract_fonts(template, directory)
    families = pack["profile"]["fonts"]
    for alias, family in [("OpinionForm", families["form"]), ("OpinionBody", families["body"])]:
        pdfmetrics.registerFont(TTFont(alias, str(paths[family])))
    return paths


def wrap_text(text, font, size, width):
    """Preserve explicit newlines and fit every character; never clip a field."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    lines = []
    for paragraph in str(text).replace("\r", "").split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            if stringWidth(current + char, font, size) > width and current:
                boundary = current.rfind(" ")
                if boundary >= len(current) * .6:
                    lines.append(current[:boundary].rstrip())
                    current = current[boundary + 1:] + char
                else:
                    lines.append(current.rstrip())
                    current = char.lstrip()
            else:
                current += char
        lines.append(current.rstrip())
    return lines


def fit_text(text, spec, font="OpinionForm"):
    from reportlab.pdfbase.pdfmetrics import stringWidth

    x, y, width, height = spec["box"]
    size = float(spec["size"])
    minimum = float(spec.get("min_size", size))
    while size >= minimum - .001:
        lines = wrap_text(text, font, size, width)
        line_height = max(size, spec.get("line", size * 1.35) * size / spec["size"])
        required = size + (len(lines) - 1) * line_height
        if required <= height + .01 and all(stringWidth(line, font, size) <= width + .01 for line in lines):
            return lines, round(size, 3), line_height
        size = round(size - .1, 4)
        if minimum < size < minimum + .1:
            size = minimum
    raise ValueError("표지 칸에 내용이 들어가지 않습니다. 내용을 임의로 자르지 않았습니다: " + str(text)[:70])


def create_overlay(fields, pdf_path, template, work_dir, pack,
                   custom_boxes=None, page_size=(595, 842), page_index=0):
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics

    font_registry(template, Path(work_dir) / "form_fonts", pack)
    if custom_boxes is not None:
        representative = False
        specs = {key: {"box": list(spec[:4]), "size": spec[4], "min_size": spec[4],
                       "line": spec[4] * 1.3, "align": spec[5]} for key, spec in custom_boxes.items()}
        values = {key: str(value) for key, value in fields.items() if isinstance(value, str)}
    else:
        values, representative = form_values(fields, pack, page=page_index)
        specs = copy.deepcopy(pack["pages"][page_index]["fields"])
        if representative and pack.get("representative_box"):
            setting = pack["representative_box"]
            specs[setting["field"]] = {key: value for key, value in setting.items() if key != "field"}
    width, height = page_size
    c = canvas.Canvas(str(pdf_path), pagesize=page_size, invariant=1)
    c.setTitle(pack.get("output", {}).get("overlay_title", pack["title"] + " 입력값 레이어"))
    if custom_boxes is None:
        c.setFillColorRGB(1, 1, 1)
        for mask in pack.get("masks", []):
            if mask["page"] == page_index:
                x, y, w, h = mask["box"]
                c.rect(x, height - y - h, w, h, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    entries = []
    for key, spec in specs.items():
        value = values.get(key, UNKNOWN)
        if custom_boxes is None:
            value += pack.get("suffixes", {}).get(key, "")
        if not str(value).strip():
            continue
        x, y, w, h = spec["box"]
        if x < 0 or y < 0 or x + w > width + .1 or y + h > height + .1:
            raise ValueError("서식 좌표 범위 오류: " + key)
        if spec.get("align", "left") not in {"left", "center", "right"}:
            raise ValueError("서식 정렬 오류: " + key)
        lines, size, leading = fit_text(value, spec)
        block_height = size + (len(lines) - 1) * leading
        top = y + (h - block_height) / 2 if spec.get("valign") == "middle" else y
        for line_index, text in enumerate(lines):
            text_width = pdfmetrics.stringWidth(text, "OpinionForm", size)
            left = (x + (w - text_width) / 2 if spec.get("align") == "center"
                    else x + w - text_width if spec.get("align") == "right" else x)
            desired_top = top + line_index * leading
            descent = pdfmetrics.getDescent("OpinionForm") / 1000 * size
            baseline = height - desired_top - size - descent
            c.setFont("OpinionForm", size)
            c.drawString(left, baseline, text)
            entries.append({"field": key, "text": text, "left": left, "top": desired_top,
                            "width": text_width, "height": size, "box": spec["box"],
                            "align": spec.get("align", "left"), "valign": spec.get("valign", "top")})
    c.save()
    return {"page_size": list(page_size), "entries": entries,
            "representative_signature": representative, "profile": pack["profile"]["version"]}
