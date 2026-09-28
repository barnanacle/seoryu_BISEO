"""Compatibility functions for the opinion-notice pack layout."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))

from form_engine.layout import (
    create_overlay as _create_overlay,
    fit_text,
    font_registry as _font_registry,
    wrap_text,
)
from form_engine.pack import load_pack
from form_engine.transforms import form_values as _form_values, normalized_address

PACK = load_pack("opinion_notice_11")
PROFILE = HERE / "서식/layout_profile.json"
UNKNOWN = "【확인 필요】"


def font_registry(template: Path, directory: Path):
    return _font_registry(template, directory, PACK)


def form_values(fields):
    return _form_values(fields, PACK)


def create_overlay(fields, pdf_path, template, work_dir, custom_boxes=None,
                   page_size=(595, 842)):
    return _create_overlay(fields, pdf_path, template, work_dir, PACK,
                           custom_boxes, page_size)
