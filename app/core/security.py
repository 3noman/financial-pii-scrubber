from pathlib import Path
import re
import zipfile
from app.config import get_settings
from app.core.exceptions import FileValidationError

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".csv", ".txt"}
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\- ()]")


def sanitize_filename(filename: str) -> str:
  """Strips directory paths and unsafe characters to prevent path traversal."""
  if not filename or not filename.strip():
    raise FileValidationError("Filename cannot be empty.")

  # Extract only the base name (blocks ../ and C:\ traversal)
  clean_name = Path(filename).name.strip()
  clean_name = _SAFE_FILENAME_RE.sub("_", clean_name)

  # Prevent hidden dotfiles or empty names
  clean_name = clean_name.lstrip(".")
  if not clean_name or "." not in clean_name:
    raise FileValidationError("Please upload a valid statement file.")
  return clean_name


def validate_file_signature_and_size(file_path: Path) -> str:
  """Validates that the file exists, is within size limits, has a supported

  extension, and matches the expected binary signature (magic bytes). Returns
  the normalized lowercase extension (e.g. '.pdf').
  """
  settings = get_settings()
  if not file_path.exists() or not file_path.is_file():
    raise FileValidationError("Uploaded file could not be found.")

  file_size = file_path.stat().st_size
  if file_size == 0:
    raise FileValidationError(
        f"'{file_path.name}' is empty (0 bytes). Please upload a valid"
        " statement."
    )
  if file_size > settings.max_file_size_bytes:
    raise FileValidationError(
        f"'{file_path.name}' exceeds the {settings.MAX_FILE_SIZE_MB} MB limit."
    )

  ext = file_path.suffix.lower()
  if ext not in SUPPORTED_EXTENSIONS:
    raise FileValidationError(
        f"Unsupported format '{ext}'. Supported formats: PDF, DOCX, CSV, TXT."
    )

  # Read the first 2048 bytes to verify actual file content signature
  with file_path.open("rb") as f:
    header = f.read(2048)

  if ext == ".pdf":
    if not header.startswith(b"%PDF-"):
      raise FileValidationError(
          f"'{file_path.name}' does not have a valid PDF file signature."
      )
  elif ext == ".docx":
    if not header.startswith(b"PK\x03\x04") or not zipfile.is_zipfile(
        file_path
    ):
      raise FileValidationError(
          f"'{file_path.name}' is not a valid DOCX archive."
      )
    with zipfile.ZipFile(file_path, "r") as zf:
      if "word/document.xml" not in zf.namelist():
        raise FileValidationError(
            f"'{file_path.name}' is a ZIP archive, not a valid Word DOCX"
            " document."
        )
  elif ext in {".csv", ".txt"}:
    # Reject binary files (e.g. .exe, .pdf, .png renamed to .csv/.txt) containing null bytes
    if b"\x00" in header:
      raise FileValidationError(
          f"'{file_path.name}' contains binary data and is not a valid"
          f" {ext.upper()} text file."
      )

  return ext