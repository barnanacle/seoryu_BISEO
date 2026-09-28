"""Public/fictitious form-pack smoke and safety checks."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "opinion_writer/bin"))

from document_runtime import bootstrap
from form_engine.engine import build
from form_engine.pack import load_pack, resolve_asset
from form_engine.transforms import normalize_fields


class FormPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bootstrap()

    def test_two_packs_load_and_keep_official_pdf_hash(self):
        for name in ("opinion_notice_11", "cosmetics_seller_registration"):
            pack = load_pack(name)
            source = resolve_asset(pack, pack["files"]["form_pdf"])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), pack["form_sha256"])

    def test_pack_asset_cannot_escape(self):
        pack = load_pack("cosmetics_seller_registration")
        with self.assertRaises(ValueError):
            resolve_asset(pack, "../../escape.pdf")

    def test_defined_field_values_must_be_strings(self):
        pack = load_pack("cosmetics_seller_registration")
        with self.assertRaises(ValueError):
            normalize_fields({"신청인_성명": ["홍길동"]}, pack)

    def test_list_pack_build_preserves_two_official_pages(self):
        from pypdf import PdfReader
        pack = load_pack("cosmetics_seller_registration")
        sample = json.loads((Path(pack["_root"]) / "examples/fields.sample.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="form_pack_test_") as temporary:
            result = build(sample, pack, temporary, no_open=True)
            self.assertTrue(result["layout_passed"])
            self.assertEqual(len(PdfReader(result["pdf"]).pages), 2)
            self.assertTrue(Path(result["docx"]).is_file())
            self.assertTrue(Path(result["full_docx"]).is_file())
            self.assertEqual(result["mode"], "vector")

    def test_none_annex_pack_builds_without_extra_page(self):
        from pypdf import PdfReader
        pack = copy.deepcopy(load_pack("cosmetics_seller_registration"))
        pack["annexes"] = [{"type": "none"}]
        sample = json.loads((Path(pack["_root"]) / "examples/fields.sample.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="form_pack_test_") as temporary:
            result = build(sample, pack, temporary, no_open=True)
            self.assertIsNone(result["docx"])
            self.assertEqual(len(PdfReader(result["pdf"]).pages), 2)

    def test_unknown_official_form_change_stops(self):
        pack = load_pack("cosmetics_seller_registration")
        sample = json.loads((Path(pack["_root"]) / "examples/fields.sample.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="form_pack_test_") as temporary:
            alternate = Path(temporary) / "changed.pdf"
            alternate.write_bytes(resolve_asset(pack, pack["files"]["form_pdf"]).read_bytes() + b"modified")
            with self.assertRaisesRegex(ValueError, "공식 서식 원본"):
                build(sample, pack, temporary, no_open=True, asset_overrides={"form_pdf": alternate})


if __name__ == "__main__":
    unittest.main()
