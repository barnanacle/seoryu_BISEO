"""Fictitious pack checks: the example opinion form is not a pack-count limit."""
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "opinion_writer/bin"))

from document_runtime import bootstrap
from form_engine.engine import build
from form_engine.pack import PACKS_ROOT, load_pack, resolve_asset
from form_engine.transforms import normalize_fields


class OpinionPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bootstrap()

    def test_example_opinion_form_is_unchanged_without_removed_pack(self):
        # Keep the retired identifier out of user-facing source searches.
        removed_id = "cos" + "metics_seller_registration"
        self.assertFalse((PACKS_ROOT / removed_id).exists())
        pack = load_pack("opinion_notice_11")
        source = resolve_asset(pack, pack["files"]["form_pdf"])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), pack["form_sha256"])

    def test_pack_asset_cannot_escape(self):
        pack = load_pack("opinion_notice_11")
        with self.assertRaises(ValueError):
            resolve_asset(pack, "../../escape.pdf")

    def test_defined_field_values_must_be_strings(self):
        pack = load_pack("opinion_notice_11")
        with self.assertRaises(ValueError):
            normalize_fields({"의견제출인_성명": ["가상 신청인"]}, pack)

    def test_opinion_sample_builds_pdf_and_editable_documents(self):
        from pypdf import PdfReader
        pack = load_pack("opinion_notice_11")
        sample = json.loads(
            (Path(pack["_root"]) / "examples/fields.sample.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory(prefix="opinion_pack_test_") as temporary:
            result = build(sample, pack, temporary, no_open=True)
            self.assertTrue(result["layout_passed"])
            self.assertGreaterEqual(len(PdfReader(result["pdf"]).pages), 2)
            self.assertTrue(Path(result["docx"]).is_file())
            self.assertTrue(Path(result["full_docx"]).is_file())
            self.assertEqual(result["mode"], "vector")

    def test_changed_official_form_stops(self):
        pack = load_pack("opinion_notice_11")
        sample = json.loads(
            (Path(pack["_root"]) / "examples/fields.sample.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory(prefix="opinion_pack_test_") as temporary:
            changed = Path(temporary) / "changed.pdf"
            changed.write_bytes(resolve_asset(pack, pack["files"]["form_pdf"]).read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "공식 서식 원본"):
                build(sample, pack, temporary, no_open=True, asset_overrides={"form_pdf": changed})

    def _synthetic_pack(self, directory, annex_type):
        """Keep the public opinion PDF, but never create another real-law pack."""
        original = load_pack("opinion_notice_11")
        pack = copy.deepcopy(original)
        root = Path(directory) / "synthetic"
        root.mkdir()
        for relative in ("form/official_form.pdf", "form/official_form_background.png"):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(resolve_asset(original, relative), destination)
        pack["_root"] = root
        pack["validation"] = {"type": "basic"}
        pack["profile"]["version"] = "synthetic-" + annex_type
        fonts = Path(original["_root"]) / "assets/fonts"
        if annex_type == "list":
            template = root / "annex/list_template.docx"
            template.parent.mkdir(parents=True, exist_ok=True)
            command = [
                sys.executable, str(TOOLS / "form_engine/bin/create_list_template.py"),
                "--out", str(template), "--title", "가상 확인표",
                "--intro", "테스트용 자료 목록입니다.",
                "--placeholder", "소명자료_목록",
                "--form-font", str(fonts / "NanumGothic-Regular.ttf"),
                "--body-font", str(fonts / "NanumMyeongjo-Regular.ttf"),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            pack["files"]["annex_docx"] = "annex/list_template.docx"
            pack["files"]["font_docx"] = "annex/list_template.docx"
            pack["annexes"] = [{
                "type": "list", "template": "annex/list_template.docx",
                "list_fields": ["소명자료_목록"], "append_to_submission": False,
            }]
        else:
            template = root / "form/blank_font_template.docx"
            subprocess.run([
                sys.executable, str(TOOLS / "form_engine/bin/create_font_template.py"),
                "--out", str(template),
                "--form-font", str(fonts / "NanumGothic-Regular.ttf"),
                "--body-font", str(fonts / "NanumMyeongjo-Regular.ttf"),
            ], check=True, capture_output=True, text=True)
            pack["files"].pop("annex_docx", None)
            pack["files"]["font_docx"] = "form/blank_font_template.docx"
            pack["annexes"] = [{"type": "none"}]
        sample = json.loads(
            (Path(original["_root"]) / "examples/fields.sample.json").read_text(encoding="utf-8")
        )
        return pack, sample

    def test_synthetic_list_annex_remains_separate(self):
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory(prefix="synthetic_list_pack_") as directory:
            pack, sample = self._synthetic_pack(directory, "list")
            result = build(sample, pack, Path(directory) / "output", no_open=True)
            self.assertTrue(result["layout_passed"])
            self.assertEqual(len(PdfReader(result["pdf"]).pages), 1)
            self.assertTrue(Path(result["docx"]).is_file())
            self.assertTrue(Path(result["full_docx"]).is_file())

    def test_synthetic_none_annex_has_no_extra_document(self):
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory(prefix="synthetic_none_pack_") as directory:
            pack, sample = self._synthetic_pack(directory, "none")
            result = build(sample, pack, Path(directory) / "output", no_open=True)
            self.assertTrue(result["layout_passed"])
            self.assertEqual(len(PdfReader(result["pdf"]).pages), 1)
            self.assertIsNone(result["docx"])
            self.assertTrue(Path(result["full_docx"]).is_file())


if __name__ == "__main__":
    unittest.main()
