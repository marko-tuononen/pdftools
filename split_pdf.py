#!/usr/bin/env python3
"""Split a PDF into named parts described by ordered, 1-based page ranges."""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError


def unique_parts(pairs):
    """Reject duplicate JSON keys instead of silently losing a part."""
    parts = {}
    for name, ranges in pairs:
        if name in parts:
            raise ValueError(f"Duplicate part name: {name!r}")
        parts[name] = ranges
    return parts


def load_split_structure(value):
    """Read an inline JSON object, a JSON file, or the original page count."""
    value = value.strip()
    if re.fullmatch(r"[+-]?[0-9]+", value):
        return int(value)
    if value.startswith(("{", "[")):
        source = value
    else:
        source = Path(value).read_text(encoding="utf-8-sig")
    try:
        return json.loads(source, object_pairs_hook=unique_parts)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid split JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}. "
            'Use an object like {"part1": ["1-10", "15"]}.'
        ) from exc


def parse_page_ranges(ranges, page_count, part_name):
    """Expand inclusive ranges to zero-based indices, retaining order/repeats."""
    if not isinstance(ranges, list) or not ranges:
        raise ValueError(f"Part {part_name!r} must contain a non-empty list of pages/ranges.")

    indices = []
    for item in ranges:
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            raise ValueError(f"Part {part_name!r}: expected a page number or range, got {item!r}.")
        match = re.fullmatch(r"\s*([0-9]+)(?:\s*-\s*([0-9]+))?\s*", str(item))
        if not match:
            raise ValueError(f"Part {part_name!r}: invalid range {item!r}; use '3' or '3-7'.")
        first = int(match.group(1))
        last = int(match.group(2) or match.group(1))
        if not 1 <= first <= last <= page_count:
            raise ValueError(
                f"Part {part_name!r}: range {item!r} must be ascending and within "
                f"1-{page_count}."
            )
        indices.extend(range(first - 1, last))
    return indices


def validate_parts(structure, page_count):
    """Validate every part before creating any output files."""
    if type(structure) is int:
        if not 1 <= structure < page_count:
            raise ValueError(f"The first-part page count must be between 1 and {page_count - 1}.")
        structure = {
            "first": [f"1-{structure}"],
            "second": [f"{structure + 1}-{page_count}"],
        }
    if not isinstance(structure, dict) or not structure:
        raise ValueError("The split structure must be a non-empty JSON object of named parts.")

    parts = {}
    used_names = set()
    for name, ranges in structure.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
            raise ValueError(
                f"Invalid part name {name!r}: start with a letter or digit and use only "
                "ASCII letters, digits, hyphens, and underscores."
            )
        if name.casefold() in used_names:
            raise ValueError(f"Part names must be distinct even ignoring case: {name!r}.")
        used_names.add(name.casefold())
        parts[name] = parse_page_ranges(ranges, page_count, name)
    return parts


def split_pdf(input_pdf, structure, output_dir=Path("."), *, force=False):
    """Write named PDF parts and return their paths. The source is never replaced."""
    input_path = Path(input_pdf)
    output_dir = Path(output_dir)
    with input_path.open("rb") as source:
        reader = PdfReader(source)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported; provide an unencrypted copy.")
        if not reader.pages:
            raise ValueError("The input PDF contains no pages.")
        parts = validate_parts(structure, len(reader.pages))
        outputs = [output_dir / f"{input_path.stem}-{name}.pdf" for name in parts]

        for output in outputs:
            if output.resolve() == input_path.resolve() or (
                output.exists() and output.samefile(input_path)
            ):
                raise ValueError(f"An output would replace the input PDF: {output}")
            if output.is_dir():
                raise ValueError(f"An output path is a directory: {output}")
            if os.path.lexists(output) and not force:
                raise FileExistsError(f"Output already exists: {output}. Use --force to replace it.")

        output_dir.mkdir(parents=True, exist_ok=True)
        # Stage every PDF first so parsing/writing failures leave existing outputs alone.
        with tempfile.TemporaryDirectory(prefix=".split-pdf-", dir=output_dir) as temporary:
            staged = []
            for output, indices in zip(outputs, parts.values()):
                with PdfWriter() as writer:
                    for index in indices:
                        writer.add_page(reader.pages[index])
                    writer.metadata = reader.metadata
                    if reader.xmp_metadata is not None:
                        writer.xmp_metadata = reader.xmp_metadata
                    path = Path(temporary) / output.name
                    writer.write(path)
                    staged.append(path)

            for path, output in zip(staged, outputs):
                if force:
                    os.replace(path, output)
                else:
                    # Same-directory hard links publish complete files without clobbering
                    # a file that appeared after the initial existence check.
                    os.link(path, output)
    return outputs


def parse_cli_arguments(argv=None):
    parser = argparse.ArgumentParser(
        description="Split a PDF into named parts using inclusive, 1-based page ranges.",
        epilog=(
            "Examples:\n"
            "  %(prog)s book.pdf splits.json\n"
            "  %(prog)s book.pdf '{\"part1\": [\"1-10\"], \"part2\": [\"11-12\", 15]}'\n"
            "  %(prog)s book.pdf 10  # original first/second split\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input_pdf", type=Path, help="PDF to split")
    parser.add_argument("splits", help="JSON file, inline JSON object, or first-part page count")
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=Path("."),
        help="output folder (default: current working directory)",
    )
    parser.add_argument("--force", action="store_true", help="replace existing output files")
    return parser, parser.parse_args(argv)


def main(argv=None):
    parser, args = parse_cli_arguments(argv)
    try:
        structure = load_split_structure(args.splits)
        outputs = split_pdf(args.input_pdf, structure, args.output_dir, force=args.force)
    except (OSError, ValueError, PyPdfError) as exc:
        parser.exit(1, f"{parser.prog}: error: {exc}\n")
    for output in outputs:
        print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
