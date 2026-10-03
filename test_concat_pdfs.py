"""Check the existing concatenation command against the shared pypdf dependency."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from test_split_pdf import make_pdf


SCRIPT = Path(__file__).with_name("concat_pdfs.py")


class ConcatPdfTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.first = self.root / "first.pdf"
        self.second = self.root / "second.pdf"
        self.output = self.root / "combined.pdf"
        make_pdf(self.first, count=3)
        make_pdf(self.second, count=2)

    def cli(self, *inputs):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, inputs), str(self.output)],
            cwd=self.root, text=True, capture_output=True,
        )

    def test_concatenates_inputs_in_argument_order(self):
        result = self.cli(self.second, self.first)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        reader = PdfReader(self.output)
        self.assertEqual([page.extract_text() for page in reader.pages],
                         ["Page 1", "Page 2", "Page 1", "Page 2", "Page 3"])
        self.assertEqual([page.rotation for page in reader.pages], [0, 90, 0, 90, 0])

    def test_skips_missing_and_unreadable_inputs(self):
        corrupt = self.root / "broken.pdf"
        corrupt.write_text("not a PDF", encoding="utf-8")
        result = self.cli(self.root / "missing.pdf", corrupt, self.second)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Input file not found", result.stdout)
        self.assertIn("Error appending", result.stdout)
        self.assertEqual(len(PdfReader(self.output).pages), 2)

    def test_no_valid_inputs_leaves_no_output(self):
        result = self.cli(self.root / "missing.pdf")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertIn("No PDFs were successfully appended", result.stdout)

    def test_missing_arguments_print_usage(self):
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Usage:", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
