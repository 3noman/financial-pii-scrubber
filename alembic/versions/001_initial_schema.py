"""Initial schema for statements, transactions, analyses, and chat messages

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-11-10 13:15:00
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  # 1. statements table
  op.create_table(
      "statements",
      sa.Column("id", sa.Uuid(), nullable=False),
      sa.Column("original_filename", sa.String(length=255), nullable=False),
      sa.Column("file_type", sa.String(length=20), nullable=False),
      sa.Column("processing_status", sa.String(length=50), nullable=False),
      sa.Column("scrubbed_content", sa.Text(), nullable=False),
      sa.Column("verification_status", sa.String(length=50), nullable=False),
      sa.Column("redaction_summary", sa.JSON(), nullable=False),
      sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
      sa.PrimaryKeyConstraint("id"),
  )
  op.create_index(
      "ix_statements_created_at", "statements", ["created_at"], unique=False
  )
  op.create_index(
      "ix_statements_processing_status",
      "statements",
      ["processing_status"],
      unique=False,
  )
  op.create_index(
      "ix_statements_verification_status",
      "statements",
      ["verification_status"],
      unique=False,
  )

  # 2. transactions table
  op.create_table(
      "transactions",
      sa.Column("id", sa.Uuid(), nullable=False),
      sa.Column("statement_id", sa.Uuid(), nullable=False),
      sa.Column("transaction_date", sa.String(length=32), nullable=False),
      sa.Column("merchant_name", sa.String(length=255), nullable=False),
      sa.Column("description", sa.Text(), nullable=False),
      sa.Column("transaction_type", sa.String(length=20), nullable=False),
      sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
      sa.Column("currency", sa.String(length=10), nullable=False),
      sa.Column("balance", sa.Numeric(precision=14, scale=2), nullable=True),
      sa.Column("category", sa.String(length=80), nullable=False),
      sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
      sa.ForeignKeyConstraint(
          ["statement_id"], ["statements.id"], ondelete="CASCADE"
      ),
      sa.PrimaryKeyConstraint("id"),
  )
  op.create_index(
      "ix_transactions_category", "transactions", ["category"], unique=False
  )
  op.create_index(
      "ix_transactions_merchant_name",
      "transactions",
      ["merchant_name"],
      unique=False,
  )
  op.create_index(
      "ix_transactions_statement_id",
      "transactions",
      ["statement_id"],
      unique=False,
  )
  op.create_index(
      "ix_transactions_transaction_date",
      "transactions",
      ["transaction_date"],
      unique=False,
  )
  op.create_index(
      "ix_transactions_transaction_type",
      "transactions",
      ["transaction_type"],
      unique=False,
  )

  # 3. analyses table
  op.create_table(
      "analyses",
      sa.Column("id", sa.Uuid(), nullable=False),
      sa.Column("statement_id", sa.Uuid(), nullable=False),
      sa.Column("analysis_result", sa.JSON(), nullable=False),
      sa.Column("model_name", sa.String(length=100), nullable=False),
      sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
      sa.ForeignKeyConstraint(
          ["statement_id"], ["statements.id"], ondelete="CASCADE"
      ),
      sa.PrimaryKeyConstraint("id"),
  )
  op.create_index(
      "ix_analyses_statement_id", "analyses", ["statement_id"], unique=False
  )

  # 4. chat_messages table
  op.create_table(
      "chat_messages",
      sa.Column("id", sa.Uuid(), nullable=False),
      sa.Column("statement_id", sa.Uuid(), nullable=False),
      sa.Column("conversation_id", sa.Uuid(), nullable=False),
      sa.Column("role", sa.String(length=20), nullable=False),
      sa.Column("message", sa.Text(), nullable=False),
      sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
      sa.ForeignKeyConstraint(
          ["statement_id"], ["statements.id"], ondelete="CASCADE"
      ),
      sa.PrimaryKeyConstraint("id"),
  )
  op.create_index(
      "ix_chat_messages_conversation_id",
      "chat_messages",
      ["conversation_id"],
      unique=False,
  )
  op.create_index(
      "ix_chat_messages_statement_id",
      "chat_messages",
      ["statement_id"],
      unique=False,
  )
  op.create_index(
      "ix_chat_statement_conv",
      "chat_messages",
      ["statement_id", "conversation_id"],
      unique=False,
  )


def downgrade() -> None:
  op.drop_table("chat_messages")
  op.drop_table("analyses")
  op.drop_table("transactions")
  op.drop_table("statements")