from pathlib import Path
from typing import Callable
from app.core.security import SUPPORTED_EXTENSIONS, validate_file_signature_and_size
from app.services.extractors.csv import extract_csv
from app.services.extractors.docx import extract_docx
from app.services.extractors.pdf import extract_pdf
from app.services.extractors.txt import extract_txt

EXTRACTOR_REGISTRY: dict[str, Callable[[Path], str]] = {
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".csv": extract_csv,
    ".txt": extract_txt,
}


def extract_document(file_path: Path) -> str:
    """Validates file signature and size, then extracts text using the appropriate

    format-specific extractor.
    """
    ext = validate_file_signature_and_size(file_path)
    extractor = EXTRACTOR_REGISTRY[ext]
    return extractor(file_path)


__all__ = [
    "SUPPORTED_EXTENSIONS",
    "EXTRACTOR_REGISTRY",
    "extract_document",
]
