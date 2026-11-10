from typing import Any
from uuid import UUID
from app.core.exceptions import PrivacyVerificationFailedError
from app.database.connection import get_db
from app.services.database_service import (
    get_latest_analysis,
    get_statement_by_id,
    save_analysis_result,
)
from app.services.groq_service import generate_budget_analysis
from app.services.transaction_parser import parse_transactions_from_scrubbed_text
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/statements", tags=["AI Budget Analysis"])


@router.post("/{statement_id}/analyze")
def run_statement_analysis(
    statement_id: UUID, db: Session = Depends(get_db)
) -> dict[str, Any]:
  """Runs privacy gate verification, deterministic Python math, and Groq AI analysis."""
  stmt = get_statement_by_id(db, statement_id)
  if not stmt:
    raise HTTPException(status_code=404, detail="Statement record not found.")

  if stmt.verification_status != "passed" or not stmt.scrubbed_content.strip():
    raise PrivacyVerificationFailedError([
        "Statement has not passed privacy verification and cannot be sent for"
        " AI analysis."
    ])

  tx_schemas = parse_transactions_from_scrubbed_text(stmt.scrubbed_content)
  analysis_payload, model_used = generate_budget_analysis(
      scrubbed_text=stmt.scrubbed_content,
      transactions=tx_schemas,
  )

  saved = save_analysis_result(
      db=db,
      statement_id=stmt.id,
      analysis_result=analysis_payload,
      model_name=model_used,
  )

  return {
      "analysis_id": str(saved.id),
      "statement_id": str(stmt.id),
      "original_filename": stmt.original_filename,
      "model_name": saved.model_name,
      "created_at": saved.created_at.isoformat(),
      "analysis": saved.analysis_result,
  }


@router.get("/{statement_id}/analysis")
def get_statement_analysis(
    statement_id: UUID, db: Session = Depends(get_db)
) -> dict[str, Any]:
  stmt = get_statement_by_id(db, statement_id)
  if not stmt:
    raise HTTPException(status_code=404, detail="Statement record not found.")

  latest = get_latest_analysis(db, statement_id)
  if not latest:
    raise HTTPException(
        status_code=404,
        detail=(
            "No spending report has been generated for this statement yet."
            " Click 'Generate AI Insights' to create one."
        ),
    )

  return {
      "analysis_id": str(latest.id),
      "statement_id": str(stmt.id),
      "original_filename": stmt.original_filename,
      "model_name": latest.model_name,
      "created_at": latest.created_at.isoformat(),
      "analysis": latest.analysis_result,
  }