from uuid import UUID
from app.models.models import Analysis, ChatMessage, Statement, Transaction
from app.schemas.schemas import TransactionSchema
from sqlalchemy import select
from sqlalchemy.orm import Session


def create_verified_statement_with_transactions(
    db: Session,
    original_filename: str,
    file_type: str,
    scrubbed_content: str,
    verification_passed: bool,
    redaction_summary: dict[str, int],
    parsed_transactions: list[TransactionSchema],
) -> Statement:
  """Persists a verified scrubbed statement and its parsed transactions in a single atomic transaction."""
  statement = Statement(
      original_filename=original_filename,
      file_type=file_type,
      processing_status="completed" if verification_passed else "blocked",
      scrubbed_content=scrubbed_content if verification_passed else "",
      verification_status="passed" if verification_passed else "failed",
      redaction_summary=redaction_summary,
  )
  db.add(statement)
  db.flush()  # Generates statement.id UUID before inserting child transactions

  if verification_passed:
    for tx in parsed_transactions:
      db_tx = Transaction(
          statement_id=statement.id,
          transaction_date=tx.transaction_date,
          merchant_name=tx.merchant_name,
          description=tx.description,
          transaction_type=tx.transaction_type,
          amount=tx.amount,
          currency=tx.currency,
          balance=tx.balance,
          category=tx.category,
      )
      db.add(db_tx)

  db.commit()
  db.refresh(statement)
  return statement


def list_statements(db: Session) -> list[Statement]:
  stmt = select(Statement).order_by(Statement.created_at.desc())
  return list(db.scalars(stmt).all())


def get_statement_by_id(db: Session, statement_id: UUID) -> Statement | None:
  return db.get(Statement, statement_id)


def get_transactions_for_statement(
    db: Session, statement_id: UUID
) -> list[Transaction]:
  stmt = (
      select(Transaction)
      .where(Transaction.statement_id == statement_id)
      .order_by(Transaction.transaction_date.asc(), Transaction.created_at.asc())
  )
  return list(db.scalars(stmt).all())


def save_analysis_result(
    db: Session,
    statement_id: UUID,
    analysis_result: dict,
    model_name: str,
) -> Analysis:
  analysis = Analysis(
      statement_id=statement_id,
      analysis_result=analysis_result,
      model_name=model_name,
  )
  db.add(analysis)
  db.commit()
  db.refresh(analysis)
  return analysis


def get_latest_analysis(db: Session, statement_id: UUID) -> Analysis | None:
  stmt = (
      select(Analysis)
      .where(Analysis.statement_id == statement_id)
      .order_by(Analysis.created_at.desc())
  )
  return db.scalars(stmt).first()


def save_chat_message(
    db: Session,
    statement_id: UUID,
    conversation_id: UUID,
    role: str,
    message: str,
) -> ChatMessage:
  msg = ChatMessage(
      statement_id=statement_id,
      conversation_id=conversation_id,
      role=role,
      message=message,
  )
  db.add(msg)
  db.commit()
  db.refresh(msg)
  return msg


def get_chat_history(
    db: Session, conversation_id: UUID, statement_id: UUID | None = None
) -> list[ChatMessage]:
  stmt = select(ChatMessage).where(
      ChatMessage.conversation_id == conversation_id
  )
  if statement_id is not None:
    stmt = stmt.where(ChatMessage.statement_id == statement_id)
  stmt = stmt.order_by(ChatMessage.created_at.asc())
  return list(db.scalars(stmt).all())


def delete_statement_and_related_data(db: Session, statement_id: UUID) -> bool:
  """Deletes a statement and cascades deletion to its transactions, analyses, and chat messages."""
  statement = db.get(Statement, statement_id)
  if not statement:
    return False
  db.delete(statement)
  db.commit()
  return True