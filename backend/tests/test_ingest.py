import unittest

from helpers import BACKEND  # noqa: F401
from app.ml.errors import DataValidationError
from app.ml.ingest import load_csv_bytes, sanitize_cell, to_safe_csv
import pandas as pd


class IngestTests(unittest.TestCase):
    def test_valid_csv(self):
        df = load_csv_bytes(b"a,b\n1,x\n2,y\n")
        self.assertEqual(df.shape, (2, 2))

    def test_utf8_bom_and_spaces_in_header(self):
        df = load_csv_bytes("\ufeff a , b \n1,2\n".encode("utf-8"))
        self.assertEqual(list(df.columns), ["a", "b"])

    def test_rejections(self):
        cases = {
            "empty_file": b"",
            "empty_file ": b"   \n  ",
            "no_rows": b"a,b\n",
            "duplicate_columns": b"a,a\n1,2\n",
            "bad_header": b"a,,c\n1,2,3\n",
            "not_text": b"\x00\x01\x02binary",
            "bad_encoding": b"a,b\n\xff\xfe,1\n",
        }
        for expected, content in cases.items():
            with self.subTest(expected):
                with self.assertRaises(DataValidationError) as ctx:
                    load_csv_bytes(content)
                self.assertEqual(ctx.exception.code, expected.strip())

    def test_oversized_upload_rejected(self):
        with self.assertRaises(DataValidationError) as ctx:
            load_csv_bytes(b"a\n" + b"1\n" * 100, max_bytes=50)
        self.assertEqual(ctx.exception.code, "file_too_large")

    def test_row_and_column_limits(self):
        with self.assertRaises(DataValidationError) as ctx:
            load_csv_bytes(b"a\n" + b"1\n" * 20, max_rows=10)
        self.assertEqual(ctx.exception.code, "too_many_rows")
        with self.assertRaises(DataValidationError) as ctx:
            load_csv_bytes(b"a,b,c\n1,2,3\n", max_cols=2)
        self.assertEqual(ctx.exception.code, "too_many_columns")

    def test_malformed_csv(self):
        with self.assertRaises(DataValidationError):
            load_csv_bytes(b'a,b\n1,2,3,4,5\n"unterminated,1\n')


class CsvInjectionTests(unittest.TestCase):
    def test_formula_cells_are_neutralised(self):
        for payload in ["=1+1", "+cmd", "-2+3", "@SUM(A1)"]:
            self.assertTrue(sanitize_cell(payload).startswith("'"))
        self.assertEqual(sanitize_cell("hello"), "hello")

    def test_to_safe_csv_keeps_numbers_untouched(self):
        df = pd.DataFrame({"name": ["=HYPERLINK(1)", "ok"], "value": [-5, 3]})
        text = to_safe_csv(df)
        self.assertIn("'=HYPERLINK(1)", text)
        self.assertIn("-5", text)
        self.assertNotIn("'-5", text)


if __name__ == "__main__":
    unittest.main()
