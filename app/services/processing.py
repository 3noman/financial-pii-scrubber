from dataclasses import dataclass
from pathlib import Path
from app.core.exceptions import DocumentExtractionError, FileValidationError
from app.core.logging import get_logger
from app.core.security import SUPPORTED_EXTENSIONS, sanitize_filename
from app.schemas.schemas import CombinedProcessingResponse, FileProcessingDetail
from app.services.extractors import extract_document
from app.services.pii.anonymizer import scrub_text
from app.services.pii.verifier import VerificationReport, verify_scrubbed_text

logger = get_logger(__name__)


@dataclass
class SingleFileProcessedResult:
  """Internal result for one processed file before database persistence."""

  detail: FileProcessingDetail
  scrubbed_text: str
  verification_report: VerificationReport | None = None


def process_single_file(file_path: Path) -> SingleFileProcessedResult:
  """Executes the local privacy workflow on a single file:

  Raw file -> Signature check & Extraction -> Local PII Scrubbing -> Independent
  Verification. Never raises unhandled exceptions so one bad file cannot crash a
  batch.
  """
  try:
    safe_name = sanitize_filename(file_path.name)
  except FileValidationError:
    safe_name = file_path.name

  ext = file_path.suffix.lower()
  if ext not in SUPPORTED_EXTENSIONS:
    logger.warning(f"Skipping unsupported file format: {safe_name}")
    return SingleFileProcessedResult(
        detail=FileProcessingDetail(
            filename=safe_name,
            file_type=ext or "unknown",
            status="unsupported",
            verification_passed=False,
            error_message=(
                f"Unsupported file format '{ext}'. Supported: PDF, DOCX,"
                " CSV, TXT."
            ),
        ),
        scrubbed_text="",
    )

  try:
    # Step 1: Local Extraction
    raw_text = extract_document(file_path)

    # Step 2: Local PII Detection & Replacement
    scrub_result = scrub_text(raw_text)

    # Step 3: Independent Security Gate Verification
    verification = verify_scrubbed_text(scrub_result.scrubbed_text)
    if not verification.passed:
      logger.error(f"Privacy verification failed for file: {safe_name}")
      return SingleFileProcessedResult(
          detail=FileProcessingDetail(
              filename=safe_name,
              file_type=ext.lstrip("."),
              status="verification_failed",
              verification_passed=False,
              redaction_count=scrub_result.total_redactions,
              entity_counts=scrub_result.entity_counts,
              error_message=(
                  "Privacy verification blocked this statement: "
                  + "; ".join(verification.findings)
              ),
          ),
          scrubbed_text="",
          verification_report=verification,
      )

    logger.info(
        f"Processed and verified '{safe_name}' "
        f"({scrub_result.total_redactions} identifiers scrubbed)."
    )
    return SingleFileProcessedResult(
        detail=FileProcessingDetail(
            filename=safe_name,
            file_type=ext.lstrip("."),
            status="success",
            verification_passed=True,
            redaction_count=scrub_result.total_redactions,
            entity_counts=scrub_result.entity_counts,
        ),
        scrubbed_text=scrub_result.scrubbed_text,
        verification_report=verification,
    )

  except (FileValidationError, DocumentExtractionError) as exc:
    logger.warning(f"File processing failed for '{safe_name}': {exc.user_message}")
    return SingleFileProcessedResult(
        detail=FileProcessingDetail(
            filename=safe_name,
            file_type=ext.lstrip("."),
            status="failed",
            verification_passed=False,
            error_message=exc.user_message,
        ),
        scrubbed_text="",
    )
  except Exception as exc:
    logger.error(
        f"Unexpected error processing '{safe_name}': {type(exc).__name__}"
    )
    return SingleFileProcessedResult(
        detail=FileProcessingDetail(
            filename=safe_name,
            file_type=ext.lstrip("."),
            status="failed",
            verification_passed=False,
            error_message=(
                f"Could not process '{safe_name}' due to an internal format"
                " error."
            ),
        ),
        scrubbed_text="",
    )


def process_directory(directory_path: Path) -> CombinedProcessingResponse:
  """Discovers all files in a directory, processes supported formats, isolates errors,

  and combines all verified scrubbed outputs using the exact Section 3/7 header
  format.
  """
  if not directory_path.exists() or not directory_path.is_dir():
    return CombinedProcessingResponse(
        status="failed",
        total_files=0,
        successful_files=0,
        failed_files=0,
        unsupported_files=0,
        verification_passed=False,
        combined_output="",
        files=[],
    )

  # Discover all non-hidden files (ignore .gitkeep and dotfiles)
  candidate_files = sorted(
      [
          p
          for p in directory_path.iterdir()
          if p.is_file() and not p.name.startswith(".")
      ],
      key=lambda p: p.name.lower(),
  )

  return process_file_list(candidate_files)


def process_file_list(file_paths: list[Path]) -> CombinedProcessingResponse:
  """Processes a list of file paths and returns the CombinedProcessingResponse."""
  details: list[FileProcessingDetail] = []
  combined_sections: list[str] = []

  successful_count = 0
  failed_count = 0
  unsupported_count = 0
  any_verification_failed = False

  for file_path in file_paths:
    res = process_single_file(file_path)
    details.append(res.detail)

    if res.detail.status == "success" and res.detail.verification_passed:
      successful_count += 1
      header = f"---- File: {res.detail.filename} ----"
      combined_sections.append(f"{header}\n{res.scrubbed_text}")
    elif res.detail.status == "unsupported":
      unsupported_count += 1
      failed_count += 1
    else:
      failed_count += 1
      if res.detail.status == "verification_failed":
        any_verification_failed = True

  total_files = len(file_paths)
  all_verified = (successful_count > 0) and (not any_verification_failed)

  if successful_count == total_files and total_files > 0:
    overall_status = "success"
  elif successful_count > 0:
    overall_status = "partial_success"
  else:
    overall_status = "failed"

  return CombinedProcessingResponse(
      status=overall_status,
      total_files=total_files,
      successful_files=successful_count,
      failed_files=failed_count,
      unsupported_files=unsupported_count,
      verification_passed=all_verified,
      combined_output="\n\n".join(combined_sections),
      files=details,
  )