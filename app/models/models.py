from datetime import datetime, timezone
from decimal import Decimal
import uuid
from app.database.base import Base
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship


def _utc_now() -> datetime:
  return datetime.now(timezone.utc)


class Statement(Base):
  """Stores only verified scrubbed statement text and privacy metadata.

  Raw statement contents are never persisted.
  """

  __tablename__ = "statements"

  id: Mapped[uuid.UUID] = mapped_column(
      Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
  )
  original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
  file_type: Mapped[str] = mapped_column(String(20), nullable=False)
  processing_status: Mapped[str] = mapped_column(
      String(50), nullable=False, index=True
  )
  scrubbed_content: Mapped[str] = mapped_column(Text, nullable=False)
  verification_status: Mapped[str] = mapped_column(
      String(50), nullable=False, index=True
  )
  redaction_summary: Mapped[dict] = mapped_column(
      JSON, default=dict, nullable=False
  )
  created_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True), default=_utc_now, nullable=False, index=True
  )

  transactions: Mapped[list["Transaction"]] = relationship(
      "Transaction",
      back_populates="statement",
      cascade="all, delete-orphan",
      passive_deletes=True,
  )
  analyses: Mapped[list["Analysis"]] = relationship(
      "Analysis",
      back_populates="statement",
      cascade="all, delete-orphan",
      passive_deletes=True,
  )
  chat_messages: Mapped[list["ChatMessage"]] = relationship(
      "ChatMessage",
      back_populates="statement",
      cascade="all, delete-orphan",
      passive_deletes=True,
  )


class Transaction(Base):
  """Structured financial transaction parsed from a verified scrubbed statement."""

  __tablename__ = "transactions"

  id: Mapped[uuid.UUID] = mapped_column(
      Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
  )
  statement_id: Mapped[uuid.UUID] = mapped_column(
      Uuid(as_uuid=True),
      ForeignKey("statements.id", ondelete="CASCADE"),
      nullable=False,
      index=True,
  )
  transaction_date: Mapped[str] = mapped_column(
      String(32), nullable=False, index=True
  )
  merchant_name: Mapped[str] = mapped_column(
      String(255), nullable=False, index=True
  )
  description: Mapped[str] = mapped_column(Text, nullable=False)
  transaction_type: Mapped[str] = mapped_column(
      String(20), nullable=False, index=True
  )
  amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
  currency: Mapped[str] = mapped_column(
      String(10), nullable=False, default="PKR"
  )
  balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
  category: Mapped[str] = mapped_column(
      String(80), nullable=False, default="Other", index=True
  )
  created_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True), default=_utc_now, nullable=False
  )

  statement: Mapped["Statement"] = relationship(
      "Statement", back_populates="transactions"
  )


class Analysis(Base):
  """Stores verified AI budgeting insights alongside deterministic Python metrics."""

  __tablename__ = "analyses"

  id: Mapped[uuid.UUID] = mapped_column(
      Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
  )
  statement_id: Mapped[uuid.UUID] = mapped_column(
      Uuid(as_uuid=True),
      ForeignKey("statements.id", ondelete="CASCADE"),
      nullable=False,
      index=True,
  )
  analysis_result: Mapped[dict] = mapped_column(JSON, nullable=False)
  model_name: Mapped[str] = mapped_column(String(100), nullable=False)
  created_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True), default=_utc_now, nullable=False
  )

  statement: Mapped["Statement"] = relationship(
      "Statement", back_populates="analyses"
  )


class ChatMessage(Base):
  """Stores grounded Q&A conversation history scoped to a specific statement."""

  __tablename__ = "chat_messages"
  __table_args__ = (
      Index("ix_chat_statement_conv", "statement_id", "conversation_id"),
  )

  id: Mapped[uuid.UUID] = mapped_column(
      Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
  )
  statement_id: Mapped[uuid.UUID] = mapped_column(
      Uuid(as_uuid=True),
      ForeignKey("statements.id", ondelete="CASCADE"),
      nullable=False,
      index=True,
  )
  conversation_id: Mapped[uuid.UUID] = mapped_column(
      Uuid(as_uuid=True), nullable=False, index=True, default=uuid.uuid4
  )
  role: Mapped[str] = mapped_column(String(20), nullable=False)
  message: Mapped[str] = mapped_column(Text, nullable=False)
  created_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True), default=_utc_now, nullable=False
  )

  statement: Mapped["Statement"] = relationship(
      "Statement", back_populates="chat_messages"
  )