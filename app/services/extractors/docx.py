from pathlib import Path
from app.core.exceptions import DocumentExtractionError
from docx import Document


def extract_docx(file_path: Path) -> str:
  """Extracts paragraphs and table rows from a DOCX financial statement."""
  try:
    doc = Document(str(file_path))
    lines: list[str] = []

    for paragraph in doc.paragraphs:
      text = paragraph.text.strip()
      if text:
        lines.append(text)

    for table in doc.tables:
      for row in table.rows:
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        if any(cells):
          lines.append(" | ".join(cells))

    combined = "\n".join(lines).strip()
    if not combined:
      raise DocumentExtractionError(
          file_path.name, "DOCX document contains no readable text."
      )
    return combined
  except DocumentExtractionError:
    raise
  except Exception as exc:
    raise DocumentExtractionError(
        file_path.name, f"Corrupted or unreadable DOCX ({type(exc).__name__})."
    ) from exc