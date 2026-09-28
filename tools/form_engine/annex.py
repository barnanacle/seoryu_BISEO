"""Fill a pack's DOCX annex template using confirmed field values."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from .pack import resolve_asset
from .transforms import UNKNOWN, normalize_fields


def _xml_lines(value):
    return '</w:t><w:br/><w:t xml:space="preserve">'.join(escape(line) for line in str(value).split("\n"))


def build_annex_docx(fields: dict, out_path: str | Path, pack: dict) -> Path | None:
    annexes = pack.get("annexes", [])
    if not annexes or (len(annexes) == 1 and annexes[0]["type"] == "none"):
        return None
    if len(annexes) != 1:
        raise ValueError("현재는 꾸러미당 붙임 틀 하나를 지원합니다.")
    annex = annexes[0]
    if annex["type"] not in {"narrative", "list"}:
        raise ValueError("지원하지 않는 붙임 유형: " + annex["type"])
    values = normalize_fields(fields, pack)
    template = resolve_asset(pack, annex["template"])
    with zipfile.ZipFile(template) as source:
        xml = source.read("word/document.xml").decode()
    para_re = r"<w:p\b(?:(?!</w:p>).)*?</w:p>"
    paragraphs = re.findall(para_re, xml, flags=re.S)
    repeat = annex.get("repeat") if annex["type"] == "narrative" else None
    title = body = None
    if repeat:
        title_tag = "{{" + repeat["title_placeholder"] + "}}"
        body_tag = "{{" + repeat["body_placeholder"] + "}}"
        title = next((p for p in paragraphs if title_tag in p), None)
        body = next((p for p in paragraphs if body_tag in p), None)
        if title is None or body is None:
            raise ValueError("붙임 틀에 반복 제목·본문 표시가 없습니다.")
        item_fields = pack["fields"][repeat["field"]]["item_fields"]
    else:
        title_tag = body_tag = ""
        item_fields = []

    def replace(match):
        paragraph = match.group(0)
        if paragraph == body:
            return ""
        if paragraph == title:
            result = []
            for number, item in enumerate(values[repeat["field"]], 1):
                result.append(title.replace(title_tag, _xml_lines(str(number) + ". " + item[item_fields[0]])))
                result.extend(body.replace(body_tag, _xml_lines(block))
                              for block in re.split(r"\n\s*\n", item[item_fields[1]].strip()))
            return "".join(result) or body.replace(body_tag, UNKNOWN)
        keys = re.findall(r"\{\{([^{}]+)\}\}", paragraph)
        if not keys:
            return paragraph
        key = keys[0]
        value = str(values.get(key, UNKNOWN))
        if key in annex.get("list_fields", []):
            blocks = [line for line in value.split("\n") if line.strip()]
            pieces = []
            keep_last = int(annex.get("keep_last_list_items", 0))
            for index, block in enumerate(blocks):
                copy = paragraph
                if index >= max(0, len(blocks) - keep_last):
                    if "<w:keepNext" in copy:
                        copy = re.sub(r"<w:keepNext[^>]*/>", "<w:keepNext/>", copy)
                    else:
                        copy = copy.replace("<w:pPr>", "<w:pPr><w:keepNext/>", 1)
                pieces.append(re.sub(r"\{\{([^{}]+)\}\}",
                                     lambda token: _xml_lines(block if token.group(1) == key
                                                              else values.get(token.group(1), UNKNOWN)), copy))
            return "".join(pieces)
        blocks = (re.split(r"\n\s*\n", value.strip())
                  if key in annex.get("paragraph_fields", []) else [value])
        return "".join(re.sub(r"\{\{([^{}]+)\}\}",
                              lambda token: _xml_lines(block if token.group(1) == key
                                                       else values.get(token.group(1), UNKNOWN)), paragraph)
                       for block in blocks)

    xml = re.sub(para_re, replace, xml, flags=re.S)
    out_path = Path(out_path)
    with zipfile.ZipFile(template) as source, zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            target.writestr(item, xml.encode() if item.filename == "word/document.xml"
                            else source.read(item.filename))
    return out_path
