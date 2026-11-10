from pathlib import Path
from app.core.exceptions import DocumentExtractionError, FileValidationError
from app.core.security import sanitize_filename
from app.services.extractors import extract_document
from docx import Document
import pytest


def test_extract_txt_success(tmp_path: Path) -> None:
    txt_file = tmp_path / "statement.txt"
    txt_file.write_text("2026-10-01 | Foodpanda | PKR 1,450.00", encoding="utf-8")
    result = extract_document(txt_file)
    assert "Foodpanda" in result
    assert "PKR 1,450.00" in result


def test_extract_csv_with_cp1252_encoding(tmp_path: Path) -> None:
    csv_file = tmp_path / "uk_wallet.csv"
    # Write using Windows-1252 with British Pound symbol (£)
    csv_file.write_bytes(
        "Date,Merchant,Amount\n2026-10-05,TESCO STORES,£42.50\n".encode("cp1252")
    )
    result = extract_document(csv_file)
    assert "TESCO STORES" in result
    assert "£42.50" in result


def test_extract_docx_paragraphs_and_tables(tmp_path: Path) -> None:
    docx_file = tmp_path / "statement.docx"
    doc = Document()
    doc.add_paragraph("Account Holder: Ayesha Khan")
    table = doc.add_table(rows=1, cols=3)
    table.rows[0].cells[0].text = "2026-10-12"
    table.rows[0].cells[1].text = "Netflix.com"
    table.rows[0].cells[2].text = "USD 15.99"
    doc.save(str(docx_file))

    result = extract_document(docx_file)
    assert "Ayesha Khan" in result
    assert "Netflix.com" in result
    assert "USD 15.99" in result


def test_reject_empty_file(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("", encoding="utf-8")
    with pytest.raises(FileValidationError, match="empty"):
        extract_document(empty_file)


def test_reject_fake_pdf_signature(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_text("This is plain text pretending to be a PDF")
    with pytest.raises(FileValidationError, match="valid PDF file signature"):
        extract_document(fake_pdf)


def test_reject_corrupted_pdf_with_header(tmp_path: Path) -> None:
    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"%PDF-1.7\nbroken binary garbage")
    with pytest.raises(DocumentExtractionError, match="Corrupted or unreadable"):
        extract_document(corrupt_pdf)


def test_sanitize_filename_blocks_path_traversal() -> None:
    cleaned = sanitize_filename("../../Windows/System32/evil_statement.pdf")
    assert cleaned == "evil_statement.pdf"
