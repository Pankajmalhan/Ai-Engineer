"""Loads PDFs (digital + scanned/OCR), HTML, DOCX, and Markdown into a single unified
list of RawDocument, all through Unstructured.io's `partition()` -- one call handles
every format via format-specific partitioners (pdfminer for PDF text, python-docx for
DOCX, lxml/bs4 for HTML, markdown-it for MD) and returns a flat list of typed Elements
(Title, NarrativeText, Table, ...) that we flatten back into plain text per document.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from unstructured.partition.auto import partition

from app.models import RawDocument

SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".html": "html",
    ".htm": "html",
    ".docx": "docx",
    ".md": "md",
}


def ocr_available() -> bool:
    """Scanned-PDF OCR (strategy='hi_res'/'ocr_only') needs Tesseract + Poppler on
    PATH; digital-text PDFs (strategy='fast', pdfminer only) don't."""
    return shutil.which("tesseract") is not None and shutil.which("pdftoppm") is not None


def load_file(path: str | Path, pdf_strategy: str = "fast") -> RawDocument:
    """pdf_strategy: 'fast' (pdfminer text extraction, no OCR, works on digital PDFs
    with zero system deps) or 'hi_res'/'ocr_only' (real OCR for scanned PDFs, requires
    ocr_available()). Ignored for non-PDF formats."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext} (supported: {sorted(SUPPORTED_EXTENSIONS)})")
    fmt = SUPPORTED_EXTENSIONS[ext]

    kwargs = {"strategy": pdf_strategy} if fmt == "pdf" else {}
    elements = partition(filename=str(path), **kwargs)
    print(elements)
    text = "\n\n".join(el.text for el in elements if getattr(el, "text", "") and el.text.strip())
    return RawDocument(id=path.stem, source_path=str(path), format=fmt, text=text)


def load_directory(dir_path: str | Path, pdf_strategy: str = "fast") -> list[RawDocument]:
    """Walks dir_path, loading every supported file into one unified list, in the
    format LlamaIndex's SimpleDirectoryReader is often reached for -- unstructured's
    partition() is used directly instead since it already normalizes every format to
    the same Element/text shape without a second abstraction layer on top."""
    dir_path = Path(dir_path)
    docs = []
    for path in sorted(dir_path.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            docs.append(load_file(path, pdf_strategy=pdf_strategy))
    return docs
