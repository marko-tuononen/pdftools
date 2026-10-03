#!/usr/bin/env python3

import sys
from pathlib import Path
from pypdf import PdfWriter


def parse_cli_arguments():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input_pdf_1> [input_pdf_2 ...] <output_pdf>")
        sys.exit(1)

    return [Path(p) for p in sys.argv[1:-1]], Path(sys.argv[-1])


def concatenate_pdfs(input_filepaths, output_filepath):
    merger = PdfWriter()
    successful_appends = []
    failed_appends = []

    print(f"Attempting to concatenate PDFs to: {output_filepath}")
    print("---")

    for pdf_path in input_filepaths:
        if not pdf_path.is_file():
            print(f"Warning: Input file not found - {pdf_path}")
            failed_appends.append(pdf_path)
            continue
        try:
            merger.append(str(pdf_path))
            print(f"Appended: {pdf_path}")
            successful_appends.append(pdf_path)
        except Exception as e:
            print(f"Error appending {pdf_path}: {e}")
            failed_appends.append(pdf_path)

    print("---")

    if not successful_appends:
        print("No PDFs were successfully appended. Output file will not be created.")
        merger.close()
        sys.exit(1)

    try:
        merger.write(str(output_filepath))
        merger.close()
        print(f"Successfully created concatenated PDF: {output_filepath}")
    except Exception as e:
        print(f"Error writing output PDF {output_filepath}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    concatenate_pdfs(*parse_cli_arguments())
