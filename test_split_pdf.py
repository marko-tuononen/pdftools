"""Regression tests using real, labelled PDFs generated with pypdf only."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from pypdf.xmp import XmpInformation

from split_pdf import load_split_structure, split_pdf


SCRIPT = Path(__file__).with_name("split_pdf.py")


def make_pdf(path, count=200, *, metadata=True, encrypted=False):
    with PdfWriter() as writer:
        for number in range(1, count + 1):
            page = writer.add_blank_page(width=300 + number, height=400)
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({
                    NameObject("/F1"): DictionaryObject({
                        NameObject("/Type"): NameObject("/Font"),
                        NameObject("/Subtype"): NameObject("/Type1"),
                        NameObject("/BaseFont"): NameObject("/Helvetica"),
                    }),
                }),
            })
            content = DecodedStreamObject()
            content.set_data(f"BT /F1 24 Tf 30 340 Td (Page {number}) Tj ET".encode())
            page[NameObject("/Contents")] = content
            if number == 2:
                page.rotate(90)
        writer.metadata = {"/Title": "Test source", "/Author": "Tester", "/Custom": "Value"} if metadata else None
        if metadata:
            xmp = XmpInformation.create()
            xmp.dc_title = {"x-default": "XMP title"}
            writer.xmp_metadata = xmp
        if encrypted:
            writer.encrypt("secret", algorithm="RC4-128")
        writer.write(path)


class SplitPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.source = Path(cls.fixture.name) / "book.pdf"
        make_pdf(cls.source)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "parts"

    def assert_pages(self, path, expected):
        reader = PdfReader(path)
        self.assertEqual(len(reader.pages), len(expected))
        self.assertEqual([page.extract_text() for page in reader.pages], [f"Page {n}" for n in expected])
        self.assertEqual([int(page.mediabox.width) for page in reader.pages], [300 + n for n in expected])
        self.assertEqual([page.rotation for page in reader.pages], [90 if n == 2 else 0 for n in expected])
        return reader

    def cli(self, *arguments, cwd=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            cwd=cwd or self.root, text=True, capture_output=True,
        )

    def test_exact_requested_example_and_metadata(self):
        structure = load_split_structure(str(SCRIPT.with_name("splits.example.json")))
        paths = split_pdf(self.source, structure, self.output)
        self.assertEqual([p.name for p in paths], ["book-part1.pdf", "book-part2.pdf"])
        self.assert_pages(paths[0], list(range(1, 171)))
        reader = self.assert_pages(paths[1], [171, 172, 181, 182, 189, 190, 199, 200])
        self.assertEqual(reader.metadata, PdfReader(self.source).metadata)
        self.assertEqual(reader.xmp_metadata.dc_title, {"x-default": "XMP title"})
        self.assertEqual(reader.xmp_metadata.stream.get_data(), PdfReader(self.source).xmp_metadata.stream.get_data())

    def test_three_parts_preserve_order_and_repeats(self):
        paths = split_pdf(self.source, {
            "reordered": ["8-9", "1-2", 2], "shared": ["2", " 10 - 11 "], "last": [200],
        }, self.output)
        self.assertEqual(len(paths), 3)
        for path, expected in zip(paths, [[8, 9, 1, 2, 2], [2, 10, 11], [200]]):
            self.assert_pages(path, expected)

    def test_invalid_later_part_writes_nothing(self):
        for ranges in [[], [0], [201], ["3-2"], ["0-2"], ["1-201"], ["1-9999999999999999999"],
                       ["2-"], ["-2"], ["1,2"], ["x"], [True], [1.2], [None], [{}], "1-2"]:
            with self.subTest(ranges=ranges), self.assertRaises(ValueError):
                split_pdf(self.source, {"good": [1], "bad": ranges}, self.output)
            self.assertFalse(self.output.exists())

    def test_invalid_structures_and_names(self):
        invalid = [None, True, [], {}, {"../escape": [1]}, {"/absolute": [1]},
                   {"a/b": [1]}, {"a\\b": [1]}, {"": [1]}, {"has space": [1]},
                   {"a": [1], "A": [2]}]
        for structure in invalid:
            with self.subTest(structure=structure), self.assertRaises(ValueError):
                split_pdf(self.source, structure, self.output)
            self.assertFalse(self.output.exists())

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate part name"):
            load_split_structure('{"part": [1], "part": [2]}')

    def test_legacy_cli(self):
        result = self.cli(self.source, "170")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_pages(self.root / "book-first.pdf", list(range(1, 171)))
        self.assert_pages(self.root / "book-second.pdf", list(range(171, 201)))

    def test_invalid_legacy_counts(self):
        for count in [-1, 0, 200, 201]:
            with self.subTest(count=count), self.assertRaises(ValueError):
                split_pdf(self.source, count, self.output)
        self.assertFalse(self.output.exists())

    def test_json_file_cli_and_custom_output_dir(self):
        config = self.root / "split config.json"
        config.write_text(json.dumps({"one": [1], "two": [2], "three": [3]}), encoding="utf-8-sig")
        result = self.cli(self.source, config, "--output-dir", self.output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(list(self.output.glob("*.pdf"))), 3)
        self.assert_pages(self.output / "book-three.pdf", [3])

    def test_inline_json_cli_and_force(self):
        args = [self.source, '{"one": [1]}']
        first = self.cli(*args)
        self.assertEqual(first.returncode, 0, first.stderr)
        refused = self.cli(*args)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("already exists", refused.stderr)
        self.assertNotIn("Traceback", refused.stderr)
        replaced = self.cli(self.source, '{"one": [2]}', "--force")
        self.assertEqual(replaced.returncode, 0, replaced.stderr)
        self.assert_pages(self.root / "book-one.pdf", [2])

    def test_existing_later_output_prevents_all_writes(self):
        self.output.mkdir()
        existing = self.output / "book-second.pdf"
        existing.write_bytes(b"keep this file")
        with self.assertRaises(FileExistsError):
            split_pdf(self.source, {"first": [1], "second": [2]}, self.output)
        self.assertEqual(existing.read_bytes(), b"keep this file")
        self.assertFalse((self.output / "book-first.pdf").exists())

    def test_missing_metadata(self):
        source = self.root / "no-metadata.pdf"
        make_pdf(source, count=1, metadata=False)
        paths = split_pdf(source, {"only": [1]}, self.output)
        reader = self.assert_pages(paths[0], [1])
        self.assertIsNone(reader.metadata)
        self.assertIsNone(reader.xmp_metadata)

    def test_cli_errors_are_readable(self):
        corrupt = self.root / "corrupt.pdf"
        corrupt.write_text("not a PDF")
        for source, spec in [(self.source, '{"a": {"1-2"}}'),
                             (self.source, "missing.json"),
                             (self.root / "missing.pdf", '{"a": [1]}'),
                             (corrupt, '{"a": [1]}')]:
            with self.subTest(source=source, spec=spec):
                result = self.cli(source, spec)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("error:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_empty_and_encrypted_pdf_errors(self):
        for count, encrypted, message in [(0, False, "no pages"), (1, True, "Encrypted")]:
            source = self.root / f"input-{count}.pdf"
            make_pdf(source, count=count, encrypted=encrypted)
            with self.assertRaisesRegex(ValueError, message):
                split_pdf(source, {"part": [1]}, self.output)
        self.assertFalse(self.output.exists())

    def test_source_alias_cannot_be_overwritten(self):
        self.output.mkdir()
        destination = self.output / "book-alias.pdf"
        destination.symlink_to(self.source)
        original = self.source.read_bytes()
        with self.assertRaisesRegex(ValueError, "replace the input"):
            split_pdf(self.source, {"alias": [1]}, self.output, force=True)
        self.assertEqual(self.source.read_bytes(), original)

    def test_staging_failure_preserves_existing_outputs(self):
        self.output.mkdir()
        existing = self.output / "book-first.pdf"
        existing.write_bytes(b"original")
        with patch("split_pdf.PdfWriter.write", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                split_pdf(self.source, {"first": [1], "second": [2]}, self.output, force=True)
        self.assertEqual(existing.read_bytes(), b"original")
        self.assertEqual(list(self.output.iterdir()), [existing])

    def test_publication_does_not_clobber_late_file(self):
        self.output.mkdir()
        destination = self.output / "book-one.pdf"
        original_write = PdfWriter.write

        def concurrent_write(writer, stream):
            result = original_write(writer, stream)
            destination.write_bytes(b"created during split")
            return result

        with patch("split_pdf.PdfWriter.write", concurrent_write):
            with self.assertRaises(FileExistsError):
                split_pdf(self.source, {"one": [1]}, self.output)
        self.assertEqual(destination.read_bytes(), b"created during split")


if __name__ == "__main__":
    unittest.main()
