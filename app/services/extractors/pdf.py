from pathlib import Path
from app.core.exceptions import DocumentExtractionError
import pdfplumber


def extract_pdf(file_path: Path) -> str:
  """Extracts text and tabular transaction rows from a PDF statement using pdfplumber."""
  try:
    extracted_pages: list[str] = []
    with pdfplumber.open(file_path) as pdf:
      if not pdf.pages:
        raise DocumentExtractionError(
            file_path.name, "PDF contains no pages."
        )

      for page_num, page in enumerate(pdf.pages, start=1):
        page_text = (page.extract_text(layout=False) or "").strip()
        if page_text:
          extracted_pages.append(page_text)
        else:
          # Fallback to table extraction if standard text extraction returns empty
          tables = page.extract_tables()
          for table in tables:
            for row in table:
              cleaned_row = [str(cell).strip() for cell in row if cell]
              if cleaned_row:
                extracted_pages.append(" | ".join(cleaned_row))

    combined = "\n".join(extracted_pages).strip()
    if not combined:
      raise DocumentExtractionError(
          file_path.name,
          "No readable text found in PDF (it may be an image-only scan).",
      )
    return combined
  except DocumentExtractionError:
    raise
  except Exception as exc:
    raise DocumentExtractionError(
        file_path.name, f"Corrupted or unreadable PDF ({type(exc).__name__})."
    ) from exc