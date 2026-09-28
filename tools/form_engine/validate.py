"""Validate a rendered pack without assuming a particular form's field names."""
from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path


def validate_pack(docx_path, merged_pdf, cover_pages, fields, output_report, *,
                  pack, overlays=(), repeat=True, cover_pdf=None, append_annex=True):
    from validate_layout import check_overlay, compare_images, validate as validate_opinion
    from document_runtime import convert_docx, render_pdf, sha256, temp_root
    from pypdf import PdfReader

    if pack["validation"]["type"] == "opinion_precise":
        return validate_opinion(docx_path, merged_pdf, cover_pages, fields, output_report,
                                overlays=overlays, repeat=repeat, cover_pdf=cover_pdf,
                                profile=pack["profile"])
    if pack["validation"]["type"] != "basic":
        raise ValueError("지원하지 않는 검증 방식: " + pack["validation"]["type"])
    result = {"profile": pack["profile"]["version"], "form_sha256": pack["form_sha256"],
              "docx_sha256": sha256(docx_path) if docx_path else None,
              "pdf_sha256": sha256(merged_pdf),
              "cover_pages": cover_pages, "errors": [], "warnings": [], "form": [],
              "page_comparison": []}
    errors = result["errors"]
    if docx_path:
        with zipfile.ZipFile(docx_path) as archive:
            xml = archive.read("word/document.xml").decode()
        if "{{" in xml or "}}" in xml:
            errors.append("붙임 DOCX에 치환되지 않은 필드가 있습니다.")
    for overlay, placement in overlays:
        problems, positions = check_overlay(overlay, placement)
        errors.extend(problems)
        result["form"].extend(positions)
    with tempfile.TemporaryDirectory(prefix="pack_check_", dir=temp_root()) as directory:
        tmp = Path(directory)
        fresh = tmp / "annex.pdf"
        result["conversion"] = convert_docx(Path(docx_path), fresh) if docx_path else None
        actual = PdfReader(merged_pdf)
        result["annex_pages"] = len(PdfReader(fresh).pages) if docx_path else 0
        expected_pages = cover_pages + (result["annex_pages"] if append_annex else 0)
        if len(actual.pages) != expected_pages:
            errors.append("최종 PDF 쪽수가 꾸러미 정의와 다릅니다.")
        for index, page in enumerate(actual.pages[:cover_pages]):
            source = pack["pages"][index]
            size = source.get("size") or [float(page.mediabox.width), float(page.mediabox.height)]
            if abs(float(page.mediabox.width)-size[0]) > .1 or abs(float(page.mediabox.height)-size[1]) > .1:
                errors.append("공식 서식 쪽 크기가 다릅니다: " + str(index + 1))
        if cover_pdf:
            actual_cover = render_pdf(Path(merged_pdf), tmp / "merged_cover", dpi=120,
                                      first=1, last=cover_pages)
            expected_cover = render_pdf(Path(cover_pdf), tmp / "expected_cover", dpi=120)
            result["cover_comparison"] = [compare_images(a, b) for a, b in zip(actual_cover, expected_cover)]
            if len(actual_cover) != len(expected_cover) or any(not item["equal"] for item in result["cover_comparison"]):
                errors.append("합본 표지가 확인한 공식 서식과 다릅니다.")
        if append_annex and docx_path and len(actual.pages) == expected_pages:
            actual_annex = render_pdf(Path(merged_pdf), tmp / "merged_annex", dpi=120,
                                      first=cover_pages + 1)
            expected_annex = render_pdf(fresh, tmp / "fresh_annex", dpi=120)
            result["page_comparison"] = [compare_images(a, b) for a, b in zip(actual_annex, expected_annex)]
            if len(actual_annex) != len(expected_annex) or any(not item["equal"] for item in result["page_comparison"]):
                errors.append("붙임 DOCX와 최종 PDF의 렌더 픽셀이 다릅니다.")
        if repeat and docx_path:
            again = tmp / "repeat.pdf"
            convert_docx(Path(docx_path), again)
            first_images = render_pdf(fresh, tmp / "first", dpi=120)
            second_images = render_pdf(again, tmp / "second", dpi=120)
            result["repeat_comparison"] = [compare_images(a, b) for a, b in zip(first_images, second_images)]
            if len(first_images) != len(second_images) or any(not item["equal"] for item in result["repeat_comparison"]):
                errors.append("같은 DOCX의 반복 변환 결과가 다릅니다.")
    result["passed"] = not errors
    Path(output_report).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
