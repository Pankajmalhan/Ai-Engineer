from pathlib import Path

import pytest

from app.loaders import SUPPORTED_EXTENSIONS, load_directory, load_file

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_load_directory_loads_every_supported_format():
    docs = load_directory(FIXTURES_DIR)
    formats = {d.format for d in docs}
    assert formats == {"md", "html", "docx", "pdf"}


def test_markdown_loading_preserves_content():
    doc = load_file(FIXTURES_DIR / "sample.md")
    assert doc.format == "md"
    assert "thirty days" in doc.text
    assert "billing portal" in doc.text


def test_html_loading_strips_tags_but_keeps_text():
    doc = load_file(FIXTURES_DIR / "sample.html")
    assert doc.format == "html"
    assert "<h1>" not in doc.text
    assert "New Engineer Onboarding" in doc.text
    assert "VPN setup" in doc.text


def test_docx_loading_extracts_paragraphs():
    doc = load_file(FIXTURES_DIR / "sample.docx")
    assert doc.format == "docx"
    assert "Incident Response Runbook" in doc.text
    assert "on-call engineer" in doc.text


def test_digital_pdf_loading_extracts_text_without_ocr():
    doc = load_file(FIXTURES_DIR / "sample_digital.pdf", pdf_strategy="fast")
    assert doc.format == "pdf"
    assert "Quarterly Infrastructure Report" in doc.text


def test_load_file_rejects_unsupported_extension(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(ValueError, match="Unsupported file type"):
        load_file(bad)


def test_supported_extensions_cover_the_weekly_goal_formats():
    assert set(SUPPORTED_EXTENSIONS.values()) == {"pdf", "html", "docx", "md"}
