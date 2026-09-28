"""Checks for the sole shipped opinion-submission form pack."""
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
from form_engine.pack import PACKS_ROOT, load_pack, resolve_asset
from form_engine.transforms import normalize_fields


class OpinionPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bootstrap()

    def test_only_opinion_pack_is_shipped_and_original_is_unchanged(self):
        self.assertEqual(
            [path.parent.name for path in PACKS_ROOT.glob("*/pack.json")],
            ["opinion_notice_11"],
        )
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


if __name__ == "__main__":
    unittest.main()
