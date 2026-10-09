"""Synthetic checks: preserve the original masking logic after UI removal."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from pii_rules import Masker, nfc, read_text


class PrivacyRulesTests(unittest.TestCase):
    def test_original_rule_body_is_identical_except_final_blank_lines(self):
        source = (ROOT / "tools/pii_rules.py").read_text(encoding="utf-8")
        body = source.split("# 판정 규칙 원형\n", 1)[1]
        # Header editing may normalize final blank lines; all rule content stays exact.
        self.assertEqual(hashlib.sha256(body.rstrip().encode()).hexdigest(),
                         "a9ebfe5f9f0cd8cc21a7365071eee123c02dbf5aceaae8bb1f12eaf5a85a0fa4")

    def test_synthetic_identifiers_are_masked(self):
        samples = ["900101-1234567", "123-45-67890", "010-1234-5678",
                   "test@example.com", "1,234,000원", "M12345678"]
        for value in samples:
            with self.subTest(value=value):
                mask = Masker()
                result = mask(value)
                self.assertNotEqual(result, value)
                self.assertGreater(mask.total, 0)

    def test_synthetic_person_and_corporation_are_masked(self):
        for value in ["김철수 대표", "(주)예시상사", "NGUYEN VAN A", "王小明_비자.pdf"]:
            mask = Masker()
            self.assertNotEqual(mask(value), value)

    def test_turning_off_name_guess_keeps_strong_rules(self):
        mask = Masker(guess_names=False)
        self.assertEqual(mask("김철수 대표"), "김철수 대표")
        self.assertEqual(mask("010-1234-5678"), "010-****-****")

    def test_normalization_and_read_only_helpers(self):
        self.assertEqual(nfc(unicodedata.normalize("NFD", "자료실")), "자료실")
        with tempfile.TemporaryDirectory(prefix="pii_rules_") as folder:
            file = Path(folder) / "synthetic.txt"
            file.write_text("합성 fixture", encoding="utf-8")
            before = file.stat().st_mtime_ns
            self.assertEqual(read_text(file), "합성 fixture")
            self.assertEqual(file.stat().st_mtime_ns, before)
            self.assertIsNone(read_text(Path(folder) / "absent.txt"))


if __name__ == "__main__":
    unittest.main()
