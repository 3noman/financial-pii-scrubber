from typing import Any
from uuid import UUID
import uuid
from app.core.exceptions import PrivacyVerificationFailedError
from app.database.connection import get_db
from app.services.chat_service import answer_budget_chat_question
from app.services.database_service import (
    get_chat_history,
    get_statement_by_id,
    save_chat_message,
)
from app.services.transaction_parser import parse_transactions_from_scrubbed_text
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/chat", tags=["Grounded AI Chat"])


class ChatRequestSchema(BaseModel):
  statement_id: UUID
  question: str = Field(min_length=2, max_length=1000)
  conversation_id: UUID | None = None


@router.post("")
def ask_chat_question(
    payload: ChatRequestSchema, db: Session = Depends(get_db)
) -> dict[str, Any]:
  stmt = get_statement_by_id(db, payload.statement_id)
  if not stmt:
    raise HTTPException(status_code=404, detail="Statement record not found.")

  if stmt.verification_status != "passed" or not stmt.scrubbed_content.strip():
    raise PrivacyVerificationFailedError(
        ["Statement failed privacy verification and cannot be used for chat."]
    )

  conv_id = payload.conversation_id or uuid.uuid4()
  existing_msgs = get_chat_history(db, conv_id, stmt.id)
  history_dicts = [
      {"role": m.role, "message": m.message} for m in existing_msgs
  ]

  tx_schemas = parse_transactions_from_scrubbed_text(stmt.scrubbed_content)

  # Save user's question
  save_chat_message(
      db=db,
      statement_id=stmt.id,
      conversation_id=conv_id,
      role="user",
      message=payload.question,
  )

  # Generate grounded reply
  reply = answer_budget_chat_question(
      question=payload.question,
      scrubbed_text=stmt.scrubbed_content,
      transactions=tx_schemas,
      conversation_history=history_dicts,
  )

  # Save assistant's answer
  saved_reply = save_chat_message(
      db=db,
      statement_id=stmt.id,
      conversation_id=conv_id,
      role="assistant",
      message=reply,
  )

  return {
      "conversation_id": str(conv_id),
      "statement_id": str(stmt.id),
      "question": payload.question,
      "answer": reply,
      "created_at": saved_reply.created_at.isoformat(),
  }


@router.get("/{conversation_id}")
def retrieve_conversation_history(
    conversation_id: UUID,
    statement_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
  messages = get_chat_history(db, conversation_id, statement_id)
  return {
      "conversation_id": str(conversation_id),
      "message_count": len(messages),
      "messages": [
          {
              "id": str(m.id),
              "statement_id": str(m.statement_id),
              "role": m.role,
              "message": m.message,
              "created_at": m.created_at.isoformat(),
          }
          for m in messages
      ],
  }