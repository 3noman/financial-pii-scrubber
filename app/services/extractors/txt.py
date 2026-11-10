from pathlib import Path
from app.core.exceptions import DocumentExtractionError

ENCODINGS_TO_TRY = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def read_text_with_fallback(file_path: Path) -> str:
  """Reads a text file using pathlib and falls back through standard encodings."""
  raw_bytes = file_path.read_bytes()
  for encoding in ENCODINGS_TO_TRY:
    try:
      return raw_bytes.decode(encoding)
    except UnicodeDecodeError:
      continue
  raise DocumentExtractionError(
      file_path.name, "Unsupported character encoding."
  )


def extract_txt(file_path: Path) -> str:
  """Extracts text from a plain TXT financial statement."""
  try:
    text = read_text_with_fallback(file_path).strip()
    if not text:
      raise DocumentExtractionError(
          file_path.name, "TXT file contains only whitespace."
      )
    return text
  except DocumentExtractionError:
    raise
  except Exception as exc:
    raise DocumentExtractionError(
        file_path.name, f"Could not read TXT ({type(exc).__name__})."
    ) from exc