from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class FileProcessingDetail(BaseModel):
  """Per-file processing status in a batch or folder run."""

  filename: str
  file_type: str
  status: Literal["success", "failed", "unsupported", "verification_failed"]
  verification_passed: bool = False
  redaction_count: int = 0
  entity_counts: dict[str, int] = Field(default_factory=dict)
  error_message: str | None = None
  statement_id: UUID | None = None


class CombinedProcessingResponse(BaseModel):
  """Pydantic response model matching Section 7 (Combined Output Engine)."""

  status: Literal["success", "partial_success", "failed"]
  total_files: int
  successful_files: int
  failed_files: int
  unsupported_files: int = 0
  verification_passed: bool
  combined_output: str
  files: list[FileProcessingDetail] = Field(default_factory=list)


class TransactionSchema(BaseModel):
  """Validated transaction record."""

  model_config = ConfigDict(from_attributes=True)

  id: UUID | None = None
  statement_id: UUID | None = None
  transaction_date: str
  merchant_name: str
  description: str
  transaction_type: Literal["Debit", "Credit"]
  amount: Decimal
  currency: str = "PKR"
  balance: Decimal | None = None
  category: str = "Uncategorized"


class StatementSummarySchema(BaseModel):
  """Summary of a stored statement record in PostgreSQL."""

  model_config = ConfigDict(from_attributes=True)

  id: UUID
  original_filename: str
  file_type: str
  processing_status: str
  verification_status: str
  created_at: datetime