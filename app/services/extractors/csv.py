import csv
import io
from pathlib import Path
from app.core.exceptions import DocumentExtractionError
from app.services.extractors.txt import read_text_with_fallback


def extract_csv(file_path: Path) -> str:
    """Extracts rows from a CSV statement, preserving column structure."""
    try:
        raw_text = read_text_with_fallback(file_path)
        if not raw_text.strip():
            raise DocumentExtractionError(file_path.name, "CSV file is empty.")

        reader = csv.reader(io.StringIO(raw_text))
        formatted_rows: list[str] = []
        for row in reader:
            cleaned_cells = [cell.strip() for cell in row if cell and cell.strip()]
            if cleaned_cells:
                formatted_rows.append(" | ".join(cleaned_cells))

        if not formatted_rows:
            raise DocumentExtractionError(
                file_path.name, "CSV file contains no non-empty rows."
            )
        return "\n".join(formatted_rows)
    except DocumentExtractionError:
        raise
    except csv.Error as exc:
        raise DocumentExtractionError(
            file_path.name, "Malformed CSV structure."
        ) from exc
    except Exception as exc:
        raise DocumentExtractionError(
            file_path.name, f"Could not read CSV ({type(exc).__name__})."
        ) from exc
