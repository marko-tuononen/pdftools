# pdftools

Small Python command-line utilities for splitting and concatenating PDF files.

- `split_pdf.py` extracts named parts using ordered, inclusive page ranges.
- `concat_pdfs.py` combines PDF files in the order provided.

## Setup

Requires Python 3.10 or newer. From the repository folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\Activate.ps1` in
PowerShell instead. Both utilities use
[`pypdf`](https://pypdf.readthedocs.io/en/stable/).

## Split a PDF

```sh
python split_pdf.py book.pdf splits.example.json
```

### Define your parts

Use a JSON object with a list of page ranges for each output name:

```json
{
  "part1": ["1-170"],
  "part2": ["171-172", "181-182", "189-190", "199-200"],
  "selected": ["5", 12, "20-23"]
}
```

For `book.pdf`, this produces `book-part1.pdf`, `book-part2.pdf`, and
`book-selected.pdf` in the current working directory. The bundled example contains
two sample parts and requires at least 200 input pages.

- Page numbers start at **1**, and range endpoints are **inclusive**. These are
  physical PDF page positions, not printed page numbers or custom PDF page labels.
- Each value is a JSON array (`[...]`), not a Python set (`{...}`), so order is
  explicit. For example, `["8-9", "1-2"]` outputs pages 8, 9, 1, 2 in that order.
- Individual pages can be strings or integers. Ranges must be strings.
- You may reuse pages across parts. Repeated or overlapping entries within a part
  deliberately repeat those pages. Unlisted pages are omitted.
- Names start with an ASCII letter or digit and contain only ASCII letters,
  digits, hyphens, or underscores. Names must be unique ignoring case.
- Empty parts, reversed ranges, out-of-bounds pages, and duplicate JSON names
  produce an error before any output PDF is written.

### Other ways to run it

Pass JSON directly (the quoting below works in macOS/Linux shells):

```sh
python split_pdf.py book.pdf '{"intro": ["1-5"], "extracts": ["10-12", 20]}'
```

Choose an output folder; add `--force` when intentionally replacing existing files:

```sh
python split_pdf.py book.pdf splits.example.json --output-dir parts
python split_pdf.py book.pdf splits.example.json --output-dir parts --force
```

The original two-part command still works:

```sh
python split_pdf.py book.pdf 170
```

This creates `book-first.pdf` with pages 1-170 and `book-second.pdf` with the rest.
The count must leave at least one page in each output.

You can also import the function with a normal Python dictionary:

```python
from split_pdf import split_pdf

paths = split_pdf("book.pdf", {
    "part1": ["1-170"],
    "part2": ["171-172", "181-182", "189-190", "199-200"],
}, output_dir="parts")
```

### Splitter preservation and file handling

Selected pages retain their page contents, sizes, and rotation. The tool copies
both document information metadata and XMP metadata when present, using
[pypdf's metadata interfaces](https://pypdf.readthedocs.io/en/stable/user/metadata.html).
Missing metadata is supported. This is a page extraction utility: document-level
bookmarks, attachments, page labels, and interactive form structure are not copied.
Encrypted input PDFs are rejected with a clear error.

All ranges and existing destinations are checked first, and all PDFs are staged
before publishing. Each output is published as a complete file; existing files
are protected unless `--force` is supplied. The input PDF cannot be replaced.
Publishing the entire batch is not transactional: an operating-system failure
during publication can leave earlier parts in place. Default publication uses
hard links within the output folder, requiring a filesystem that supports them.

## Concatenate PDFs

```sh
python concat_pdfs.py cover.pdf report.pdf appendix.pdf combined.pdf
```

The final argument is the output filename. Inputs are appended in the order
provided. The concatenation utility reports and skips missing or unreadable
inputs, and fails if none can be appended. It replaces an existing output file,
so choose an output path distinct from your input files. This utility uses
[pypdf's PDF merging interface](https://pypdf.readthedocs.io/en/stable/user/merging-pdfs.html).

## Local files

`split_pdf.py` also accepts your own configuration, for example `splits.json`.
The `.gitignore` excludes that local configuration, PDF documents, temporary
outputs, virtual environments, and Python caches. The shared sample is
`splits.example.json`.

## Tests

```sh
python -m unittest discover -v
```

Tests generate their own PDFs in temporary folders; no real input PDF is needed.

The GitHub Actions workflow runs the tests on Linux with Python 3.10, 3.12,
and 3.14, and on macOS with Python 3.12, after pushes and pull requests.
