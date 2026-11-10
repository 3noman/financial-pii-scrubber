from pathlib import Path
from typing import Any
from uuid import UUID
import uuid
from app.config import get_settings
from app.core.exceptions import FileValidationError
from app.core.logging import get_logger
from app.core.security import sanitize_filename
from app.database.connection import get_db
from app.schemas.schemas import CombinedProcessingResponse, FileProcessingDetail
from app.services.analytics import compute_deterministic_analytics
from app.services.database_service import (
    create_verified_statement_with_transactions,
    delete_statement_and_related_data,
    get_statement_by_id,
    get_transactions_for_statement,
    list_statements,
)
from app.services.processing import process_single_file
from app.services.transaction_parser import parse_transactions_from_scrubbed_text
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

logger = get_logger(__name__)
router = APIRouter(prefix="/api/statements", tags=["Statements"])


def _persist_batch_and_build_response(
    file_paths_with_names: list[tuple[Path, str]],
    db: Session,
) -> CombinedProcessingResponse:
  """Processes a list of (temp_path, original_filename) pairs, stores verified results in DB,

  writes the combined scrubbed output to outputs/combined_scrubbed_output.txt,
  and returns the summary.
  """
  settings = get_settings()
  details: list[FileProcessingDetail] = []
  combined_sections: list[str] = []

  successful_count = 0
  failed_count = 0
  unsupported_count = 0
  any_verification_failed = False

  for temp_path, original_name in file_paths_with_names:
    res = process_single_file(temp_path)
    res.detail.filename = original_name

    if res.detail.status == "success" and res.detail.verification_passed:
      parsed_txs = parse_transactions_from_scrubbed_text(res.scrubbed_text)
      db_stmt = create_verified_statement_with_transactions(
          db=db,
          original_filename=original_name,
          file_type=res.detail.file_type,
          scrubbed_content=res.scrubbed_text,
          verification_passed=True,
          redaction_summary=res.detail.entity_counts,
          parsed_transactions=parsed_txs,
      )
      res.detail.statement_id = db_stmt.id
      successful_count += 1
      combined_sections.append(
          f"---- File: {original_name} ----\n{res.scrubbed_text}"
      )
    elif res.detail.status == "unsupported":
      unsupported_count += 1
      failed_count += 1
    else:
      failed_count += 1
      if res.detail.status == "verification_failed":
        any_verification_failed = True
        create_verified_statement_with_transactions(
            db=db,
            original_filename=original_name,
            file_type=res.detail.file_type,
            scrubbed_content="",
            verification_passed=False,
            redaction_summary=res.detail.entity_counts,
            parsed_transactions=[],
        )

    details.append(res.detail)

  total_files = len(file_paths_with_names)
  all_verified = (successful_count > 0) and (not any_verification_failed)
  combined_str = "\n\n".join(combined_sections)

  # If multiple files succeeded, also store a combined portfolio statement record for unified analysis/chat
  if successful_count > 1 and all_verified:
    all_txs = parse_transactions_from_scrubbed_text(combined_str)
    combined_redactions: dict[str, int] = {}
    for d in details:
      for k, v in d.entity_counts.items():
        combined_redactions[k] = combined_redactions.get(k, 0) + v
    create_verified_statement_with_transactions(
        db=db,
        original_filename=f"Combined_Batch_{successful_count}_Files.txt",
        file_type="combined",
        scrubbed_content=combined_str,
        verification_passed=True,
        redaction_summary=combined_redactions,
        parsed_transactions=all_txs,
    )

  if combined_str:
    output_file = settings.OUTPUTS_DIR / "combined_scrubbed_output.txt"
    output_file.write_text(combined_str, encoding="utf-8")

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
      combined_output=combined_str,
      files=details,
  )


@router.post("/upload", response_model=CombinedProcessingResponse)
async def upload_statements(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> CombinedProcessingResponse:
  """Uploads one or more statement files, processes and scrubs them locally,

  deletes temporary raw files immediately, and stores verified scrubbed records.
  """
  settings = get_settings()
  if not files:
    raise FileValidationError("Please select at least one statement file.")
  if len(files) > settings.MAX_FILES_PER_REQUEST:
    raise FileValidationError(
        f"Maximum {settings.MAX_FILES_PER_REQUEST} files allowed per upload."
    )

  temp_files_to_cleanup: list[Path] = []
  batch_inputs: list[tuple[Path, str]] = []

  try:
    for upload in files:
      raw_name = upload.filename or "statement.txt"
      safe_name = sanitize_filename(raw_name)
      content = await upload.read()

      if len(content) > settings.max_file_size_bytes:
        raise FileValidationError(
            f"'{safe_name}' exceeds the {settings.MAX_FILE_SIZE_MB} MB file"
            " size limit."
        )

      unique_temp_name = f"{uuid.uuid4().hex}_{safe_name}"
      temp_path = settings.TEMP_UPLOAD_DIR / unique_temp_name
      temp_path.write_bytes(content)
      temp_files_to_cleanup.append(temp_path)
      batch_inputs.append((temp_path, safe_name))

    return _persist_batch_and_build_response(batch_inputs, db)
  finally:
    # CRITICAL PRIVACY REQUIREMENT: Always delete temporary raw files immediately
    for temp_path in temp_files_to_cleanup:
      try:
        if temp_path.exists():
          temp_path.unlink()
      except OSError:
        logger.warning("Could not remove temporary upload file.")


@router.post("/process-folder", response_model=CombinedProcessingResponse)
def process_data_folder(
    db: Session = Depends(get_db),
) -> CombinedProcessingResponse:
  """Processes all supported files inside the local data/ directory."""
  settings = get_settings()
  candidate_files = sorted(
      [
          (p, sanitize_filename(p.name))
          for p in settings.DATA_DIR.iterdir()
          if p.is_file() and not p.name.startswith(".")
      ],
      key=lambda item: item[1].lower(),
  )
  if not candidate_files:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            "No statement files were found in the data/ folder. Please upload"
            " files or place statements in data/."
        ),
    )
  return _persist_batch_and_build_response(candidate_files, db)


@router.get("")
def get_all_statements(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
  """Returns all stored statements ordered from newest to oldest."""
  records = list_statements(db)
  return [
      {
          "id": str(s.id),
          "original_filename": s.original_filename,
          "file_type": s.file_type,
          "processing_status": s.processing_status,
          "verification_status": s.verification_status,
          "redaction_summary": s.redaction_summary,
          "created_at": s.created_at.isoformat(),
      }
      for s in records
  ]


@router.get("/{statement_id}")
def get_statement_detail(
    statement_id: UUID, db: Session = Depends(get_db)
) -> dict[str, Any]:
  stmt = get_statement_by_id(db, statement_id)
  if not stmt:
    raise HTTPException(status_code=404, detail="Statement record not found.")
  txs = get_transactions_for_statement(db, statement_id)
  return {
      "id": str(stmt.id),
      "original_filename": stmt.original_filename,
      "file_type": stmt.file_type,
      "processing_status": stmt.processing_status,
      "verification_status": stmt.verification_status,
      "redaction_summary": stmt.redaction_summary,
      "transaction_count": len(txs),
      "created_at": stmt.created_at.isoformat(),
  }


@router.get("/{statement_id}/scrubbed")
def get_scrubbed_statement(
    statement_id: UUID, db: Session = Depends(get_db)
) -> dict[str, Any]:
  stmt = get_statement_by_id(db, statement_id)
  if not stmt:
    raise HTTPException(status_code=404, detail="Statement record not found.")
  return {
      "statement_id": str(stmt.id),
      "original_filename": stmt.original_filename,
      "verification_status": stmt.verification_status,
      "redaction_summary": stmt.redaction_summary,
      "scrubbed_content": stmt.scrubbed_content,
  }


@router.get("/{statement_id}/verification")
def get_statement_verification(
    statement_id: UUID, db: Session = Depends(get_db)
) -> dict[str, Any]:
  stmt = get_statement_by_id(db, statement_id)
  if not stmt:
    raise HTTPException(status_code=404, detail="Statement record not found.")
  passed = stmt.verification_status == "passed"
  total_redactions = sum((stmt.redaction_summary or {}).values())
  return {
      "statement_id": str(stmt.id),
      "original_filename": stmt.original_filename,
      "verification_passed": passed,
      "verification_status": stmt.verification_status,
      "safe_for_ai_analysis": passed,
      "total_redactions": total_redactions,
      "redaction_summary": stmt.redaction_summary,
      "human_message": (
          "Personal and financial identifiers have been replaced with safe"
          " placeholders. This statement is verified safe for AI analysis."
          if passed
          else (
              "Verification blocked this statement because potential sensitive"
              " patterns remained. It will not be sent to external AI."
          )
      ),
  }


@router.get("/{statement_id}/transactions")
def get_statement_transactions(
    statement_id: UUID, db: Session = Depends(get_db)
) -> dict[str, Any]:
  stmt = get_statement_by_id(db, statement_id)
  if not stmt:
    raise HTTPException(status_code=404, detail="Statement record not found.")
  txs = get_transactions_for_statement(db, statement_id)
  tx_schemas = parse_transactions_from_scrubbed_text(stmt.scrubbed_content)
  deterministic_summary = compute_deterministic_analytics(tx_schemas)
  return {
      "statement_id": str(stmt.id),
      "original_filename": stmt.original_filename,
      "count": len(txs),
      "summary": deterministic_summary,
      "transactions": [
          {
              "id": str(t.id),
              "transaction_date": t.transaction_date,
              "merchant_name": t.merchant_name,
              "description": t.description,
              "transaction_type": t.transaction_type,
              "amount": float(t.amount),
              "currency": t.currency,
              "balance": float(t.balance) if t.balance is not None else None,
              "category": t.category,
          }
          for t in txs
      ],
  }


@router.delete("/{statement_id}")
def delete_statement(
    statement_id: UUID, db: Session = Depends(get_db)
) -> dict[str, Any]:
  deleted = delete_statement_and_related_data(db, statement_id)
  if not deleted:
    raise HTTPException(status_code=404, detail="Statement record not found.")
  return {
      "status": "deleted",
      "statement_id": str(statement_id),
      "message": (
          "Statement and all associated transactions, AI analyses, and chat"
          " history have been permanently deleted."
      ),
  }